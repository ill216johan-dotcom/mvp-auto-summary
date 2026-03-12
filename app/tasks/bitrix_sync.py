"""
Bitrix24 CRM sync — daily pull of leads, contacts, calls, emails, comments.
Tasks 5 (leads/contacts mapping), 6 (calls), 7 (emails), 8 (comments), 12 (pipeline).
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from app.core.logger import get_logger

log = get_logger("bitrix_sync")

# Bitrix OWNER_TYPE_ID constants
OWNER_TYPE_LEAD = 1
OWNER_TYPE_CONTACT = 3

# Activity TYPE_ID constants
ACTIVITY_CALL = 1
ACTIVITY_EMAIL = 4


# ── Helpers ───────────────────────────────────────────────────────────────────

def _extract_phone(phone_field: Any) -> str:
    """Extract first phone number from Bitrix phone field (list of dicts)."""
    if isinstance(phone_field, list) and phone_field:
        return str(phone_field[0].get("VALUE", ""))
    return str(phone_field or "")


def _extract_email(email_field: Any) -> str:
    """Extract first email address from Bitrix email field (list of dicts)."""
    if isinstance(email_field, list) and email_field:
        return str(email_field[0].get("VALUE", ""))
    return str(email_field or "")


def _parse_datetime(val: str | None) -> datetime | None:
    """Parse Bitrix datetime string to Python datetime."""
    if not val:
        return None
    try:
        return datetime.fromisoformat(val)
    except (ValueError, TypeError):
        return None


def _extract_contract_number(value: str | None) -> str | None:
    """Extract ФФ-XXXX contract number from a string. Returns e.g. 'ФФ-4405' or None."""
    if not value:
        return None
    value = str(value).strip()
    # Matches FF-4405 or ФФ-4405 (Cyrillic variant)
    m = re.search(r"(?:FF|ФФ|фф)-?(\d+)", value, re.IGNORECASE)
    if m:
        return f'ФФ-{m.group(1)}'
    return None


def _extract_email_addresses(communications: Any) -> tuple[str, str]:
    """Extract from/to emails from Bitrix activity COMMUNICATIONS list."""
    email_from = ""
    email_to = ""
    if not isinstance(communications, list):
        return email_from, email_to
    for comm in communications:
        if not isinstance(comm, dict):
            continue
        if comm.get("TYPE") == "EMAIL":
            val = comm.get("VALUE", "")
            direction = int(comm.get("DIRECTION", 0))
            if direction == 1:  # incoming — sender
                email_from = val
            elif direction == 2:  # outgoing — recipient
                email_to = val
            elif not email_from:
                email_from = val
    return email_from, email_to


# ── Wave 2 sync functions ─────────────────────────────────────────────────────

def _enrich_call_record_urls(client: Any, conn: Any, lead: dict, stats: dict) -> None:
    """
    Fetch call recordings from voximplant.statistic.get for a lead and update
    bitrix_calls with record_url + set transcript_status='pending' for Whisper.
    """
    entity_type = "LEAD" if lead["bitrix_entity_type"] == "lead" else "CONTACT"
    try:
        records = client.get_call_history(filter={
            "CRM_ENTITY_TYPE": entity_type,
            "CRM_ENTITY_ID": lead["bitrix_lead_id"],
        })
    except Exception as e:
        log.warning("voximplant_fetch_failed", lead_id=lead.get("bitrix_lead_id"), error=str(e))
        return

    for rec in records:
        record_url = rec.get("CALL_RECORD_URL") or rec.get("SRC_URL") or ""
        bitrix_call_id = rec.get("CALL_ID", "")
        phone_number = rec.get("PHONE_NUMBER", "")

        # Skip if neither record_url nor phone_number
        if not record_url and not phone_number:
            continue
        try:
            cur = conn.cursor()
            try:
                # Match by bitrix_call_id if available, otherwise by lead + approximate date
                if bitrix_call_id:
                    phone_number = rec.get("PHONE_NUMBER", "")
                    cur.execute(
                        """
                        UPDATE bitrix_calls
                        SET record_url = %s, phone_number = %s, transcript_status = 'pending'
                        WHERE bitrix_call_id = %s
                          AND transcript_status = 'no_record'
                        """,
                        (record_url, phone_number, bitrix_call_id),
                    )
                else:
                    # Fallback: match by lead_id + call date (within same minute)
                    call_start = rec.get("CALL_START_DATE")
                    phone_number = rec.get("PHONE_NUMBER", "")
                    if call_start:
                        cur.execute(
                            """
                            UPDATE bitrix_calls
                            SET record_url = %s, phone_number = %s, transcript_status = 'pending'
                            WHERE bitrix_lead_id = %s
                              AND transcript_status = 'no_record'
                              AND DATE_TRUNC('minute', call_date) =
                                  DATE_TRUNC('minute', %s::timestamptz)
                            LIMIT 1
                            """,
                            (record_url, phone_number, lead["bitrix_lead_id"], call_start),
                        )
                conn.commit()
                if cur.rowcount and cur.rowcount > 0:
                    stats["urls_enriched"] = stats.get("urls_enriched", 0) + 1
            except Exception as e:
                conn.rollback()
                log.warning("call_url_update_failed", call_id=bitrix_call_id, error=str(e))
            finally:
                cur.close()
        except Exception as e:
            log.warning("call_enrich_error", error=str(e))


def sync_bitrix_leads(client: Any, conn: Any) -> dict:
    """
    Sync all Bitrix Leads → bitrix_leads table with diffy_lead_id = BX-LEAD-{id}.
    Returns stats dict.
    """
    stats = {"leads_synced": 0, "errors": []}
    try:
        leads = client.get_leads(select=[
            "ID", "TITLE", "NAME", "LAST_NAME", "PHONE", "EMAIL",
            "STATUS_ID", "SOURCE_ID", "ASSIGNED_BY_ID",
        ])
    except Exception as e:
        log.error("bitrix_get_leads_failed", error=str(e))
        stats["errors"].append(str(e))
        return stats

    # Batch-resolve user names
    user_ids = list({int(l.get("ASSIGNED_BY_ID", 0)) for l in leads if l.get("ASSIGNED_BY_ID")})
    user_map: dict[int, str] = {}
    if user_ids:
        try:
            user_map = client.get_users(user_ids)
        except Exception as e:
            log.warning("bitrix_users_failed", error=str(e))

    for lead in leads:
        try:
            lead_id = int(lead["ID"])
            # Try to extract ФФ-номер from title first
            ff_number = _extract_contract_number(lead.get("TITLE", ""))
            diffy_lead_id = ff_number if ff_number else f"BX-LEAD-{lead_id}"
            responsible_id = int(lead.get("ASSIGNED_BY_ID") or 0)
            name_parts = [lead.get("NAME", ""), lead.get("LAST_NAME", "")]
            full_name = " ".join(p for p in name_parts if p).strip()

            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO bitrix_leads
                        (bitrix_lead_id, bitrix_entity_type, diffy_lead_id, title, name,
                         phone, email, status_id, source_id, responsible_id,
                         responsible_name, last_synced_at)
                    VALUES (%s, 'lead', %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (bitrix_lead_id) DO UPDATE SET
                        diffy_lead_id    = EXCLUDED.diffy_lead_id,
                        title            = EXCLUDED.title,
                        name             = EXCLUDED.name,
                        phone            = EXCLUDED.phone,
                        email            = EXCLUDED.email,
                        status_id        = EXCLUDED.status_id,
                        responsible_id   = EXCLUDED.responsible_id,
                        responsible_name = EXCLUDED.responsible_name,
                        last_synced_at   = NOW()
                    """,
                    (
                        lead_id, diffy_lead_id,
                        lead.get("TITLE", ""), full_name,
                        _extract_phone(lead.get("PHONE")),
                        _extract_email(lead.get("EMAIL")),
                        lead.get("STATUS_ID", ""), lead.get("SOURCE_ID", ""),
                        responsible_id, user_map.get(responsible_id, ""),
                    ),
                )
                conn.commit()
                stats["leads_synced"] += 1
            except Exception as e:
                conn.rollback()
                raise
            finally:
                cur.close()
        except Exception as e:
            log.error("lead_sync_error", lead_id=lead.get("ID"), error=str(e))
            stats["errors"].append(f"lead {lead.get('ID')}: {e}")

    log.info("sync_bitrix_leads_done", **{k: v for k, v in stats.items() if k != "errors"})
    return stats


