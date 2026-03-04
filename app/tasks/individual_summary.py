"""
Individual Summary Generator — replaces n8n WF03 (03-individual-summaries.json).

Original WF03 flow:
  1. Cron at 22:00
  2. Load unprocessed calls from processed_files
  3. Load dataset map from lead_chat_mapping
  4. For each lead: combine transcripts → LLM summary
  5. Save .md file to /summaries/{date}/
  6. Push document to Dify Knowledge Base
  7. Save to client_summaries table

CRITICAL FIX: The original n8n WF03 JSON hardcoded
  https://open.bigmodel.cn/api/paas/v4/chat/completions (OpenAI format)
but the actual LLM is Claude via z.ai (Anthropic format).
This Python implementation uses the correct API from day one.
"""
from __future__ import annotations

import os
from collections import defaultdict
from datetime import date, datetime
from typing import Any

from app.core.db import Database
from app.core.dify_api import DifyClient
from app.core.llm import LLMClient
from app.core.logger import get_logger

log = get_logger("individual_summary")

# Fallback prompts (used if DB prompts table is empty)
DEFAULT_CALL_PROMPT = (
    "Ты бизнес-аналитик. Проанализируй транскрипцию(и) созвона с клиентом.\n"
    "Выдай:\n"
    "1) Краткое резюме (2-3 предл.)\n"
    "2) Участники звонка\n"
    "3) Ключевые договорённости\n"
    "4) Action Items с дедлайнами (если есть)\n"
    "5) Риски/проблемы\n"
    "6) Тон клиента (позитивный/нейтральный/негативный)\n"
    "Формат: Markdown. Не более 1500 слов."
)

DEFAULT_CHAT_PROMPT = (
    "Ты куратор клиентского отдела фулфилмент-компании. "
    "Проанализируй переписку с клиентом в Telegram.\n"
    "Выдай в формате Markdown:\n"
    "## Резюме дня (2-3 предложения)\n"
    "## Вопросы клиента\n"
    "### Решённые\n"
    "### Нерешённые\n"
    "## Action Items для команды\n"
    "## Тон клиента\n"
    "(позитивный / нейтральный / негативный / требует внимания)"
)


