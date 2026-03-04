# Plan: Restructuring MVP Auto-Summary Without n8n

> **Date:** 2026-03-04
> **Author:** Architecture Analysis
> **Status:** IMPLEMENTED (Phases 0-4 complete, Phase 5 pending deployment)
> **Goal:** Replace n8n with a native Python orchestrator for stability, maintainability, and elimination of known bugs

---

## 0. IMPLEMENTATION STATUS

| Phase | Description | Status | Files Created |
|-------|-------------|--------|---------------|
| **Phase 0** | Project structure + config | DONE | `app/__init__.py`, `app/config.py`, `requirements.txt`, `tests/conftest.py` |
| **Phase 1** | Core modules | DONE | `app/core/db.py`, `app/core/llm.py`, `app/core/telegram_api.py`, `app/core/dify_api.py`, `app/core/logger.py` |
| **Phase 2** | Task implementations | DONE | `app/tasks/scan_recordings.py` (WF01), `app/tasks/individual_summary.py` (WF03), `app/tasks/deadline_extractor.py` (WF06), `app/tasks/daily_digest.py` (WF02), `app/bot/handler.py` (WF04) |
| **Phase 3** | Scheduler + entry point | DONE | `app/scheduler.py`, `app/main.py` |
| **Phase 4** | Docker infrastructure | DONE | `Dockerfile`, `docker-compose.yml` (updated), `.env.example` (updated) |
| **Phase 5** | Migration + verification | PENDING | Deploy to server, parallel run, verify, remove n8n |

### Key Design Decisions
- n8n moved to `profiles: [legacy]` in docker-compose.yml (safe migration)
- Default STT_PROVIDER changed from `speechkit` to `whisper` (matches actual deployment)
- WHISPER_URL default changed from `http://whisper:9000` to `http://whisper:8000` (correct port)
- All env vars keep backward-compatible names (GLM4_* aliases in config.py)

### How to Deploy
```bash
# Build and start orchestrator (n8n stays dormant unless --profile legacy)
docker compose build orchestrator
docker compose up -d orchestrator

# To run n8n alongside for verification:
docker compose --profile legacy up -d n8n

# After verification, remove n8n permanently:
docker compose --profile legacy stop n8n
docker volume rm mvp-autosummary_n8n_data
```

---

## 1. WHY REMOVE n8n

### 1.1 Current Problems

| Problem | Severity | Details |
|---------|----------|---------|
| **API format mismatch** | CRITICAL | WF03 JSON hardcodes `open.bigmodel.cn` (OpenAI format), but actual LLM is Claude via z.ai (Anthropic format). WF03 **does not work** as defined. |
| **Fragile workflow editing** | HIGH | Changing a prompt or API URL requires either JSON surgery, n8n UI clicks, or direct DB manipulation (`workflow_entity` table). No version control. |
| **Credential sprawl** | HIGH | API keys are hardcoded in: gen_wf*.py, test_wf*.py, docs/SPECS.md, combine_client_data.py. n8n adds its own credential layer on top. |
| **Duplicate logic** | HIGH | Business logic exists in both n8n Code nodes (JavaScript) AND standalone Python scripts. Two codebases to maintain. |
| **Race condition in WF01** | MEDIUM | 10 retries x 60s is insufficient for Whisper medium on CPU. n8n polling model is rigid. |
| **No proper error handling** | MEDIUM | n8n error workflow (WF00) only sends alerts but doesn't retry intelligently. |
| **Heavy resource usage** | MEDIUM | n8n container + its own Node.js runtime + n8n PostgreSQL tables. Extra 200-500MB RAM. |
| **No local dev/testing** | MEDIUM | Cannot run workflows locally without a full n8n instance. Python scripts CAN be tested locally. |
| **Black-box orchestration** | LOW | Non-developers cannot understand or debug JSON workflows. n8n UI is actually harder than reading Python. |

### 1.2 What We Gain

1. **Single language** (Python) for all business logic
2. **Version-controlled code** instead of JSON blobs in n8n DB
3. **Proper testing** with pytest, mocks, CI/CD
4. **Correct LLM integration** -- Python scripts already use the right Anthropic API
5. **Simpler Docker stack** -- remove n8n container entirely
6. **Better error handling** with retries, backoff, structured logging
7. **Easier onboarding** -- one `requirements.txt`, one project structure

### 1.3 Risk Assessment

| Risk | Mitigation |
|------|------------|
| Downtime during migration | Run both systems in parallel; n8n stays active until Python pipeline is verified |
| Loss of n8n UI monitoring | Replace with simple logging + Telegram alerts + /status command |
| Prompts stored in n8n Code nodes | Already migrated to `prompts` DB table -- Python reads from there |
| Telegram bot webhook | python-telegram-bot library handles this natively |

