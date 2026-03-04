"""
Deadline Extractor — replaces n8n WF06 (06-deadline-extractor.json).

Original WF06 flow:
  1. Every 15 min (schedule trigger)
  2. Load transcripts where tasks_extracted = false
  3. Send to LLM with extraction prompt
  4. Parse JSON array of tasks
  5. Save each task to extracted_tasks table
  6. Mark file as tasks_extracted = true
  7. Send Telegram notification for each new task

Prompt source: 06-deadline-extractor.json "Prepare Prompt" Code node.
"""
from __future__ import annotations

import json

from app.core.db import Database
from app.core.llm import LLMClient
from app.core.logger import get_logger
from app.core.telegram_api import TelegramSender

log = get_logger("deadline_extractor")

EXTRACTION_PROMPT = (
    "Ты строгий бизнес-ассистент. Твоя задача — извлечь из транскрипта созвона "
    "или чата ВСЕ обещания, задачи и дедлайны.\n\n"
    "ПРАВИЛА:\n"
    '1. Ищи фразы вроде "я сделаю это завтра", "отправлю до пятницы", '
    '"нужно проверить остатки", "поставь задачу на...".\n'
    "2. Если задач и дедлайнов НЕТ, верни строго пустой JSON массив: []\n"
    "3. Если задачи есть, верни JSON массив объектов следующего формата "
    "(и больше никакого текста!):\n"
    "[\n"
    "  {\n"
    '    "task": "Краткая суть задачи (например: Отправить коммерческое предложение)",\n'
    '    "assignee": "Кто должен сделать (например: Евгений, или Клиент, или Неизвестно)",\n'
    '    "deadline": "Упомянутый срок (например: 15 марта, завтра, до конца недели, без срока)",\n'
    '    "context": "Краткий контекст из-за чего возникла задача (1 предложение)"\n'
    "  }\n"
    "]"
)


class DeadlineExtractorTask:
    """Extract tasks and deadlines from meeting transcripts."""

    def __init__(
        self,
        db: Database,
        llm: LLMClient,
        telegram: TelegramSender | None = None,
        notify_chat_id: str = "",
    ) -> None:
        self.db = db
        self.llm = llm
        self.telegram = telegram
        self.notify_chat_id = notify_chat_id

    def run(self) -> dict[str, int]:
        """
        Extract tasks from all unprocessed transcripts.
        Returns dict: {'processed': N, 'tasks_found': M}
        """
        transcripts = self.db.get_untasked_transcripts(limit=5)
        if not transcripts:
            log.debug("no_untasked_transcripts")
            return {"processed": 0, "tasks_found": 0}

        total_tasks = 0
        processed = 0

        for t in transcripts:
            try:
                tasks = self._extract_tasks(t["transcript_text"])
                log.info(
                    "tasks_extracted",
                    file_id=t["id"],
                    lead_id=t["lead_id"],
                    task_count=len(tasks),
                )

                # Save tasks to DB
                if tasks:
                    self.db.save_extracted_tasks(t["lead_id"], t["filename"], tasks)
                    total_tasks += len(tasks)

                    # Send Telegram notifications
                    self._notify_tasks(t["lead_id"], tasks)

                # Mark as extracted (even if no tasks found)
                self.db.mark_tasks_extracted(t["id"])
                processed += 1

            except Exception as e:
                log.error(
                    "task_extraction_failed",
                    file_id=t["id"],
                    lead_id=t["lead_id"],
                    error=str(e),
                )
                # Still mark as extracted to avoid infinite retries on bad transcripts
                try:
                    self.db.mark_tasks_extracted(t["id"])
                except Exception:
                    pass

        log.info("deadline_extraction_complete", processed=processed, tasks_found=total_tasks)
        return {"processed": processed, "tasks_found": total_tasks}

    def _extract_tasks(self, transcript_text: str) -> list[dict[str, str]]:
        """Send transcript to LLM and parse the JSON response."""
        raw_response = self.llm.generate(
            EXTRACTION_PROMPT, transcript_text, max_tokens=1000
        )

        # Parse JSON from response (LLM might wrap in markdown code blocks)
        cleaned = raw_response.strip()
        if cleaned.startswith("```"):
            # Remove markdown code block wrapper
            lines = cleaned.split("\n")
            cleaned = "\n".join(lines[1:-1]) if len(lines) > 2 else cleaned

        try:
            tasks = json.loads(cleaned)
            if not isinstance(tasks, list):
                tasks = [tasks]
            return tasks
        except json.JSONDecodeError:
            # Try to find JSON array in the response
            start = cleaned.find("[")
            end = cleaned.rfind("]")
            if start != -1 and end > start:
                try:
                    tasks = json.loads(cleaned[start : end + 1])
                    if isinstance(tasks, list):
                        return tasks
                except json.JSONDecodeError:
                    pass

            log.warning("task_json_parse_failed", response_preview=cleaned[:200])
            return []

    def _notify_tasks(self, lead_id: str | None, tasks: list[dict[str, str]]) -> None:
        """Send Telegram notification for each extracted task."""
        if not self.telegram or not self.notify_chat_id:
            return

        for task in tasks:
            text = (
                f"<b>Новая задача (LEAD-{lead_id or '?'})</b>\n\n"
                f"<b>Задача:</b> {task.get('task', '?')}\n"
                f"<b>Кто:</b> {task.get('assignee', '?')}\n"
                f"<b>Дедлайн:</b> {task.get('deadline', '?')}\n"
                f"<b>Контекст:</b> {task.get('context', '-')}"
            )
            try:
                self.telegram.send_message(self.notify_chat_id, text)
            except Exception as e:
                log.warning("task_notification_failed", error=str(e))