def sync_bitrix_contacts(client: Any, conn: Any, contract_field: str) -> dict:
    """
    Sync Bitrix Contacts → bitrix_leads table.
    Contacts with contract number get diffy_lead_id = LEAD-{num}.
    Others get diffy_lead_id = BX-CONTACT-{id}.
    """
    stats = {"contacts_synced": 0, "errors": []}
    select_fields = [
        "ID", "TITLE", "NAME", "LAST_NAME", "PHONE", "EMAIL", "ASSIGNED_BY_ID",
    ]
    if contract_field:
        select_fields.append(contract_field)

    try:
        contacts = client.get_contacts(select=select_fields)
    except Exception as e:
        log.error("bitrix_get_contacts_failed", error=str(e))
        stats["errors"].append(str(e))
        return stats

    user_ids = list({int(c.get("ASSIGNED_BY_ID", 0)) for c in contacts if c.get("ASSIGNED_BY_ID")})
    user_map: dict[int, str] = {}
    if user_ids:
        try:
            user_map = client.get_users(user_ids)
        except Exception as e:
            log.warning("bitrix_users_failed", error=str(e))

    for contact in contacts:
        try:
            contact_id = int(contact["ID"])
            contract_raw = contact.get(contract_field, "") if contract_field else ""
            contract_digits = _extract_contract_number(str(contract_raw) if contract_raw else None)

            if contract_digits:
                diffy_lead_id = contract_digits  # Already in ФФ-XXXX format
                contract_number = contract_digits
            else:
                diffy_lead_id = f"BX-CONTACT-{contact_id}"
                contract_number = None

            responsible_id = int(contact.get("ASSIGNED_BY_ID") or 0)
            name_parts = [contact.get("NAME", ""), contact.get("LAST_NAME", "")]
            full_name = " ".join(p for p in name_parts if p).strip()

            cur = conn.cursor()
            try:
                cur.execute(
                    """
                    INSERT INTO bitrix_leads
                        (bitrix_lead_id, bitrix_entity_type, diffy_lead_id, title, name,
                         phone, email, responsible_id, responsible_name,
                         contract_number, last_synced_at)
                    VALUES (%s, 'contact', %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (bitrix_lead_id) DO UPDATE SET
                        diffy_lead_id    = EXCLUDED.diffy_lead_id,
                        title            = EXCLUDED.title,
                        name             = EXCLUDED.name,
                        phone            = EXCLUDED.phone,
                        email            = EXCLUDED.email,
                        responsible_id   = EXCLUDED.responsible_id,
                        responsible_name = EXCLUDED.responsible_name,
                        contract_number  = EXCLUDED.contract_number,
                        last_synced_at   = NOW()
                    """,
                    (
                        contact_id, diffy_lead_id,
                        contact.get("TITLE", ""), full_name,
                        _extract_phone(contact.get("PHONE")),
                        _extract_email(contact.get("EMAIL")),
                        responsible_id, user_map.get(responsible_id, ""),
                        contract_number,
                    ),
                )
                conn.commit()
                stats["contacts_synced"] += 1
            except Exception as e:
                conn.rollback()
                raise
            finally:
                cur.close()
        except Exception as e:
            log.error("contact_sync_error", contact_id=contact.get("ID"), error=str(e))
            stats["errors"].append(f"contact {contact.get('ID')}: {e}")

    log.info("sync_bitrix_contacts_done", **{k: v for k, v in stats.items() if k != "errors"})
    return stats


