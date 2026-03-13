"""
Batch enrichment script: populate RECORD_FILE_ID for all existing bitrix_calls
by matching voximplant.statistic.get records to DB rows by lead_id + date.

Run inside the container:
    docker cp scripts/batch_enrich_recordings.py mvp-auto-summary-orchestrator-1:/tmp/
    docker exec mvp-auto-summary-orchestrator-1 python3 /tmp/batch_enrich_recordings.py
"""
from __future__ import annotations

import os
import sys
import time
from datetime import datetime, timedelta, timezone

sys.path.insert(0, "/app")

import psycopg2
import psycopg2.extras
import requests

BITRIX_WEBHOOK = os.environ.get(
    "BITRIX_WEBHOOK_URL",
    "https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/",
)
DB_DSN = (
    f"host={os.environ.get('POSTGRES_HOST','postgres')} "
    f"port={os.environ.get('POSTGRES_PORT','5432')} "
    f"dbname={os.environ.get('POSTGRES_DB','n8n')} "
    f"user={os.environ.get('POSTGRES_USER','n8n')} "
    f"password={os.environ.get('POSTGRES_PASSWORD','')}"
)


def bitrix_post(method: str, params: dict) -> dict:
    url = BITRIX_WEBHOOK.rstrip("/") + "/" + method
    resp = requests.post(url, json=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def fetch_vox_for_lead(lead_id: int) -> list[dict]:
    """Fetch all voximplant records for a specific lead with recordings."""
    all_records: list[dict] = []
    start = 0
    while True:
        try:
            result = bitrix_post("voximplant.statistic.get", {
                "FILTER": {
                    "CRM_ENTITY_ID": str(lead_id),
                    "CALL_RECORD_URL": "%",
                },
                "SELECT": [
                    "CALL_ID", "RECORD_FILE_ID", "CALL_RECORD_URL",
                    "PHONE_NUMBER", "CALL_START_DATE", "CALL_DURATION",
                    "CRM_ENTITY_ID", "CRM_ENTITY_TYPE",
                ],
                "START": start,
            })
        except Exception as e:
            print(f"    voximplant API error for lead {lead_id}: {e}")
            break

        items = result.get("result", [])
        all_records.extend(items)
        total = result.get("total", 0)
        if len(all_records) >= total or not items:
            break
        start += 50
        time.sleep(0.2)
    return all_records


def main():
    print("Connecting to DB...")
    conn = psycopg2.connect(DB_DSN)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Stats
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(record_file_id) as with_file_id,
            COUNT(record_url) as with_url,
            COUNT(CASE WHEN transcript_status='no_record' THEN 1 END) as no_record,
            COUNT(CASE WHEN transcript_status='pending' THEN 1 END) as pending,
            COUNT(CASE WHEN transcript_status='done' THEN 1 END) as done
        FROM bitrix_calls
    """)
    row = cur.fetchone()
    print(f"Before enrichment:")
    print(f"  total={row['total']}, with_file_id={row['with_file_id']}, with_url={row['with_url']}")
    print(f"  no_record={row['no_record']}, pending={row['pending']}, done={row['done']}")

    # Get distinct lead_ids that have calls without recordings
    cur.execute("""
        SELECT DISTINCT bitrix_lead_id, COUNT(*) as call_count
        FROM bitrix_calls
        WHERE transcript_status = 'no_record'
          AND bitrix_lead_id IS NOT NULL
        GROUP BY bitrix_lead_id
        ORDER BY call_count DESC
        LIMIT 5000
    """)
    leads_to_process = cur.fetchall()
    print(f"\nLeads with unrecorded calls: {len(leads_to_process)}")

    enriched_total = 0
    leads_processed = 0

    for lead_row in leads_to_process:
        lead_id = lead_row['bitrix_lead_id']
        leads_processed += 1

        if leads_processed % 50 == 0:
            print(f"  Progress: {leads_processed}/{len(leads_to_process)} leads, enriched={enriched_total}")

        try:
            vox_records = fetch_vox_for_lead(lead_id)
            if not vox_records:
                continue
        except Exception as e:
            print(f"  Error fetching lead {lead_id}: {e}")
            continue

        # Build a map: call_date (minute precision) -> vox record
        vox_by_minute: dict[str, dict] = {}
        for rec in vox_records:
            file_id = rec.get("RECORD_FILE_ID")
            if not file_id:
                continue
            start_str = rec.get("CALL_START_DATE", "")
            if not start_str:
                continue
            try:
                dt = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
                minute_key = dt.strftime("%Y-%m-%dT%H:%M")
                vox_by_minute[minute_key] = rec
            except Exception:
                pass

        if not vox_by_minute:
            continue

        # Get DB calls for this lead without recording
        cur.execute("""
            SELECT id, call_date
            FROM bitrix_calls
            WHERE bitrix_lead_id = %s
              AND transcript_status = 'no_record'
              AND record_file_id IS NULL
        """, (lead_id,))
        db_calls = cur.fetchall()

        for db_call in db_calls:
            call_date = db_call['call_date']
            if not call_date:
                continue

            if call_date.tzinfo is None:
                call_date = call_date.replace(tzinfo=timezone.utc)

            # Try +-5 minute window to account for timezone/clock differences
            matched_rec = None
            for delta in [0, 1, -1, 2, -2, 3, -3, 5, -5]:
                candidate = call_date + timedelta(minutes=delta)
                minute_key = candidate.strftime("%Y-%m-%dT%H:%M")
                if minute_key in vox_by_minute:
                    matched_rec = vox_by_minute[minute_key]
                    break

            if not matched_rec:
                continue

            record_file_id = matched_rec.get("RECORD_FILE_ID")
            record_url = matched_rec.get("CALL_RECORD_URL") or matched_rec.get("SRC_URL") or ""
            call_id_str = matched_rec.get("CALL_ID", "")

            try:
                update_cur = conn.cursor()
                update_cur.execute(
                    """
                    UPDATE bitrix_calls
                    SET record_file_id = %s,
                        bitrix_call_id = COALESCE(NULLIF(bitrix_call_id, ''), %s),
                        record_url = COALESCE(record_url, NULLIF(%s, '')),
                        transcript_status = 'pending'
                    WHERE id = %s AND transcript_status = 'no_record'
                    """,
                    (int(record_file_id), call_id_str or None, record_url, db_call['id']),
                )
                conn.commit()
                if update_cur.rowcount > 0:
                    enriched_total += 1
                update_cur.close()
            except Exception as e:
                conn.rollback()
                print(f"    DB update error for call id={db_call['id']}: {e}")

        time.sleep(0.1)

    # Final stats
    cur.execute("""
        SELECT
            COUNT(*) as total,
            COUNT(record_file_id) as with_file_id,
            COUNT(CASE WHEN transcript_status='pending' THEN 1 END) as pending,
            COUNT(CASE WHEN transcript_status='done' THEN 1 END) as done
        FROM bitrix_calls
    """)
    row = cur.fetchone()
    print(f"\nAfter enrichment:")
    print(f"  with_file_id={row['with_file_id']}, pending={row['pending']}, done={row['done']}")
    print(f"\nTotal enriched this run: {enriched_total}")
    conn.close()


if __name__ == "__main__":
    main()