---

## 2. CURRENT ARCHITECTURE vs. TARGET ARCHITECTURE

### 2.1 Current (n8n-based)

```
[Jitsi/Jibri] -> /mnt/recordings/
                       |
              [n8n WF01: cron 5m]     <- JavaScript + HTTP nodes
              [n8n WF03: cron 22:00]  <- JavaScript + HTTP nodes + broken API
              [n8n WF06: cron 22:30]  <- JavaScript + HTTP nodes
              [n8n WF02: cron 23:00]  <- JavaScript + HTTP nodes
              [n8n WF04: polling 30s] <- JavaScript + HTTP nodes
                       |
              [PostgreSQL] + [Dify] + [Telegram] + [Nginx]
```

### 2.2 Target (Python-based)

```
[Jitsi/Jibri] -> /mnt/recordings/
                       |
              [Python Orchestrator]   <- APScheduler + watchdog
              |   scheduler.py        <- cron jobs definition
              |   watcher.py          <- file system watcher (replaces WF01 polling)
              |   tasks/
              |   |   scan_recordings.py    <- WF01 logic
              |   |   individual_summary.py <- WF03 logic
              |   |   deadline_extractor.py <- WF06 logic
              |   |   daily_digest.py       <- WF02 logic
              |   |   telegram_bot.py       <- WF04 logic (python-telegram-bot)
              |   core/
              |   |   db.py                 <- PostgreSQL connection pool
              |   |   llm.py               <- Anthropic API client (unified)
              |   |   telegram.py           <- Telegram API helpers
              |   |   dify.py              <- Dify API client
              |   |   config.py            <- .env loading, settings
              |   |   logging_setup.py     <- structured logging
              |
              [transcribe service]    <- UNCHANGED (already Python, independent)
              [PostgreSQL]            <- UNCHANGED
              [Dify]                  <- UNCHANGED
              [Whisper]               <- UNCHANGED
              [Nginx summaries]       <- UNCHANGED
```

---

## 3. DETAILED MIGRATION PLAN

### Phase 0: Preparation (1-2 days)

#### 0.1 Create project structure
```
app/
  __init__.py
  config.py          # Pydantic Settings, loads .env
  main.py            # Entry point: starts scheduler + bot + watcher
  core/
    __init__.py
    db.py             # psycopg2 connection pool (or asyncpg)
    llm.py            # Anthropic Messages API client
    telegram_api.py   # Telegram Bot API helpers (sendMessage, getUpdates)
    dify_api.py       # Dify Knowledge Base API client
    logger.py         # Structured logging with rotation
  tasks/
    __init__.py
    scan_recordings.py      # WF01
    individual_summary.py   # WF03
    deadline_extractor.py   # WF06
    daily_digest.py         # WF02
  bot/
    __init__.py
    handler.py              # WF04: Telegram bot command handlers
    commands.py             # /report, /status, /rag, /help logic
  scheduler.py              # APScheduler job definitions
  watcher.py                # watchdog FileSystemEventHandler

requirements.txt
Dockerfile
tests/
  test_llm.py
  test_digest.py
  test_scan.py
  conftest.py
```

#### 0.2 Create `requirements.txt`
```
psycopg2-binary==2.9.9
httpx>=0.27.0            # async HTTP client (replaces urllib.request)
apscheduler>=3.10.4      # cron-like scheduler
python-telegram-bot>=21.0  # Telegram bot framework
watchdog>=4.0.0          # file system watcher
pydantic-settings>=2.0   # typed config from .env
python-dotenv>=1.0.0
structlog>=24.0.0        # structured logging
tenacity>=8.2.0          # retry with backoff
```

#### 0.3 Create `app/config.py`
Centralized, typed configuration from `.env`:
```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    # Database
    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str = "n8n"
    postgres_user: str = "n8n"
    postgres_password: str

    # LLM (Claude via z.ai)
    llm_api_key: str          # was GLM4_API_KEY
    llm_base_url: str = "https://api.z.ai/api/anthropic"
    llm_model: str = "claude-3-5-haiku-20241022"

    # Telegram
    telegram_bot_token: str
    telegram_chat_id: str

    # Dify
    dify_api_key: str
    dify_base_url: str = "http://84.252.100.93:8080"
    dify_chatbot_url: str = ""

    # STT
    transcribe_url: str = "http://transcribe:9001"

    # Paths
    recordings_dir: str = "/recordings"
    summaries_dir: str = "/summaries"
    summaries_base_url: str = "http://84.252.100.93:8181"

    # Schedule (Moscow time)
    timezone: str = "Europe/Moscow"
    scan_interval_minutes: int = 5
    individual_summary_hour: int = 22    # WF03
    deadline_extractor_hour: int = 22    # WF06
    deadline_extractor_minute: int = 30
    daily_digest_hour: int = 23          # WF02

    class Config:
        env_file = ".env"
        extra = "ignore"
```