def sync_calls(client: Any, conn: Any, leads: list[dict]) -> dict:
    """
    Sync call activities for all leads/contacts → bitrix_calls table.
    After inserting from crm.activity, enriches record_url from voximplant.statistic.
    Calls with a record_url get transcript_status='pending' for Whisper.
    """
    stats = {"calls_synced": 0, "urls_enriched": 0, "errors": []}

    for lead in leads:
        try:
            owner_type = OWNER_TYPE_LEAD if lead["bitrix_entity_type"] == "lead" else OWNER_TYPE_CONTACT
            activities = client.get_activities(
                owner_type_id=owner_type,
                owner_id=lead["bitrix_lead_id"],
                type_id=ACTIVITY_CALL,
            )
            for activity in activities:
                try:
                    activity_id = int(activity["ID"])
                    settings = activity.get("SETTINGS") or {}
                    if isinstance(settings, str):
                        settings = {}
                    duration = (
                        settings.get("DURATION")
                        or settings.get("CALL_DURATION")
                        or activity.get("DURATION")
                    )
                    # Extract call_id for later voximplant enrichment
                    call_id_str = (
                        settings.get("CALL_ID")
                        or settings.get("CALL_UUID")
                        or ""
                    )
                    # Extract phone number from COMMUNICATIONS (more reliable than voximplant)
                    communications = activity.get("COMMUNICATIONS") or []
                    phone_number = ""
                    if communications and len(communications) > 0:
                        comm = communications[0]
                        if comm.get("TYPE") == "PHONE":
                            phone_number = comm.get("VALUE") or ""

                    cur = conn.cursor()
                    try:
                        cur.execute(
                            """
                            INSERT INTO bitrix_calls
                                (bitrix_activity_id, bitrix_call_id, bitrix_lead_id, diffy_lead_id,
                                 direction, phone_number, call_date, responsible_id, responsible_name,
                                 call_duration, transcript_status)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'no_record')
                            ON CONFLICT (bitrix_activity_id) DO UPDATE SET
                                phone_number = EXCLUDED.phone_number
                            """,
                            (
                                activity_id, call_id_str or None,
                                lead["bitrix_lead_id"], lead["diffy_lead_id"],
                                int(activity.get("DIRECTION") or 0),
                                phone_number,
                                _parse_datetime(activity.get("START_TIME")),
                                int(activity.get("RESPONSIBLE_ID") or 0),
                                "",
                                int(duration) if duration else None,
                            ),
                        )
                        conn.commit()
                        stats["calls_synced"] += 1
                    except Exception as e:
                        conn.rollback()
                        raise
                    finally:
                        cur.close()
                except Exception as e:
                    log.error("call_insert_error", activity_id=activity.get("ID"), error=str(e))
                    stats["errors"].append(str(e))

            # Enrich record_url from voximplant.statistic for this lead
            _enrich_call_record_urls(client, conn, lead, stats)

        except Exception as e:
            log.error("calls_lead_error", lead_id=lead.get("bitrix_lead_id"), error=str(e))
            stats["errors"].append(str(e))

    log.info("sync_calls_done", **{k: v for k, v in stats.items() if k != "errors"})
    return stats


