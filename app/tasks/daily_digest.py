"""
Daily Digest Generator — replaces n8n WF02 (02-daily-digest.json).

Original WF02 flow:
  1. Cron at 23:00 (was 21:00)
  2. Load today's completed transcripts from processed_files
  3. Load today's client_summaries
  4. Combine context
  5. Send to LLM for digest generation
  6. Build final Telegram message with header + digest + summary links
  7. Send to all bot_chats
  8. Mark transcripts as summary_sent

Based on working test_wf02.py (which correctly uses Anthropic API).
"""
from __future__ import annotations

from datetime import date
from typing import Any

from app.core.db import Database
from app.core.llm import LLMClient
from app.core.logger import get_logger
from app.core.telegram_api import TelegramSender

log = get_logger("daily_digest")

DEFAULT_DIGEST_PROMPT = (
    "Ты бизнес-аналитик. Сформируй ежедневный дайджест по стенограммам встреч.\n\n"
    "ФОРМАТ (строго HTML без Markdown):\n"
    "1) <b>Резюме дня</b> (3-5 предложений)\n"
    "2) <b>Ключевые договорённости</b> (буллеты)\n"
    "3) <b>Action items</b> (буллет, ответственный, срок)\n"
    "4) <b>Риски/блокеры</b> (или Нет)\n"
    "5) По каждому LEAD-ID: 1-2 ключевых пункта\n\n"
    "Максимум 3000 символов. Используй HTML-теги (<b>, <i>), НЕ Markdown."
)


class DailyDigestTask:
    """Generate and send daily summary digest to Telegram."""

    def __init__(
        self,
        db: Database,
        llm: LLMClient,
        telegram: TelegramSender,
        default_chat_id: str = "",
        summaries_base_url: str = "",
    ) -> None:
        self.db = db
        self.llm = llm
        self.telegram = telegram
        self.default_chat_id = default_chat_id
        self.summaries_base_url = summaries_base_url.rstrip("/")

    def run(self, target_date: date | None = None) -> dict[str, Any]:
        """
        Generate and send daily digest.
        Returns stats dict: {'transcripts', 'summaries', 'digest_chars', 'sent_to'}
        """
        d = target_date or date.today()
        today_str = d.isoformat()

        # Step 1: Load data
        transcripts = self.db.get_todays_transcripts(d)
        summaries = self.db.get_todays_summaries(d)

        if not transcripts and not summaries:
            log.info("no_data_for_digest", date=today_str)
            return {"transcripts": 0, "summaries": 0, "digest_chars": 0, "sent_to": 0}

        log.info(
            "digest_data_loaded",
            date=today_str,
            transcripts=len(transcripts),
            summaries=len(summaries),
        )

        # Step 2: Build LLM context
        context = self._build_context(transcripts, summaries)

        # Step 3: Generate digest via LLM
        prompt = self.db.get_prompt("digest_prompt") or DEFAULT_DIGEST_PROMPT
        try:
            digest = self.llm.generate(prompt, context)
        except Exception as e:
            log.error("digest_generation_failed", error=str(e))
            digest = "Ошибка генерации дайджеста."

        # Step 4: Build final Telegram message
        lead_ids = list(set(t["lead_id"] for t in transcripts if t.get("lead_id")))
        message = self._build_message(today_str, transcripts, summaries, lead_ids, digest)

        # Step 5: Send to all registered chats
        sent_to = self._send_to_chats(message)

        # Step 6: Mark as sent
        self.db.mark_summary_sent(d)

        stats = {
            "transcripts": len(transcripts),
            "summaries": len(summaries),
            "digest_chars": len(digest),
            "sent_to": sent_to,
        }
        log.info("digest_sent", **stats)
        return stats

    def _build_context(
        self,
        transcripts: list[dict[str, Any]],
        summaries: list[dict[str, Any]],
    ) -> str:
        """
        Build combined context for LLM.
        Source: test_wf02.py Step 2.
        """
        parts = []

        for t in transcripts:
            lead_id = t.get("lead_id", "?")
            lead_name = t.get("lead_name") or "?"
            text = (t.get("transcript_text") or "")[:800]
            parts.append(
                f'[LEAD-{lead_id} ({lead_name})]\n'
                f'Файл: {t.get("filename", "?")}\n'
                f'Текст: {text}'
            )

        for s in summaries:
            lead_id = s.get("lead_id", "?")
            lead_name = s.get("lead_name") or "?"
            src_type = s.get("source_type", "?")
            text = (s.get("summary_text") or "")[:800]
            parts.append(
                f'[LEAD-{lead_id} ({lead_name}) — Саммари ({src_type})]\n{text}'
            )

        return "\n\n".join(parts)

    def _build_message(
        self,
        today_str: str,
        transcripts: list[dict[str, Any]],
        summaries: list[dict[str, Any]],
        lead_ids: list[str],
        digest: str,
    ) -> str:
        """
        Build final Telegram message with header + digest + links.
        Source: test_wf02.py Steps 4-5.
        """
        header = (
            f"<b>Дайджест за {today_str}</b>\n"
            f"Встреч: {len(transcripts)} | Клиентов: {len(lead_ids)}"
        )

        # Summary links
        links = []
        for s in summaries:
            lead_id = s.get("lead_id", "?")
            src_type = s.get("source_type", "?")
            if self.summaries_base_url:
                link = f"{self.summaries_base_url}/{today_str}/LEAD-{lead_id}_{src_type}_{today_str}.md"
                links.append(f'<a href="{link}">LEAD-{lead_id} ({src_type})</a>')

        message = f"{header}\n\n{digest}"
        if links:
            links_block = "\n".join(f"  {lnk}" for lnk in links)
            message += f"\n\n<b>Саммари:</b>\n{links_block}"

        return message

    def _send_to_chats(self, message: str) -> int:
        """Send digest to all registered chats + default chat."""
        chat_ids: set[str] = set()

        # Registered bot chats
        try:
            db_chats = self.db.get_bot_chats()
            chat_ids.update(db_chats)
        except Exception:
            pass  # bot_chats table might not exist

        # Default chat
        if self.default_chat_id:
            chat_ids.add(self.default_chat_id)

        if not chat_ids:
            log.warning("no_chat_ids_for_digest")
            return 0

        sent = 0
        for chat_id in chat_ids:
            result = self.telegram.send_message_chunked(chat_id, message)
            if result:
                sent += 1

        return sent