**Key improvement**: Variable names now make sense (`llm_api_key` instead of `GLM4_API_KEY`). Old env var names supported via `Field(alias=...)` for backward compatibility.

---

### Phase 1: Core Modules (2-3 days)

#### 1.1 `app/core/db.py` -- Database Layer

Replace all raw `psycopg2.connect()` calls scattered across scripts with a connection pool:

```python
import psycopg2
from psycopg2 import pool
from contextlib import contextmanager

class Database:
    def __init__(self, dsn: str, min_conn=2, max_conn=10):
        self._pool = pool.ThreadedConnectionPool(min_conn, max_conn, dsn)

    @contextmanager
    def connection(self):
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    @contextmanager
    def cursor(self):
        with self.connection() as conn:
            cur = conn.cursor()
            try:
                yield cur
            finally:
                cur.close()
```

**Queries to implement** (extracted from n8n workflow nodes and test scripts):

| Method | Source | SQL |
|--------|--------|-----|
| `get_new_recordings()` | WF01 | `find` command -> `SELECT ... FROM processed_files WHERE filename = %s` (idempotency check) |
| `insert_recording(filename, filepath, lead_id, file_date)` | WF01 | `INSERT INTO processed_files ...` |
| `update_recording_status(filename, status, transcript?)` | WF01/transcribe | `UPDATE processed_files SET status=%s ...` |
| `get_todays_transcripts()` | WF02 | `SELECT ... FROM processed_files WHERE file_date = CURRENT_DATE AND status = 'completed'` |
| `get_todays_summaries()` | WF02 | `SELECT ... FROM client_summaries WHERE summary_date = CURRENT_DATE` |
| `get_unprocessed_calls()` | WF03 | `SELECT ... WHERE status = 'completed' AND dify_doc_id IS NULL` |
| `get_dataset_map()` | WF03 | `SELECT lead_id, dify_dataset_id FROM lead_chat_mapping WHERE active = true` |
| `save_client_summary(lead_id, source_type, summary_text, date)` | WF03 | `INSERT INTO client_summaries ...` |
| `get_untasked_transcripts()` | WF06 | `SELECT ... WHERE tasks_extracted = false AND transcript_text IS NOT NULL` |
| `save_extracted_tasks(tasks)` | WF06 | `INSERT INTO extracted_tasks ...` |
| `mark_summary_sent(lead_id, date)` | WF02 | `UPDATE processed_files SET summary_sent = true ...` |
| `get_prompt(name)` | WF02/03 | `SELECT prompt_text FROM prompts WHERE name = %s AND is_active = true` |
| `get_bot_chats()` | WF02 | `SELECT chat_id FROM bot_chats` |
| `get_lead_info()` | WF04 | `SELECT * FROM lead_chat_mapping` |
| `get_system_status()` | WF04 | Aggregate query across tables |

#### 1.2 `app/core/llm.py` -- LLM Client (Anthropic API)

**Single, correct implementation** replacing all the broken/inconsistent API calls:

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

class LLMClient:
    def __init__(self, api_key: str, base_url: str, model: str):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.client = httpx.Client(timeout=120.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30))
    def generate(self, system_prompt: str, user_content: str, max_tokens: int = 2000) -> str:
        """Call Claude via z.ai Anthropic Messages API."""
        response = self.client.post(
            f"{self.base_url}/v1/messages",
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_content}],
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()
        return "\n".join(
            block["text"]
            for block in data.get("content", [])
            if block.get("type") == "text"
        ).strip()
```

**Key improvements over current state:**
- Automatic retry with exponential backoff (3 attempts)
- Always uses correct Anthropic format (fixes WF03 bug)
- HTTP connection reuse via httpx.Client
- Proper error propagation

#### 1.3 `app/core/telegram_api.py` -- Telegram Helpers

```python
class TelegramClient:
    def send_message(self, chat_id, text, parse_mode="HTML"): ...
    def send_message_chunked(self, chat_id, text, max_len=4096): ...
    def get_updates(self, offset=None, timeout=30): ...
