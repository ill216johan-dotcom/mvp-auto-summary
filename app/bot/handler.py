"""
Telegram Bot command handler — replaces n8n WF04 (04-telegram-bot.json).

Original WF04 flow:
  1. Poll getUpdates every 30s
  2. Parse command (/report, /status, /rag, /help)
  3. For /report: load transcripts → LLM report → reply
  4. For /status: aggregate DB stats → reply
  5. For /rag: send Dify chatbot link
  6. For /help: send help text

Improvements:
  - python-telegram-bot with long polling (instant response vs 30s delay)
  - Async handlers (non-blocking)
  - Proper error handling per command
"""
from __future__ import annotations

from datetime import date

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from app.core.db import Database
from app.core.llm import LLMClient
from app.core.logger import get_logger

log = get_logger("bot")

DEFAULT_REPORT_PROMPT = (
    "Ты аналитик отдела кураторов фулфилмент-компании. "
    "Тебе дают транскрипты созвонов.\n\n"
    "КУРАТОРЫ: Евгений, Кристина, Анна (основные), "
    "Галина, Дарья (консультанты), Станислав, Андрей (руководители).\n\n"
    "ФОРМАТ ОТЧЁТА (HTML):\n\n"
    "<b>Отчёт за [ДАТА]</b>\n\n"
    "<b>[КУРАТОР]:</b>\n"
    "  Созвонов: N (LEAD-XXXX)\n"
    "  Решённых вопросов: N — кратко\n"
    "  Открытых вопросов: N — кратко\n\n"
    "Максимум 3500 символов."
)


class BotService:
    """Telegram bot with /report, /status, /rag, /help commands."""

    def __init__(
        self,
        token: str,
        db: Database,
        llm: LLMClient,
        dify_chatbot_url: str = "",
        summaries_base_url: str = "",
    ) -> None:
        self.db = db
        self.llm = llm
        self.dify_chatbot_url = dify_chatbot_url
        self.summaries_base_url = summaries_base_url
        self._app = Application.builder().token(token).build()

        # Register command handlers
        self._app.add_handler(CommandHandler("report", self._cmd_report))
        self._app.add_handler(CommandHandler("status", self._cmd_status))
        self._app.add_handler(CommandHandler("rag", self._cmd_rag))
        self._app.add_handler(CommandHandler("help", self._cmd_help))
        self._app.add_handler(CommandHandler("start", self._cmd_help))

    async def _cmd_report(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Generate intermediate report on demand (WF04 /report)."""
        try:
            await update.message.reply_text("Генерирую отчёт...")

            transcripts = self.db.get_todays_transcripts()
            if not transcripts:
                await update.message.reply_text(
                    "Сегодня пока нет обработанных созвонов."
                )
                return

            prompt = self.db.get_prompt("report_prompt") or DEFAULT_REPORT_PROMPT

            # Build context
            context_parts = []
            for t in transcripts:
                lead_id = t.get("lead_id", "?")
                lead_name = t.get("lead_name") or "?"
                curators = t.get("curators") or "не назначен"
                text = (t.get("transcript_text") or "")[:1000]
                context_parts.append(
                    f"[LEAD-{lead_id} ({lead_name}), куратор: {curators}]\n"
                    f"Файл: {t.get('filename', '?')}\n"
                    f"Текст: {text}"
                )
            context = "\n\n".join(context_parts)

            report = self.llm.generate(prompt, context)
            await update.message.reply_text(report, parse_mode="HTML")
            log.info("bot_report_sent", user_id=update.effective_user.id)

        except Exception as e:
            log.error("bot_report_error", error=str(e))
            await update.message.reply_text(f"Ошибка генерации отчёта: {e}")

    async def _cmd_status(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Show system status (WF04 /status)."""
        try:
            stats = self.db.get_system_status()
            leads = self.db.get_lead_info()
            today = date.today().isoformat()

            # Format status
            by_status = stats.get("by_status", {})
            status_line = " | ".join(f"{k}: {v}" for k, v in sorted(by_status.items()))

            leads_lines = []
            for lead in leads:
                active = "+" if lead.get("active") else "-"
                name = lead.get("lead_name") or "?"
                curators = lead.get("curators") or "-"
                leads_lines.append(f"  [{active}] LEAD-{lead['lead_id']} ({name}) — {curators}")
            leads_block = "\n".join(leads_lines) if leads_lines else "  Нет данных"

            text = (
                f"<b>Статус системы</b> ({today})\n\n"
                f"<b>Файлы:</b> {stats.get('total_files', 0)} всего"
                f" | {stats.get('today_files', 0)} сегодня\n"
                f"<b>По статусам:</b> {status_line}\n"
                f"<b>Саммари:</b> {stats.get('total_summaries', 0)}\n"
                f"<b>Задачи:</b> {stats.get('total_tasks', 0)}\n"
                f"<b>Сообщений чата:</b> {stats.get('total_chat_messages', 0)}\n\n"
                f"<b>Клиенты:</b>\n{leads_block}"
            )

            await update.message.reply_text(text, parse_mode="HTML")
            log.info("bot_status_sent", user_id=update.effective_user.id)

        except Exception as e:
            log.error("bot_status_error", error=str(e))
            await update.message.reply_text(f"Ошибка: {e}")

    async def _cmd_rag(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Show Dify chatbot link (WF04 /rag)."""
        if self.dify_chatbot_url:
            text = (
                f'<b>RAG Chatbot:</b>\n'
                f'<a href="{self.dify_chatbot_url}">Открыть Dify Chat</a>\n\n'
                f'Примеры вопросов:\n'
                f'  "Что обсуждали с LEAD-4405?"\n'
                f'  "Какие задачи нужно сделать?"\n'
                f'  "Итоги звонка с клиентом 987"'
            )
        else:
            text = "Dify Chatbot URL не настроен. Обратитесь к администратору."

        await update.message.reply_text(text, parse_mode="HTML")

    async def _cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """Show help text (WF04 /help)."""
        text = (
            "<b>MVP Auto-Summary Bot</b>\n\n"
            "/report — Промежуточный отчёт по сегодняшним созвонам\n"
            "/status — Статус системы и список клиентов\n"
            "/rag — Ссылка на AI-чатбот (история по клиентам)\n"
            "/help — Эта справка\n\n"
            "<i>Ежедневный дайджест приходит автоматически в 23:00</i>"
        )
        await update.message.reply_text(text, parse_mode="HTML")

    def start_polling(self) -> None:
        """Start bot with long polling (blocking call)."""
        log.info("bot_starting")
        self._app.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

    async def start_polling_async(self) -> None:
        """Start bot polling in async context (for integration with scheduler)."""
        log.info("bot_starting_async")
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
        )

    async def stop_async(self) -> None:
        """Stop bot gracefully."""
        log.info("bot_stopping")
        await self._app.updater.stop()
        await self._app.stop()
        await self._app.shutdown()