def sync_emails(client: Any, conn: Any, leads: list[dict]) -> dict:
    """
    Sync email activities for all leads/contacts → bitrix_emails table.
    Saves full email body (DESCRIPTION field = HTML text).
    """
    stats = {"emails_synced": 0, "errors": []}

    for lead in leads:
        try:
            owner_type = OWNER_TYPE_LEAD if lead["bitrix_entity_type"] == "lead" else OWNER_TYPE_CONTACT
            activities = client.get_activities(
                owner_type_id=owner_type,
                owner_id=lead["bitrix_lead_id"],
                type_id=ACTIVITY_EMAIL,
            )
            for activity in activities:
                try:
                    activity_id = int(activity["ID"])
                    communications = activity.get("COMMUNICATIONS") or []
                    email_from, email_to = _extract_email_addresses(communications)
                    cur = conn.cursor()
                    try:
                        cur.execute(
                            """
                            INSERT INTO bitrix_emails
                                (bitrix_activity_id, bitrix_lead_id, diffy_lead_id,
                                 direction, subject, email_body, email_from, email_to,
                                 email_date, responsible_id)
                            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (bitrix_activity_id) DO NOTHING
                            """,
                            (
                                activity_id, lead["bitrix_lead_id"], lead["diffy_lead_id"],
                                int(activity.get("DIRECTION") or 0),
                                activity.get("SUBJECT", ""),
                                activity.get("DESCRIPTION", ""),  # Full email body HTML
                                email_from, email_to,
                                _parse_datetime(activity.get("START_TIME")),
                                int(activity.get("RESPONSIBLE_ID") or 0),
                            ),
                        )
                        conn.commit()
                        stats["emails_synced"] += 1
                    except Exception as e:
                        conn.rollback()
                        raise
                    finally:
                        cur.close()
                except Exception as e:
                    log.error("email_insert_error", activity_id=activity.get("ID"), error=str(e))
                    stats["errors"].append(str(e))
        except Exception as e:
            log.error("emails_lead_error", lead_id=lead.get("bitrix_lead_id"), error=str(e))
            stats["errors"].append(str(e))

    log.info("sync_emails_done", **{k: v for k, v in stats.items() if k != "errors"})
    return stats