```

#### 1.4 `app/core/dify_api.py` -- Dify Knowledge Base Client

```python
class DifyClient:
    def create_document(self, dataset_id, name, text): ...
    def update_document(self, dataset_id, doc_id, text): ...
    def search(self, dataset_id, query): ...
```

---

### Phase 2: Task Implementations (3-5 days)

#### 2.1 `app/tasks/scan_recordings.py` -- Replaces WF01

**Current n8n WF01 logic** (from `01-new-recording.json`, ~705 lines of JSON):
1. Cron every 5 min
2. `find /recordings -name "*.webm" -o -name "*.mp4" -o -name "*.wav"` (Execute Command node)
3. Parse filename -> extract LEAD_ID (Code node, JS)
4. Check if already in `processed_files` (Postgres node)
5. If new: INSERT into `processed_files` with status='new'
6. POST to `http://transcribe:9001/` with `{filepath, filename}`
7. Poll `POST /check` 10 times with 60s delay
8. If transcript found: mark `completed`; else: mark `error`

**Python replacement:**

```python
import os, re
from datetime import date

class RecordingScanner:
    def __init__(self, db, transcribe_url, recordings_dir):
        self.db = db
        self.transcribe_url = transcribe_url
        self.recordings_dir = recordings_dir

    def scan(self):
        """Scan /recordings for new audio files and start transcription."""
        extensions = ('.webm', '.mp4', '.wav', '.mp3', '.m4a')
        for root, dirs, files in os.walk(self.recordings_dir):
            for filename in files:
                if not filename.lower().endswith(extensions):
                    continue
                filepath = os.path.join(root, filename)
                if self.db.is_file_processed(filename):
                    continue
                lead_id = self._extract_lead_id(filename)
                file_date = self._extract_date(filename, filepath)
                file_size = os.path.getsize(filepath)
                self.db.insert_recording(filename, filepath, lead_id, file_date, file_size)
                self._start_transcription(filepath, filename)

    def check_pending(self):
        """Check transcription status for files still 'transcribing'."""
        pending = self.db.get_transcribing_files()
        for record in pending:
            result = httpx.post(
                f"{self.transcribe_url}/check",
                json={"filename": record.filename}
            ).json()
            if result.get("transcript"):
                self.db.update_recording_status(
                    record.filename, "completed", result["transcript"]
                )
            elif result.get("status") == "error":
                self.db.update_recording_status(record.filename, "error")
            # else: still processing, do nothing

    def _extract_lead_id(self, filename):
        match = re.search(r'(\d{3,5})[-_]', filename)
        return match.group(1) if match else None

    def _start_transcription(self, filepath, filename):
        """POST to transcribe service (non-blocking)."""
        httpx.post(self.transcribe_url, json={"filepath": filepath, "filename": filename})
```

**Key improvement over n8n WF01:**
- No fixed retry count -- `check_pending()` runs every 5 min and keeps checking
- Eliminates the race condition: files in `transcribing` status are rechecked indefinitely
- Uses `os.walk()` instead of shell `find` command
- Proper LEAD_ID extraction in Python, not JavaScript

#### 2.2 `app/tasks/individual_summary.py` -- Replaces WF03

**Current n8n WF03 logic** (broken -- uses wrong API endpoint):
1. Cron at 22:00
2. Load today's completed calls from `processed_files` where `dify_doc_id IS NULL`
3. Load dataset map from `lead_chat_mapping`
4. For each lead: combine transcripts -> send to LLM -> get summary
5. Save .md file to `/summaries/{date}/`
6. Push document to Dify KB
7. Save to `client_summaries` table
8. Update `processed_files.dify_doc_id`

**Python replacement** (based on working `test_wf03.py`):

```python
class IndividualSummaryTask:
    def __init__(self, db, llm, dify, summaries_dir):
        self.db = db
        self.llm = llm
        self.dify = dify
        self.summaries_dir = summaries_dir

    def run(self):
        calls = self.db.get_unprocessed_calls()
        dataset_map = self.db.get_dataset_map()
        prompt = self.db.get_prompt("call_summary_prompt")

        grouped = self._group_by_lead(calls)
        for lead_id, lead_calls in grouped.items():
            try:
                combined_text = self._combine_transcripts(lead_calls)
                summary = self.llm.generate(prompt, combined_text)
                md_path = self._save_markdown(lead_id, summary)
                doc_id = self._push_to_dify(lead_id, summary, dataset_map)
                self.db.save_client_summary(lead_id, "call", summary, date.today())
                self.db.update_dify_doc_id(lead_calls, doc_id, summary)
                log.info("summary_generated", lead_id=lead_id, chars=len(summary))
            except Exception as e:
                log.error("summary_failed", lead_id=lead_id, error=str(e))
```