class IndividualSummaryTask:
    """Generate per-client summaries from calls and chats."""

    def __init__(
        self,
        db: Database,
        llm: LLMClient,
        dify: DifyClient,
        summaries_dir: str,
        summaries_base_url: str = "",
    ) -> None:
        self.db = db
        self.llm = llm
        self.dify = dify
        self.summaries_dir = summaries_dir
        self.summaries_base_url = summaries_base_url

    def run(self, target_date: date | None = None) -> dict[str, int]:
        """
        Run the full individual summary pipeline.
        Returns dict with counts: {'calls_summarized': N, 'chats_summarized': M}
        """
        d = target_date or date.today()
        stats = {"calls_summarized": 0, "chats_summarized": 0}

        # ── Call summaries ────────────────────────────────────
        stats["calls_summarized"] = self._process_calls(d)

        # ── Chat summaries ────────────────────────────────────
        stats["chats_summarized"] = self._process_chats(d)

        log.info("individual_summary_complete", date=str(d), **stats)
        return stats

    def _process_calls(self, target_date: date) -> int:
        """Process all unprocessed call transcripts."""
        calls = self.db.get_unprocessed_calls(target_date)
        if not calls:
            log.info("no_unprocessed_calls", date=str(target_date))
            return 0

        dataset_map = self.db.get_dataset_map()
        prompt = self.db.get_prompt("call_summary_prompt") or DEFAULT_CALL_PROMPT

        # Group calls by lead_id
        grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for call in calls:
            grouped[call["lead_id"]].append(call)

        summarized = 0
        for lead_id, lead_calls in grouped.items():
            try:
                summarized += self._summarize_lead_calls(
                    lead_id, lead_calls, prompt, dataset_map, target_date
                )
            except Exception as e:
                log.error("call_summary_failed", lead_id=lead_id, error=str(e))

        return summarized

    def _summarize_lead_calls(
        self,
        lead_id: str,
        calls: list[dict[str, Any]],
        prompt: str,
        dataset_map: dict[str, str],
        target_date: date,
    ) -> int:
        """Summarize all calls for a single lead."""
        # Combine transcripts (as in test_wf03.py)
        combined = "\n\n".join(
            f'--- Звонок {i + 1} ({c["filename"]}) ---\n{c["transcript_text"]}'
            for i, c in enumerate(calls)
        )

        # Generate summary via LLM
        summary = self.llm.generate(prompt, combined)
        log.info("call_summary_generated", lead_id=lead_id, calls=len(calls), chars=len(summary))

        # Save .md file
        md_path = self._save_markdown(lead_id, "call", summary, target_date)

        # Push to Dify KB
        dataset_id = dataset_map.get(lead_id, "")
        dify_doc_id = ""
        if dataset_id:
            try:
                today_str = target_date.isoformat()
                doc_name = f"[{today_str}] LEAD-{lead_id} — Созвоны ({len(calls)} шт.)"
                dify_doc_id = self.dify.create_document_by_text(dataset_id, doc_name, summary)
            except Exception as e:
                log.warning("dify_push_failed", lead_id=lead_id, error=str(e))

        # Save to DB
        self.db.save_client_summary(lead_id, "call", summary, target_date, file_path=md_path)
        file_ids = [c["id"] for c in calls]
        self.db.update_dify_doc_id(file_ids, dify_doc_id, summary)

        return 1

    def _process_chats(self, target_date: date) -> int:
        """Process all unprocessed chat conversations."""
        unprocessed = self.db.get_unprocessed_chats(target_date)
        if not unprocessed:
            log.info("no_unprocessed_chats", date=str(target_date))
            return 0

        prompt = self.db.get_prompt("chat_summary_prompt") or DEFAULT_CHAT_PROMPT
        dataset_map = self.db.get_dataset_map()
        summarized = 0

        for item in unprocessed:
            lead_id = item["lead_id"]
            try:
                messages = self.db.get_chat_messages_for_lead(lead_id, target_date)
                if not messages:
                    continue

                # Format chat history
                chat_text = self._format_chat(messages)

                # Generate summary via LLM
                summary = self.llm.generate(prompt, chat_text)
                log.info("chat_summary_generated", lead_id=lead_id, messages=len(messages), chars=len(summary))

                # Save .md file
                md_path = self._save_markdown(lead_id, "chat", summary, target_date)

                # Push to Dify
                dataset_id = dataset_map.get(lead_id, "")
                if dataset_id:
                    try:
                        doc_name = f"[{target_date.isoformat()}] LEAD-{lead_id} — Чат ({len(messages)} сообщ.)"
                        self.dify.create_document_by_text(dataset_id, doc_name, summary)
                    except Exception as e:
                        log.warning("dify_chat_push_failed", lead_id=lead_id, error=str(e))

                # Save to DB
                self.db.save_client_summary(lead_id, "chat", summary, target_date, file_path=md_path)
                summarized += 1

            except Exception as e:
                log.error("chat_summary_failed", lead_id=lead_id, error=str(e))

        return summarized

    def _format_chat(self, messages: list[dict[str, Any]]) -> str:
        """Format chat messages for LLM context."""
        if not messages:
            return ""

        chat_title = messages[0].get("chat_title", "Unknown")
        lines = [f"Чат: {chat_title}\n"]
        for msg in messages:
            dt = msg["date"]
            if hasattr(dt, "strftime"):
                dt_str = dt.strftime("%Y-%m-%d %H:%M")
            else:
                dt_str = str(dt)
            lines.append(f"[{dt_str}] {msg['sender']}: {msg['text']}")

        text = "\n".join(lines)

        # Truncate to 50K chars (LLM context limit)
        if len(text) > 50000:
            text = text[:50000] + "\n...[сообщения обрезаны]"

        return text

    def _save_markdown(
        self,
        lead_id: str,
        source_type: str,
        summary: str,
        target_date: date,
    ) -> str:
        """Save summary as .md file and return the relative path."""
        date_str = target_date.isoformat()
        dir_path = os.path.join(self.summaries_dir, date_str)
        os.makedirs(dir_path, exist_ok=True)

        filename = f"LEAD-{lead_id}_{source_type}_{date_str}.md"
        file_path = os.path.join(dir_path, filename)

        header = (
            f"# Summary: LEAD-{lead_id} | {source_type.upper()} | {date_str}\n\n"
            f"_Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n---\n\n"
        )

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(header + summary)

        log.debug("md_saved", path=file_path)
        return f"{date_str}/{filename}"
