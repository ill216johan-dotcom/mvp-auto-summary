"""
Bitrix24 summary generation — daily Claude AI summaries + Whisper transcription.
Tasks 10 (summaries) and 11 (transcription) from the integration plan.
"""
from __future__ import annotations

import os
import re
import tempfile
from datetime import date, timedelta
from typing import Any

import requests

from app.core.db import Database
from app.core.dify_api import DifyClient
from app.core.llm import LLMClient
from app.core.logger import get_logger

log = get_logger("bitrix_summary")

DIRECTION_IN = 1
DIRECTION_OUT = 2

BITRIX_SUMMARY_SYSTEM = (
    "Ты бизнес-аналитик компании фулфилмент. "
    "Анализируй коммуникации с клиентом и составляй чёткие, структурированные сводки. "
    "Пиши только о фактах из предоставленных данных."
)

BITRIX_SUMMARY_PROMPT = """Проанализируй коммуникации с клиентом {client_label} за {date}.

{content}

Составь сводку в формате Markdown:
## Резюме ({date})
(2-3 предложения о ключевых событиях дня)

## Звонки ({calls_count} шт.)
(ключевые темы, договорённости — если есть транскрипция)

## Письма ({emails_count} шт.)
(о чём переписывались, важные детали из текста писем)

## Комментарии ({comments_count} шт.)
(что отметили сотрудники)

## Следующие шаги
(явные задачи/договорённости или "Не выявлено")

Максимум 1000 слов. Только факты из предоставленных данных."""


def _strip_html(text: str) -> str:
    """Remove HTML tags from email body text."""
    if not text:
        return ""
    cleaned = re.sub(r"<[^>]+>", " ", text)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _extract_ff_number(title: str) -> str:
    """Extract ФФ-NNNN number from Bitrix lead title. Returns e.g. 'ФФ-4405' or ''."""
    if not title:
        return ""
    # Match ФФ-digits (case-insensitive, both ФФ and фф)
    m = re.search(r'[ФфFf][ФфFf]-?(\d+)', title, re.IGNORECASE)
    if m:
        return f'ФФ-{m.group(1)}'
    return ""


def _dir_str(direction: int | None) -> str:
    if direction == DIRECTION_IN:
        return "входящий"
    if direction == DIRECTION_OUT:
        return "исходящий"
    return "неизвестно"


def _build_content(calls: list, emails: list, comments: list) -> str:
    """Format CRM data into human-readable text for Claude."""
    parts: list[str] = []

    if calls:
        lines = [f"ЗВОНКИ ({len(calls)} шт.):"]
        for c in calls:
            dt = str(c.get("date", ""))[:16]
            dur = c.get("duration") or 0
            resp = c.get("responsible", "") or ""
            transcript = c.get("transcript") or ""
            preview = transcript[:200] + ("..." if len(transcript) > 200 else "") if transcript else "нет транскрипции"
            lines.append(f"  - {dt} | {_dir_str(c.get('direction'))} | {dur}с | {resp} | {preview}")
        parts.append("\n".join(lines))

    if emails:
        lines = [f"ПИСЬМА ({len(emails)} шт.):"]
        for e in emails:
            dt = str(e.get("date", ""))[:16]
            subj = e.get("subject", "") or "(без темы)"
            frm = e.get("from", "") or ""
            to = e.get("to", "") or ""
            body = _strip_html(e.get("body", "") or "")
            preview = body[:300] + ("..." if len(body) > 300 else "") if body else ""
            lines.append(f"  - {dt} | {_dir_str(e.get('direction'))} | Тема: {subj} | {frm} → {to}")
            if preview:
                lines.append(f"    Текст: {preview}")
        parts.append("\n".join(lines))

    if comments:
        lines = [f"КОММЕНТАРИИ ({len(comments)} шт.):"]
        for c in comments:
            dt = str(c.get("date", ""))[:16]
            author = c.get("author", "") or ""
            text = (c.get("text", "") or "")[:400]
            lines.append(f"  - {dt} | {author}: {text}")
        parts.append("\n".join(lines))

    return "\n\n".join(parts)