**Similarly for chat summaries** -- load from `chat_messages`, use `chat_summary_prompt`.

#### 2.3 `app/tasks/daily_digest.py` -- Replaces WF02

**Python replacement** (based on working `test_wf02.py`):

```python
class DailyDigestTask:
    def __init__(self, db, llm, telegram):
        self.db = db
        self.llm = llm
        self.telegram = telegram

    def run(self):
        transcripts = self.db.get_todays_transcripts()
        summaries = self.db.get_todays_summaries()
        if not transcripts and not summaries:
            log.info("no_data_today")
            return

        prompt = self.db.get_prompt("digest_prompt")
        context = self._build_context(transcripts, summaries)
        digest = self.llm.generate(prompt, context)
        message = self._format_message(digest, transcripts, summaries)

        # Send to all registered chats
        chat_ids = self.db.get_bot_chats()
        for chat_id in chat_ids:
            self.telegram.send_message_chunked(chat_id, message)

        self.db.mark_summary_sent(date.today())
```

#### 2.4 `app/tasks/deadline_extractor.py` -- Replaces WF06

```python
class DeadlineExtractorTask:
    def __init__(self, db, llm):
        self.db = db
        self.llm = llm

    def run(self):
        transcripts = self.db.get_untasked_transcripts()
        for t in transcripts:
            try:
                prompt = "Extract tasks, deadlines, and assignees from this meeting transcript. Return JSON array."
                result = self.llm.generate(prompt, t.transcript_text)
                tasks = json.loads(result)
                self.db.save_extracted_tasks(t.lead_id, t.filename, tasks)
                self.db.mark_tasks_extracted(t.id)
            except Exception as e:
                log.error("deadline_extraction_failed", file_id=t.id, error=str(e))
```

#### 2.5 `app/bot/handler.py` -- Replaces WF04

**Current WF04** uses n8n polling (getUpdates every 30s) with JavaScript Code nodes.

**Python replacement using python-telegram-bot:**

```python
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

class BotService:
    def __init__(self, token, db, llm):
        self.db = db
        self.llm = llm
        self.app = Application.builder().token(token).build()
        self.app.add_handler(CommandHandler("report", self.cmd_report))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("rag", self.cmd_rag))
        self.app.add_handler(CommandHandler("help", self.cmd_help))

    async def cmd_report(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        """Generate intermediate report on demand."""
        transcripts = self.db.get_todays_transcripts()
        prompt = self.db.get_prompt("report_prompt")
        context = self._build_report_context(transcripts)
        report = self.llm.generate(prompt, context)
        await update.message.reply_text(report, parse_mode="HTML")

    async def cmd_status(self, update, ctx):
        """Show system status."""
        stats = self.db.get_system_status()
        leads = self.db.get_lead_info()
        text = self._format_status(stats, leads)
        await update.message.reply_text(text, parse_mode="HTML")

    async def cmd_rag(self, update, ctx):
        """Show Dify chatbot link."""
        await update.message.reply_text(
            "<b>RAG Chatbot:</b>\n"
            f"<a href=\"{settings.dify_chatbot_url}\">Open Dify Chat</a>\n\n"
            "Ask questions like:\n"
            "- What was discussed with LEAD-4405?\n"
            "- What tasks are pending?",
            parse_mode="HTML"
        )

    async def cmd_help(self, update, ctx):
        await update.message.reply_text(
            "/report - Intermediate report\n"
            "/status - System status\n"
            "/rag - Open AI chatbot\n"
            "/help - This message"
        )

    def start(self):
        """Start polling (long-poll, not 30s interval)."""
        self.app.run_polling()
```

**Key improvement:** python-telegram-bot uses long polling (efficient, instant response) instead of n8n's 30-second interval polling.

---

### Phase 3: Scheduler & Entry Point (1 day)

#### 3.1 `app/scheduler.py`

