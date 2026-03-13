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

LEAD_SUMMARY_SYSTEM = (
    "Ты — старший бизнес-аналитик отдела продаж фулфилмент-оператора. "
    "Твоя задача — анализировать коммуникации с потенциальными клиентами (лидами) "
    "и составлять четкие выжимки, которые помогут менеджерам закрыть сделку. "
    "Пиши структурно, выделяй возражения и потребности."
)

LEAD_SUMMARY_PROMPT = """Проанализируй коммуникации с потенциальным клиентом {client_label} за {date}.

{content}

Составь сводку в формате Markdown строго по структуре ниже. Пиши только факты из предоставленных данных, без общих фраз.

## Статус переговоров ({date})
(2-3 предложения: на каком этапе находится сделка, общий настрой клиента)

## Потребности и Запросы
(какие услуги фулфилмента интересуют клиента, какие объемы/маркетплейсы обсуждались. Если нет данных — не пиши блок)

## Возражения и Сомнения
(если клиент сомневается из-за цены, сроков, условий — выпиши это, если нет — напиши "Не выявлено")

## Детали коммуникаций
(краткая выжимка из звонков ({calls_count} шт.), писем ({emails_count} шт.) и комментариев ({comments_count} шт.), о чем конкретно шла речь)

## Следующие шаги менеджера
(явные задачи или договоренности: отправить КП, перезвонить в среду и т.д. Если нет - "Не выявлено")

Максимум 1000 слов."""


CONTACT_SUMMARY_SYSTEM = (
    "Ты — старший аналитик отдела клиентского сервиса фулфилмент-оператора. "
    "Твоя задача — анализировать коммуникации с действующими клиентами (селлерами) "
    "и составлять четкие операционные сводки для кураторов. "
    "Выделяй проблемы, текущие задачи и недовольства."
)

CONTACT_SUMMARY_PROMPT = """Проанализируй коммуникации с действующим клиентом {client_label} за {date}.

{content}

Составь сводку в формате Markdown строго по структуре ниже. Пиши только факты из предоставленных данных, без общих фраз.

## Главное за день ({date})
(2-3 предложения о ключевых операционных событиях: отгрузки, приемки, общие вопросы)

## Индекс счастья и Проблемы
(есть ли жалобы, недовольство сроками, ошибки склада, или наоборот похвала. ЕСЛИ ПРОБЛЕМ И ЖАЛОБ НЕТ — НИЧЕГО НЕ ПИШИ В ЭТОТ БЛОК)

## Операционные задачи
(какие конкретные задачи обсуждались: маркировка, переупаковка, брак, возвраты и т.д. Если нет данных — не пиши блок)

## 🔄 Открытые вопросы (Длительные кейсы)
(Если обсуждается вопрос, который не решился за один день (например, поиск потерянного товара, долгая сверка актов, перерасчет), выдели его суть в 1 предложение. Начни строку с [Кейс: КРАТКОЕ_НАЗВАНИЕ]. Это поможет связывать историю в будущем. Если таких длительных вопросов нет — не пиши этот блок.)

## Детали коммуникаций
(краткая выжимка из звонков ({calls_count} шт.), писем ({emails_count} шт.) и комментариев сотрудников ({comments_count} шт.))

## Договоренности и Ожидания
(что куратор или склад пообещали сделать для клиента. Если ничего — не пиши блок)

Максимум 1000 слов."""


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
                    is_contact = not diffy_lead_id.startswith("BX-LEAD-")
                    dataset_name = ff_number if ff_number and is_contact else diffy_lead_id
                    
                    # Add tag to description
                    tag = "ДОГОВОР" if is_contact else "ЛИД"
                    description = f"Тип: {tag}"
                    
                    dataset_id = dify.create_dataset(name=dataset_name, description=description)
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
                    
                    is_contact = not diffy_lead_id.startswith("BX-LEAD-")
                    
                    if is_contact:
                        prompt_template = CONTACT_SUMMARY_PROMPT
                        system_prompt = CONTACT_SUMMARY_SYSTEM
                    else:
                        prompt_template = LEAD_SUMMARY_PROMPT
                        system_prompt = LEAD_SUMMARY_SYSTEM

                    prompt = prompt_template.format(
                        client_label=client_label,
                        date=str(proc_date),
                        content=content,
                        calls_count=len(calls),
                        emails_count=len(emails),
                        comments_count=len(comments),
                    )

                    raw_summary = llm.generate(system_prompt, prompt, max_tokens=1500)
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


def _get_audio_suffix(content_type: str) -> str:
    """Determine audio file suffix from Content-Type header."""
    ct = content_type.lower()
    if "wav" in ct:
        return ".wav"
    if "ogg" in ct:
        return ".ogg"
    if "webm" in ct:
        return ".webm"
    return ".mp3"


