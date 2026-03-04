# MVP Auto-Summary: Architecture & Specifications

> **Version:** 2.0 | **Date:** 2026-03-04  
> **Status:** Phase 0 — MVP  
> **Strategy:** Python Orchestrator + Buy over Build

---

## 1. Overview

System for automatic meeting transcription and summarization at a fulfillment company.

**What it does (Phase 0):**
1. Manager conducts a call in Jitsi (room name: `LEAD-{ID}-conf`)
2. Jibri records the meeting → file lands on NFS server
3. Python orchestrator detects new file → sends audio to Whisper (self-hosted)
4. Whisper returns transcript → saved to PostgreSQL + Dify Knowledge Base
5. Daily at 23:00: orchestrator collects all transcripts → Claude summarizes → Telegram digest

---

## 2. Architecture Diagram

```
                    ┌──────────────────────────────────────────────────┐
                    │                VPS (Ubuntu 22.04)                │
                    │                2 vCPU / 8 GB RAM                 │
                    │                                                  │
                    │  ┌─────────────────────────────────────────────┐ │
                    │  │            docker-compose                   │ │
                    │  │                                             │ │
                    │  │  ┌──────────────────────┐                  │ │
                    │  │  │   orchestrator       │                  │ │
                    │  │  │   (Python + APSched) │                  │ │
                    │  │  │   + Telegram Bot     │                  │ │
                    │  │  └──────────┬───────────┘                  │ │
                    │  │             │                              │ │
                    │  │  ┌──────────┴───────────┐                  │ │
                    │  │  │      PostgreSQL       │                  │ │
                    │  │  │       :5432           │                  │ │
                    │  │  │  (all data storage)   │                  │ │
                    │  │  └──────────────────────┘                  │ │
                    │  │                                             │ │
                    │  │  ┌──────────────────────┐                  │ │
                    │  │  │   transcribe service │                  │ │
                    │  │  │   (STT adapter)      │                  │ │
                    │  │  └──────────┬───────────┘                  │ │
                    │  │             │                              │ │
                    │  │  ┌──────────┴───────────┐                  │ │
                    │  │  │   Whisper (optional) │                  │ │
                    │  │  │   :8000 (profile)    │                  │ │
                    │  │  └──────────────────────┘                  │ │
                    │  │                                             │ │
                    │  │  ┌──────────────────────┐                  │ │
                    │  │  │  summaries-nginx     │                  │ │
                    │  │  │  :8181               │                  │ │
                    │  │  └──────────────────────┘                  │ │
                    │  └─────────────────────────────────────────────┘ │
                    │                                                  │
                    │  ┌────────────────┐                              │
                    │  │ /mnt/recordings│ ← NFS mount (read-only)     │
                    │  └────────────────┘                              │
                    └──────────────────────────────────────────────────┘
                              │                    │
                    ┌─────────▼─────────┐  ┌──────▼──────────┐
                    │  Claude (z.ai)    │  │  Dify.ai (RAG)  │
                    │  LLM API          │  │  External       │
                    └───────────────────┘  └─────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Telegram Bot API  │
                    │  - Daily digest    │
                    │  - Bot commands    │
                    └───────────────────┘
```

---

## 3. Key Architectural Decisions

### 3.1. Python Orchestrator (replaces n8n)

**Verdict: Миграция завершена 2026-03-04.**

Причины замены n8n на Python:

| Проблема n8n | Решение Python |
|--------------|----------------|
| Workflow JSON — чёрный ящик | Код в git, читаемый Python |
| JS в Code nodes + Python scripts = 2 кодовые базы | Единый Python |
| WF03 сломан (неправильный API формат) | Unified LLM client |
| Нет нормального retry/backoff | tenacity library |
| n8n UI для мониторинга | Telegram /status + логи |
| ~500MB RAM overhead | ~50MB RAM |

**Структура проекта:**

```
app/
├── main.py              # Entry point
├── config.py            # Pydantic Settings from .env
├── scheduler.py         # APScheduler jobs (WF01, 02, 03, 06)
├── core/
│   ├── db.py            # PostgreSQL connection pool
│   ├── llm.py           # Claude API (Anthropic format)
│   ├── telegram_api.py  # Telegram Bot API helpers
│   ├── dify_api.py      # Dify Knowledge Base API
│   └── logger.py        # Structured logging
├── tasks/
│   ├── scan_recordings.py      # WF01: scan + transcribe
│   ├── individual_summary.py   # WF03: per-client summaries
│   ├── deadline_extractor.py   # WF06: task extraction
│   └── daily_digest.py         # WF02: daily digest
└── bot/
    └── handler.py              # WF04: Telegram bot commands
```