```python
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger

def create_scheduler(config, db, llm, telegram, dify) -> BackgroundScheduler:
    scheduler = BackgroundScheduler(timezone=config.timezone)

    scanner = RecordingScanner(db, config.transcribe_url, config.recordings_dir)
    summary_task = IndividualSummaryTask(db, llm, dify, config.summaries_dir)
    deadline_task = DeadlineExtractorTask(db, llm)
    digest_task = DailyDigestTask(db, llm, telegram)

    # WF01: Scan every 5 min + check pending
    scheduler.add_job(scanner.scan, IntervalTrigger(minutes=config.scan_interval_minutes), id="scan_recordings")
    scheduler.add_job(scanner.check_pending, IntervalTrigger(minutes=config.scan_interval_minutes), id="check_pending")

    # WF03: Individual summaries at 22:00
    scheduler.add_job(summary_task.run, CronTrigger(hour=config.individual_summary_hour, minute=0), id="individual_summary")

    # WF06: Deadline extraction at 22:30
    scheduler.add_job(deadline_task.run, CronTrigger(hour=config.deadline_extractor_hour, minute=config.deadline_extractor_minute), id="deadline_extractor")

    # WF02: Daily digest at 23:00
    scheduler.add_job(digest_task.run, CronTrigger(hour=config.daily_digest_hour, minute=0), id="daily_digest")

    return scheduler
```

#### 3.2 `app/main.py`

```python
import asyncio
import signal
from app.config import Settings
from app.core.db import Database
from app.core.llm import LLMClient
from app.core.telegram_api import TelegramClient
from app.core.dify_api import DifyClient
from app.scheduler import create_scheduler
from app.bot.handler import BotService

def main():
    settings = Settings()

    db = Database(settings.database_dsn)
    llm = LLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
    telegram = TelegramClient(settings.telegram_bot_token)
    dify = DifyClient(settings.dify_api_key, settings.dify_base_url)

    # Start scheduler (WF01, WF02, WF03, WF06)
    scheduler = create_scheduler(settings, db, llm, telegram, dify)
    scheduler.start()

    # Start Telegram bot (WF04) -- blocking
    bot = BotService(settings.telegram_bot_token, db, llm)
    bot.start()

if __name__ == "__main__":
    main()
```

#### 3.3 `Dockerfile` (new orchestrator service)

```dockerfile
FROM python:3.11-slim
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/ ./app/
CMD ["python", "-m", "app.main"]
```

---

### Phase 4: Docker Compose Update (0.5 days)

#### 4.1 New `docker-compose.yml`

Replace the n8n service with the new orchestrator:

```yaml
services:
  # REMOVED: n8n service (50+ lines)

  orchestrator:
    build:
      context: .
      dockerfile: Dockerfile
    restart: unless-stopped
    environment:
      - POSTGRES_HOST=postgres
      - POSTGRES_PORT=5432
      - POSTGRES_DB=${POSTGRES_DB:-n8n}
      - POSTGRES_USER=${POSTGRES_USER:-n8n}
      - POSTGRES_PASSWORD=${POSTGRES_PASSWORD}
      - LLM_API_KEY=${GLM4_API_KEY}           # backward compat
      - LLM_BASE_URL=${GLM4_BASE_URL:-https://api.z.ai/api/anthropic}
      - LLM_MODEL=${GLM4_MODEL:-claude-3-5-haiku-20241022}
      - TELEGRAM_BOT_TOKEN=${TELEGRAM_BOT_TOKEN}
      - TELEGRAM_CHAT_ID=${TELEGRAM_CHAT_ID}
      - DIFY_API_KEY=${DIFY_API_KEY}
      - DIFY_BASE_URL=${DIFY_BASE_URL:-https://dify-ff.duckdns.org}
      - DIFY_CHATBOT_URL=${DIFY_CHATBOT_URL}
      - TRANSCRIBE_URL=http://transcribe:9001
      - SUMMARIES_BASE_URL=${SUMMARIES_BASE_URL:-http://84.252.100.93:8181}
      - TZ=Europe/Moscow
    volumes:
      - /mnt/recordings:/recordings:ro
      - summaries_data:/summaries
    depends_on:
      postgres:
        condition: service_healthy
    networks:
      - mvp-network

  # UNCHANGED: postgres, transcribe, whisper, summaries-nginx
```

#### 4.2 Volumes to Remove
- `n8n_data` volume -- no longer needed (saves ~500MB+ disk)

---

### Phase 5: Migration & Verification (2-3 days)

#### 5.1 Parallel Run Strategy