def _download_via_disk_api(bitrix_client: Any, file_id: int) -> bytes | None:
    """
    Download a call recording from Bitrix24 Disk using RECORD_FILE_ID.
    Uses disk.file.get to get a temporary DOWNLOAD_URL, then fetches the file.
    Returns raw bytes or None on failure.
    """
    download_url = bitrix_client.get_disk_download_url(file_id)
    if not download_url:
        log.warning("disk_download_url_missing", file_id=file_id)
        return None

    try:
        resp = requests.get(download_url, timeout=60, stream=True)
        resp.raise_for_status()
        content_type = resp.headers.get("Content-Type", "")
        # Sanity check: should be audio, not HTML login page
        if "text/html" in content_type:
            log.warning("disk_download_returned_html", file_id=file_id)
            return None
        return resp.content
    except Exception as e:
        log.warning("disk_download_failed", file_id=file_id, error=str(e))
        return None


def transcribe_pending_calls(
    db: Database,
    transcribe_url: str,
    limit: int = 20,
    bitrix_webhook_url: str = "",
    whisper_url: str = "",
) -> dict:
    """
    Download and transcribe call recordings via Whisper service.
    Download priority:
      1. RECORD_FILE_ID → Bitrix Disk API (disk.file.get + DOWNLOAD_URL)
      2. record_url → direct HTTP (legacy MegaPBX, usually fails)
    Processes up to `limit` pending calls per run.
    """
    from app.integrations.bitrix24 import Bitrix24Client

    stats = {"transcribed": 0, "failed": 0, "no_source": 0}
    calls = db.get_calls_pending_transcription(limit=limit)

    # Create Bitrix client once if we have a webhook URL
    bitrix_client: Any = None
    if bitrix_webhook_url:
        try:
            bitrix_client = Bitrix24Client(bitrix_webhook_url)
        except Exception as e:
            log.warning("bitrix_client_init_failed", error=str(e))

    for call in calls:
        tmp_path: str | None = None
        try:
            record_file_id = call.get("record_file_id")
            record_url = call.get("record_url")

            audio_data: bytes | None = None
            suffix = ".mp3"

            # --- Method 1: Bitrix Disk API (preferred) ---
            if record_file_id and bitrix_client:
                log.info("transcribe_via_disk_api", call_id=call["id"], file_id=record_file_id)
                # Get fresh download URL from disk.file.get
                download_url = bitrix_client.get_disk_download_url(int(record_file_id))
                if download_url:
                    try:
                        dl_resp = requests.get(download_url, timeout=60, stream=True)
                        dl_resp.raise_for_status()
                        content_type = dl_resp.headers.get("Content-Type", "")
                        if "text/html" not in content_type:
                            suffix = _get_audio_suffix(content_type)
                            audio_data = dl_resp.content
                            log.info("transcribe_disk_download_ok",
                                     call_id=call["id"], file_id=record_file_id,
                                     size=len(audio_data), content_type=content_type)
                        else:
                            log.warning("transcribe_disk_returned_html",
                                        call_id=call["id"], file_id=record_file_id)
                    except Exception as e:
                        log.warning("transcribe_disk_download_failed",
                                    call_id=call["id"], file_id=record_file_id, error=str(e))

            # --- Method 2: Direct URL fallback (legacy MegaPBX) ---
            if audio_data is None and record_url:
                log.info("transcribe_via_direct_url", call_id=call["id"], url=record_url[:80])
                try:
                    dl_resp = requests.get(record_url, timeout=30, stream=True)
                    if dl_resp.status_code in (403, 404):
                        log.warning("transcribe_url_unavailable",
                                    call_id=call["id"], status=dl_resp.status_code)
                    else:
                        dl_resp.raise_for_status()
                        content_type = dl_resp.headers.get("Content-Type", "")
                        if "text/html" not in content_type:
                            suffix = _get_audio_suffix(content_type)
                            audio_data = dl_resp.content
                except Exception as e:
                    log.warning("transcribe_url_download_failed",
                                call_id=call["id"], error=str(e))

            # --- No audio obtained ---
            if not audio_data:
                log.warning("transcribe_no_audio_source", call_id=call["id"],
                            has_file_id=bool(record_file_id), has_url=bool(record_url))
                db.update_call_transcript(call["id"], "", "failed")
                stats["no_source"] += 1
                continue

            # --- Save to temp file ---
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = tmp.name
                tmp.write(audio_data)

            # --- Send to Whisper (direct /v1/audio/transcriptions) ---
            # Use whisper_url if provided, else try transcribe_url + /v1/audio/transcriptions
            if whisper_url:
                asr_url = whisper_url.rstrip("/") + "/v1/audio/transcriptions"
            else:
                asr_url = transcribe_url.rstrip("/") + "/v1/audio/transcriptions"
            mime = "audio/mpeg" if suffix == ".mp3" else f"audio/{suffix[1:]}"
            with open(tmp_path, "rb") as audio_file:
                upload_resp = requests.post(
                    asr_url,
                    files={"file": (f"audio{suffix}", audio_file, mime)},
                    data={"language": "ru"},
                    timeout=900,  # 15 мин — CPU Whisper медленный, ~1.3x реального времени
                )
            upload_resp.raise_for_status()

            # --- Extract transcript text ---
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
                log.warning("transcribe_status_update_failed",
                            call_id=call.get("id"), error=str(db_err))
            stats["failed"] += 1

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass  # temp file cleanup — best effort

    if bitrix_client:
        try:
            bitrix_client.close()
        except Exception:
            pass

    log.info("transcribe_pending_calls_done", **stats)
    return stats