def generate_bitrix_summaries(
    db: Database,
    llm: LLMClient,
    dify: DifyClient,
    target_date: date | None = None,
) -> dict:
    """
    Generate Claude AI summaries for all Bitrix leads with activity data.
    If target_date is None — processes ALL historical data (grouped by date).
    Pushes summaries to Dify KB (auto-creating datasets when needed).
    """
    stats = {"summaries_generated": 0, "leads_processed": 0, "errors": 0, "datasets_created": 0}

    leads = db.get_bitrix_leads_for_sync()
    dataset_map = db.get_bitrix_dataset_map()  # {diffy_lead_id: dify_dataset_id} from bitrix_leads

    for lead in leads:
        diffy_lead_id = lead.get("diffy_lead_id")
        if not diffy_lead_id:
            continue

        stats["leads_processed"] += 1
        try:
            if target_date is not None:
                # Daily mode: single date
                dates_to_process = [target_date]
            else:
                # Historical mode: all unique activity dates for this lead
                dates_to_process = db.get_bitrix_activity_dates(diffy_lead_id)

            if not dates_to_process:
                log.debug("bitrix_summary_no_dates", lead=diffy_lead_id)
                continue

            # Extract ФФ-number from lead title (always, for labeling)
            ff_number = _extract_ff_number(lead.get("title", "") or lead.get("name", ""))

            # Auto-create Dify dataset if missing
            dataset_id = dataset_map.get(diffy_lead_id, "")
            if not dataset_id:
                try:
                    # Contacts (LEAD-* or with ФФ-number) get human-readable name
                    dataset_name = ff_number if ff_number and not diffy_lead_id.startswith("BX-LEAD-") else diffy_lead_id
                    dataset_id = dify.create_dataset(dataset_name)
                    if dataset_id:
                        db.save_bitrix_dataset_mapping(diffy_lead_id, dataset_id)
                        dataset_map[diffy_lead_id] = dataset_id
                        stats["datasets_created"] += 1
                        log.info("bitrix_dataset_created", lead=diffy_lead_id, dataset_id=dataset_id, name=dataset_name)
                except Exception as e:
                    log.warning("bitrix_dataset_create_failed", lead=diffy_lead_id, error=str(e))

            for proc_date in dates_to_process:
                try:
                    data = db.get_bitrix_data_for_summary(diffy_lead_id, proc_date)
                    calls = data.get("calls", [])
                    emails = data.get("emails", [])
                    comments = data.get("comments", [])

                    if not calls and not emails and not comments:
                        log.debug("bitrix_summary_no_data", lead=diffy_lead_id, date=str(proc_date))
                        continue

                    content = _build_content(calls, emails, comments)
                    client_label = ff_number if ff_number else diffy_lead_id
                    prompt = BITRIX_SUMMARY_PROMPT.format(
                        client_label=client_label,
                        date=str(proc_date),
                        content=content,
                        calls_count=len(calls),
                        emails_count=len(emails),
                        comments_count=len(comments),
                    )

                    raw_summary = llm.generate(BITRIX_SUMMARY_SYSTEM, prompt, max_tokens=1500)
                    # Prepend client label header so RAG search finds it by ФФ-number
                    header = f"# Клиент: {client_label}\n"
                    if ff_number:
                        header += f"# Номер договора: {ff_number}\n"
                    summary_text = header + "\n" + raw_summary

                    # Push to Dify KB
                    dify_doc_id = ""
                    if dataset_id:
                        try:
                            doc_name = f"[{proc_date}] {client_label} — Битрикс CRM"
                            dify_doc_id = dify.create_document_by_text(dataset_id, doc_name, summary_text)
                        except Exception as e:
                            log.warning("bitrix_dify_push_failed", lead=diffy_lead_id, date=str(proc_date), error=str(e))

                    # Save to DB
                    db.save_bitrix_summary({
                        "diffy_lead_id": diffy_lead_id,
                        "summary_date": proc_date,
                        "calls_count": len(calls),
                        "emails_count": len(emails),
                        "comments_count": len(comments),
                        "summary_text": summary_text,
                        "dify_doc_id": dify_doc_id,
                    })

                    stats["summaries_generated"] += 1
                    log.info(
                        "bitrix_summary_generated",
                        lead=diffy_lead_id,
                        date=str(proc_date),
                        calls=len(calls),
                        emails=len(emails),
                        comments=len(comments),
                        dify_doc=bool(dify_doc_id),
                    )

                except Exception as e:
                    log.error("bitrix_summary_date_failed", lead=diffy_lead_id, date=str(proc_date), error=str(e))
                    stats["errors"] += 1

        except Exception as e:
            log.error("bitrix_summary_failed", lead=diffy_lead_id, error=str(e))
            stats["errors"] += 1

    log.info("generate_bitrix_summaries_done", **stats)
    return stats


def transcribe_pending_calls(
    db: Database,
    transcribe_url: str,
    limit: int = 20,
) -> dict:
    """
    Download and transcribe call recordings via Whisper service.
    Processes up to `limit` pending calls per run.
    """
    stats = {"transcribed": 0, "failed": 0}
    calls = db.get_calls_pending_transcription()  # already LIMIT 20

    for call in calls:
        tmp_path: str | None = None
        try:
            record_url = call["record_url"]
            log.info("transcribe_downloading", call_id=call["id"], url=record_url[:80])

            # Download recording
            dl_resp = requests.get(record_url, timeout=60, stream=True)
            if dl_resp.status_code in (403, 404):
                log.warning("transcribe_unavailable", call_id=call["id"], status=dl_resp.status_code)
                db.update_call_transcript(call["id"], "", "failed")
                stats["failed"] += 1
                continue

            dl_resp.raise_for_status()

            # Save to temp file
            suffix = ".mp3"
            content_type = dl_resp.headers.get("Content-Type", "")
            if "wav" in content_type:
                suffix = ".wav"
            elif "ogg" in content_type:
                suffix = ".ogg"

            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = tmp.name
                for chunk in dl_resp.iter_content(chunk_size=8192):
                    tmp.write(chunk)

            # Send to Whisper
            asr_url = transcribe_url.rstrip("/") + "/asr"
            with open(tmp_path, "rb") as audio_file:
                upload_resp = requests.post(
                    asr_url,
                    files={"audio_file": (f"audio{suffix}", audio_file, f"audio/{suffix[1:]}")},
                    timeout=300,
                )
            upload_resp.raise_for_status()

            # Extract transcript text
            result_data = upload_resp.json()
            transcript_text = (
                result_data.get("text")
                or result_data.get("result")
                or result_data.get("transcript")
                or ""
            )

            db.update_call_transcript(call["id"], transcript_text, "done")
            stats["transcribed"] += 1
            log.info("transcribe_done", call_id=call["id"], chars=len(transcript_text))

        except Exception as e:
            log.error("transcribe_failed", call_id=call.get("id"), error=str(e))
            try:
                db.update_call_transcript(call["id"], "", "failed")
            except Exception as db_err:
                log.warning("transcribe_status_update_failed", call_id=call.get("id"), error=str(db_err))
            stats["failed"] += 1

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass  # temp file cleanup — best effort

    log.info("transcribe_pending_calls_done", **stats)
    return stats