### 3.2. File Watcher: Cron Scan

**Проблема**: `inotify` НЕ работает с NFS (файлы, созданные удалённой машиной, не генерируют события).

**Решение**: APScheduler IntervalTrigger (каждые 5 минут) + сканирование папки.

```python
scheduler.add_job(
    scanner.scan,
    IntervalTrigger(minutes=5),
    id="scan_recordings"
)
```

### 3.3. Whisper self-hosted (STT)

**Решение**: Self-hosted Whisper (0 руб/мес) вместо Yandex SpeechKit (25K руб/мес).

| Критерий | Yandex SpeechKit | Whisper (self-hosted) |
|----------|------------------|----------------------|
| Стоимость | ~25,000 руб/мес | **0 руб** |
| Формат WebM | ❌ Не поддерживает | ✅ Нативно |
| Конвертация | Нужна | **Не нужна** |
| Приватность | Данные в облаке | **Всё локально** |

**Docker**: `fedirz/faster-whisper-server:latest-cpu`  
**API**: `POST http://whisper:8000/v1/audio/transcriptions`

**Модели:**

| Модель | RAM | Скорость (60 мин) | Качество RU |
|--------|-----|-------------------|-------------|
| small | +2 GB | ~20 мин | Хорошее |
| **medium** | **+3 GB** | **~40 мин** | **Очень хорошее** |
| large-v3 | +5 GB | ~90 мин | Отличное |

### 3.4. LLM: Claude 3.5 Haiku (via z.ai)

**Endpoint**: `https://api.z.ai/api/anthropic/v1/messages`  
**Format**: Anthropic Messages API (НЕ OpenAI-compatible!)

```python
# Auth headers:
"x-api-key": API_KEY
"anthropic-version": "2023-06-01"
```

### 3.5. Dify.ai для RAG

Per-client Knowledge Bases в Dify:
- Каждый клиент = свой dataset
- Summaries push'атся через API
- RAG-чат через Dify Chatbot

---

## 4. Component Responsibilities

| Компонент | Роль | Порт | Данные |
|-----------|------|------|--------|
| **orchestrator** | Scheduler + Telegram bot | — | Все workflow |
| **transcribe** | STT adapter (Whisper/SpeechKit) | 9001 | — |
| **whisper** | Self-hosted STT | 8000 | — |
| **postgres** | All data storage | 5432 | processed_files, client_summaries, etc. |
| **summaries-nginx** | Static .md files | 8181 | /summaries/*.md |
| **Claude (z.ai)** | Summarization | External API | — |
| **Dify.ai** | RAG + Knowledge Base | External | Per-client datasets |

---

## 5. Scheduled Tasks

| ID | Schedule | Task | Описание |
|----|----------|------|----------|
| WF01 | */5 min | `scan_recordings` | Scan /recordings → transcribe → save |
| WF03 | 22:00 | `individual_summary` | Per-client summaries (calls + chats) |
| WF06 | 22:30 | `deadline_extractor` | Extract tasks/deadlines from transcripts |
| WF02 | 23:00 | `daily_digest` | Aggregate → summarize → Telegram |
| WF04 | On-demand | Telegram bot | /report, /status, /rag, /help |

---

## 6. Database Schema

### Основные таблицы

```sql
-- Аудиозаписи
processed_files (
    id, filename, filepath, lead_id, file_date,
    status, transcript_text, summary_sent,
    dify_doc_id, file_size, created_at
)

-- Telegram чаты
chat_messages (
    id, lead_id, chat_title, sender,
    message_text, message_date, imported_at
)

-- Индивидуальные summaries
client_summaries (
    id, lead_id, source_type, source_id,
    summary_text, summary_date, created_at
)

-- Маппинг клиент ↔ чат ↔ Dify dataset
lead_chat_mapping (
    lead_id, lead_name, chat_id, chat_title,
    curators, dify_dataset_id, active
)

-- Промпты с версионированием
prompts (
    id, name, prompt_text, version, is_active
)

-- Извлечённые задачи
extracted_tasks (
    id, lead_id, source_file, task_desc,
    assignee, deadline, created_at
)
```