def sync_comments(client: Any, conn: Any, leads: list[dict]) -> dict:
    """
    Sync timeline comments for all leads/contacts → bitrix_comments table.
    """
    stats = {"comments_synced": 0, "errors": []}

    for lead in leads:
        try:
            entity_type_str = "lead" if lead["bitrix_entity_type"] == "lead" else "contact"
            comments = client.get_timeline_comments(
                entity_type=entity_type_str,
                entity_id=lead["bitrix_lead_id"],
            )
            # Batch-resolve author names
            author_ids = list({int(c.get("CREATED_BY", 0)) for c in comments if c.get("CREATED_BY")})
            author_map: dict[int, str] = {}
            if author_ids:
                try:
                    author_map = client.get_users(author_ids)
                except Exception as e:
                    log.warning("comment_users_failed", error=str(e))

            for comment in comments:
                try:
                    comment_id = int(comment["ID"])
                    author_id = int(comment.get("CREATED_BY") or 0)
                    comment_text = comment.get("COMMENT") or comment.get("TEXT") or ""
                    comment_date_raw = comment.get("CREATED") or comment.get("DATE_CREATE")
                    cur = conn.cursor()
                    try:
                        cur.execute(
                            """
                            INSERT INTO bitrix_comments
                                (bitrix_comment_id, bitrix_lead_id, diffy_lead_id,
                                 comment_text, author_id, author_name, comment_date)
                            VALUES (%s, %s, %s, %s, %s, %s, %s)
                            ON CONFLICT (bitrix_comment_id) DO NOTHING
                            """,
                            (
                                comment_id, lead["bitrix_lead_id"], lead["diffy_lead_id"],
                                comment_text, author_id,
                                author_map.get(author_id, ""),
                                _parse_datetime(comment_date_raw),
                            ),
                        )
                        conn.commit()
                        stats["comments_synced"] += 1
                    except Exception as e:
                        conn.rollback()
                        raise
                    finally:
                        cur.close()
                except Exception as e:
                    log.error("comment_insert_error", comment_id=comment.get("ID"), error=str(e))
                    stats["errors"].append(str(e))
        except Exception as e:
            log.error("comments_lead_error", lead_id=lead.get("bitrix_lead_id"), error=str(e))
            stats["errors"].append(str(e))

    log.info("sync_comments_done", **{k: v for k, v in stats.items() if k != "errors"})
    return stats


# ── Wave 4 orchestration ──────────────────────────────────────────────────────

def run_bitrix_sync(
    db: Any,
    llm: Any,
    dify: Any,
    webhook_url: str,
    contract_field: str,
    transcribe_url: str,
) -> dict:
    """
    Main orchestration entry point for daily Bitrix24 sync.
    Called by scheduler at configured hour.

    Steps: leads → contacts → calls → emails → comments → transcribe → summarize
    Each step logs errors and continues on failure.
    """
    from app.integrations.bitrix24 import Bitrix24Client
    from app.tasks.bitrix_summary import generate_bitrix_summaries, transcribe_pending_calls

    log.info("bitrix_sync_started")
    client = Bitrix24Client(webhook_url)
    stats: dict = {
        "leads_synced": 0, "contacts_synced": 0,
        "calls_synced": 0, "emails_synced": 0, "comments_synced": 0,
        "transcribed": 0, "summaries_generated": 0, "errors": [],
    }

    try:
        with db.connection() as conn:
            # Step 1: Sync leads
            try:
                result = sync_bitrix_leads(client, conn)
                stats["leads_synced"] = result.get("leads_synced", 0)
                log.info("leads_synced", count=stats["leads_synced"])
            except Exception as e:
                log.error("leads_sync_failed", error=str(e))
                stats["errors"].append(f"leads: {e}")

            # Step 2: Sync contacts
            try:
                result = sync_bitrix_contacts(client, conn, contract_field)
                stats["contacts_synced"] = result.get("contacts_synced", 0)
                log.info("contacts_synced", count=stats["contacts_synced"])
            except Exception as e:
                log.error("contacts_sync_failed", error=str(e))
                stats["errors"].append(f"contacts: {e}")

            # Step 3: Get all synced leads for activity sync
            leads = db.get_bitrix_leads_for_sync()
            log.info("activity_sync_start", leads_count=len(leads))

            # Steps 4-6: Sync activities
            for sync_fn, key, label in [
                (sync_calls, "calls_synced", "calls"),
                (sync_emails, "emails_synced", "emails"),
                (sync_comments, "comments_synced", "comments"),
            ]:
                try:
                    result = sync_fn(client, conn, leads)
                    stats[key] = result.get(key, 0)
                    log.info(f"{label}_synced", count=stats[key])
                except Exception as e:
                    log.error(f"{label}_sync_failed", error=str(e))
                    stats["errors"].append(f"{label}: {e}")

        # Step 7: Transcribe pending calls (outside conn — separate commits per call)
        try:
            result = transcribe_pending_calls(db, transcribe_url)
            stats["transcribed"] = result.get("transcribed", 0)
            log.info("transcription_done", count=stats["transcribed"])
        except Exception as e:
            log.error("transcription_failed", error=str(e))
            stats["errors"].append(f"transcribe: {e}")

        # Step 8: Generate Claude summaries
        try:
            result = generate_bitrix_summaries(db, llm, dify)
            stats["summaries_generated"] = result.get("summaries_generated", 0)
            log.info("summaries_done", count=stats["summaries_generated"])
        except Exception as e:
            log.error("summaries_failed", error=str(e))
            stats["errors"].append(f"summaries: {e}")

    finally:
        client.close()  # always close HTTP session
    log.info(
        "bitrix_sync_complete",
        **{k: v for k, v in stats.items() if k != "errors"},
        errors=len(stats["errors"]),
    )
    return stats