1. **Day 1:** Deploy orchestrator alongside n8n (both active)
   - Deactivate n8n workflows one by one
   - Start with WF03 (it's broken anyway)
   - Then WF06, WF02, WF01, WF04

2. **Day 2:** All workflows on Python orchestrator, n8n still running but all workflows inactive
   - Monitor logs: `docker logs orchestrator -f`
   - Verify: Telegram messages arrive, summaries generated, bot responds

3. **Day 3:** Remove n8n from docker-compose, clean up
   - `docker compose rm n8n`
   - Remove `n8n_data` volume
   - Remove `n8n-workflows/` directory (archive to git tag first)

#### 5.2 Verification Checklist

| Check | Command | Expected |
|-------|---------|----------|
| Orchestrator running | `docker logs orchestrator --tail 20` | Scheduler started, 5 jobs registered |
| File scan works | Drop test file in `/mnt/recordings/` | Detected within 5 min, transcription started |
| Transcription completes | `SELECT * FROM processed_files ORDER BY id DESC LIMIT 5` | Status = completed |
| Individual summary | Wait until 22:00 or trigger manually | `client_summaries` row + .md file + Dify doc |
| Deadline extraction | Wait until 22:30 or trigger manually | `extracted_tasks` rows |
| Daily digest | Wait until 23:00 or trigger manually | Telegram message received |
| Bot /report | Send `/report` to bot | Report generated |
| Bot /status | Send `/status` to bot | System status shown |
| Error handling | Kill Whisper, drop file | Error logged, retried next scan |

#### 5.3 Testing Strategy

```bash
# Unit tests
pytest tests/ -v

# Integration test (requires PostgreSQL)
pytest tests/ -v -m integration

# Manual E2E test
python -m app.tasks.scan_recordings --once    # single scan
python -m app.tasks.daily_digest --once       # generate digest now
python -m app.tasks.individual_summary --once # generate summaries now
```

---

## 4. THINGS THAT DON'T CHANGE

| Component | Why |
|-----------|-----|
| **transcribe service** | Already independent Python microservice. Perfect as-is. |
| **PostgreSQL** | Database stays exactly the same. Same schema, same data. |
| **Whisper** | Self-hosted STT server. No connection to n8n. |
| **Dify.ai** | RAG platform. API calls just move from n8n HTTP nodes to Python httpx. |
| **Nginx summaries** | Serves static .md files. No changes needed. |
| **Jitsi/Jibri** | Records meetings. Files go to same `/mnt/recordings/` path. |
| **DB schema** | All tables (`processed_files`, `client_summaries`, `prompts`, etc.) stay the same. |

---

## 5. BUGS FIXED BY THIS MIGRATION

| Bug | Current State | After Migration |
|-----|---------------|-----------------|
| **WF03 wrong API format** | Hardcoded `open.bigmodel.cn` OpenAI endpoint | Unified `llm.py` always uses correct Anthropic API |
| **WF01 race condition** | 10 retries x 60s, then marks error | `check_pending()` runs indefinitely every 5 min |
| **Credential hardcoding** | API keys in gen_wf*.py, docs, test scripts | Single `.env` file, `config.py` loads it |
| **Duplicate business logic** | JS in n8n Code nodes + Python scripts | Python only |
| **No retry on LLM failure** | n8n workflow stops on HTTP error | `tenacity` retry with exponential backoff |
| **Telegram bot delay** | n8n polls every 30s | python-telegram-bot uses long polling (instant) |
| **Large file timeout** | Fixed 10-min timeout in n8n | No timeout on check_pending; transcribe service handles its own timeouts |
| **Prompt versioning** | Prompts embedded in JSON workflow nodes | Prompts read from `prompts` DB table (already exists!) |

---

## 6. OPTIONAL IMPROVEMENTS (Post-Migration)

### 6.1 File Watcher Instead of Polling (Priority: Medium)

Replace 5-min cron scan with `watchdog` filesystem watcher for instant detection:

```python
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class RecordingHandler(FileSystemEventHandler):
    def on_created(self, event):
        if event.src_path.endswith(('.webm', '.mp4', '.wav')):
            # Wait 10s for file write to complete, then process
            threading.Timer(10, process_new_file, args=[event.src_path]).start()
```

**Note:** Keep the 5-min scan as a fallback for files missed by watchdog (e.g., NFS mounts, Docker volume syncs).

### 6.2 Telegram Chat Auto-Export (Priority: Medium)

Current state: `export_telegram_chat.py` must be run manually.
Improvement: Schedule it as another task in the orchestrator (daily at 21:00).

### 6.3 Health Endpoint (Priority: Low)

Add a simple HTTP health endpoint for monitoring:
```python
# GET http://orchestrator:8080/health
{
    "status": "ok",
    "scheduler_jobs": 5,
    "next_digest": "2026-03-04T23:00:00",
    "db_connected": true,
    "pending_transcriptions": 0
}
```

### 6.4 Web Dashboard (Priority: Low)

Replace n8n UI monitoring with a simple Flask/FastAPI dashboard showing:
- Recent executions (last 24h)
- Error log
- Pending transcriptions
- Next scheduled tasks

---

## 7. EFFORT ESTIMATION

| Phase | Work | Estimate |
|-------|------|----------|
| Phase 0: Structure + Config | Project scaffold, requirements.txt, config.py | 1-2 days |
| Phase 1: Core Modules | db.py, llm.py, telegram_api.py, dify_api.py, logger | 2-3 days |
| Phase 2: Task Implementations | 5 tasks (WF01-WF06) + bot commands | 3-5 days |
| Phase 3: Scheduler + Entry Point | scheduler.py, main.py, Dockerfile | 1 day |
| Phase 4: Docker Compose | Update docker-compose.yml, .env.example | 0.5 days |
| Phase 5: Migration + Testing | Parallel run, verification, cleanup | 2-3 days |
| **Total** | | **10-15 days** |

### Critical Path

```
Phase 0 → Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5
                ↑
        Can be parallelized:
        - db.py + llm.py (different developers)
        - tasks can be done independently once core is ready
```

---

## 8. .env CHANGES

### New Variables (optional, for cleaner naming)

```env
# New (preferred)
LLM_API_KEY=99918695e8de...
LLM_BASE_URL=https://api.z.ai/api/anthropic
LLM_MODEL=claude-3-5-haiku-20241022

# Old (still supported via aliases in config.py)
GLM4_API_KEY=...
GLM4_BASE_URL=...
GLM4_MODEL=...
```

### Removed Variables

```env
# No longer needed (n8n-specific)
N8N_PORT=5678
N8N_USER=admin
N8N_PASSWORD=...
N8N_ENCRYPTION_KEY=...
N8N_WEBHOOK_URL=...
N8N_SECURE_COOKIE=false
N8N_BASIC_AUTH_ACTIVE=true
N8N_BASIC_AUTH_USER=...
N8N_BASIC_AUTH_PASSWORD=...
```

---

## 9. FILE CLEANUP AFTER MIGRATION

### Remove

```
n8n-workflows/                     # All 7 workflow JSONs
  00-error-workflow.json
  01-new-recording.json
  02-daily-digest.json
  03-individual-summaries.json
  03-individual-summary.json
  04-telegram-bot.json
  05-prompt-tester.json
  06-deadline-extractor.json

scripts/gen_wf02.py                # Workflow generators (no longer needed)
scripts/gen_wf03.py
scripts/gen_wf04.py
scripts/gen_wf05.py
scripts/add_per_call_summary.py    # n8n DB patches
scripts/add_save_summary_node.py
scripts/create_bot_commands_workflow.py
scripts/create_wf04_via_db.py
scripts/update_workflow02_digest_format.py
scripts/deploy-workflows.sh

fix_digest.js                      # n8n node patch

docs/N8N_WORKFLOW_UPDATE.md        # n8n-specific documentation

*.json (root level)                # Workflow exports, execution dumps
  wf02.json, wf02_full.json, wf02_updated.json
  exec_200.json, exec_202.json, exec_list.json
  glm_test*.json
```

### Keep (with updates)

```
scripts/init-db.sql                # DB schema (unchanged)
scripts/migrate_db_v2.sql          # DB migration (unchanged)
scripts/test_wf02.py               # Useful as reference / integration test (rename)
scripts/test_wf03.py               # Useful as reference / integration test (rename)
scripts/export_telegram_chat.py    # Still needed for manual chat export
scripts/import_chat_to_db.py       # Still needed for chat import
scripts/setup_dify_datasets.py     # Still needed for Dify setup
scripts/backup-db.sh               # Still needed for backups

services/transcribe/               # UNCHANGED -- independent microservice
docker-compose.yml                 # UPDATE: remove n8n, add orchestrator
.env.example                       # UPDATE: remove n8n vars, add orchestrator vars
docs/*                             # UPDATE references to n8n (minor text changes)
```

---

## 10. SUMMARY

This migration replaces the n8n orchestration layer with ~1500 lines of Python code organized into a clean, testable project structure. The key benefits are:

1. **Fixes the WF03 critical bug** immediately (correct Anthropic API)
2. **Eliminates the WF01 race condition** (indefinite rechecking vs. fixed retries)
3. **Single language, single codebase** (Python only, no JavaScript)
4. **Proper error handling** with retries and structured logging
5. **Instant Telegram bot responses** via long polling
6. **Simpler infrastructure** (one less Docker container, ~500MB less RAM)
7. **Version-controlled logic** (git diff instead of JSON surgery)
8. **Testable** with pytest (unit + integration tests)

The migration can be done incrementally with zero downtime by running both systems in parallel during the transition period.