---

## 7. Risk Analysis

### RED (Critical)

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Whisper OOM** | Pipeline stops | Use medium model, 8GB RAM |
| **NFS mount drops** | No recordings | Health check, Telegram alert |
| **LLM API down** | No summaries | Retry with backoff, fallback model |

### YELLOW (Medium)

| Risk | Impact | Mitigation |
|------|--------|------------|
| Whisper backlog | Digest delay | Small model, off-peak |
| Dify API changes | RAG broken | Pin version, test upgrades |

---

## 8. Project Structure

```
mvp-auto-summary/
├── docker-compose.yml          # Infrastructure
├── Dockerfile                  # Python orchestrator
├── requirements.txt            # Python deps
├── .env.example                # Environment template
│
├── app/                        # Python orchestrator
│   ├── main.py
│   ├── config.py
│   ├── scheduler.py
│   ├── core/
│   │   ├── db.py
│   │   ├── llm.py
│   │   ├── telegram_api.py
│   │   ├── dify_api.py
│   │   └── logger.py
│   ├── tasks/
│   │   ├── scan_recordings.py
│   │   ├── individual_summary.py
│   │   ├── deadline_extractor.py
│   │   └── daily_digest.py
│   └── bot/
│       └── handler.py
│
├── services/
│   └── transcribe/             # STT adapter service
│       ├── transcribe_server.py
│       └── Dockerfile
│
├── scripts/
│   ├── init-db.sql             # DB schema
│   ├── export_telegram_chat.py # Chat export (Telethon)
│   ├── import_chat_to_db.py
│   └── setup_dify_datasets.py
│
├── docs/
│   ├── SPECS.md                # This file
│   ├── API.md                  # API contracts
│   ├── QUICKSTART.md           # Quick start guide
│   └── ERRORS.md               # Troubleshooting
│
├── tests/
│   ├── conftest.py
│   └── test_*.py
│
└── nginx/
    └── summaries.conf          # Nginx config
```

---

## 9. Cost Estimate (Monthly)

| Component | Cost | Notes |
|-----------|------|-------|
| VPS (2 vCPU, 8 GB RAM) | ~2,500 RUB | Ubuntu 22.04 |
| Whisper (self-hosted) | **0 RUB** | On VPS |
| Claude 3.5 Haiku (z.ai) | ~300 RUB | ~$0.003 per summary |
| Dify.ai Cloud | Free tier | Or self-hosted |
| **TOTAL** | **~2,800 RUB/month** | |

---

## 10. Telegram Bot Commands

| Command | Description |
|---------|-------------|
| `/report` | Intermediate report on today's calls |
| `/status` | System status + client list + links |
| `/rag` | Link to Dify RAG chatbot |
| `/help` | Command reference |

---

## 11. Migration from n8n (2026-03-04)

**Статус**: ЗАВЕРШЕНО

| Phase | Description | Status |
|-------|-------------|--------|
| Phase 0 | Project structure + config | DONE |
| Phase 1 | Core modules (db, llm, telegram, dify) | DONE |
| Phase 2 | Task implementations (WF01-06) | DONE |
| Phase 3 | Scheduler + entry point | DONE |
| Phase 4 | Docker infrastructure | DONE |
| Phase 5 | Migration verification | DONE |

**Что изменилось:**
- n8n → Python orchestrator (app/)
- JS Code nodes → Python modules
- n8n credentials → .env file
- Workflow JSON → Python code in git
- n8n UI monitoring → Telegram /status + logs

**n8n всё ещё доступен** через `docker compose --profile legacy up -d n8n` для отката.

---

## 12. Доступы (актуальные)

| Сервис | URL | Данные |
|--------|-----|--------|
| Telegram Bot | `@ffp_report_bot` | Token в .env |
| Telegram Chat ID | `-1003872092456` | Группа "Отчёты ФФ Платформы" |
| Dify UI | `https://dify-ff.duckdns.org` | API key в .env |
| Summaries | `http://84.252.100.93:8181/summaries/` | Static .md files |

---

*Document created: 2026-02-18 | Updated: 2026-03-04 — Python orchestrator, removed n8n references*
