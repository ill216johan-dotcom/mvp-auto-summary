# MVP Auto-Summary: Architecture & Specifications

> **Version:** 1.0 | **Date:** 2026-02-18  
> **Status:** Phase 0 — MVP  
> **Strategy:** Buy over Build — no custom backend

---

## 1. Overview

System for automatic meeting transcription and summarization at a fulfillment company.

**What it does (Phase 0):**
1. Manager conducts a call in Jitsi (room name: `LEAD-{ID}-conf`)
2. Jibri records the meeting → file lands on NFS server
3. n8n detects new file → sends audio directly to Whisper (self-hosted)
4. Whisper returns transcript → saved to open-notebook + metadata in PostgreSQL
5. Daily at 23:00: n8n collects all transcripts → GLM-4 summarizes → Telegram digest

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
                    │  │  ┌──────────┐  ┌──────────────┐           │ │
                    │  │  │   n8n    │  │ open-notebook │           │ │
                    │  │  │  :5678   │  │    :8888      │           │ │
                    │  │  └────┬─────┘  └──────┬───────┘           │ │
                    │  │       │               │                    │ │
                    │  │  ┌────┴───────────────┴────┐              │ │
                    │  │  │      PostgreSQL          │              │ │
                    │  │  │       :5432              │              │ │
                    │  │  │  (n8n metadata store)    │              │ │
                    │  │  └─────────────────────────┘              │ │
                    │  │                                             │ │
                    │  │  ┌─────────────────────────┐              │ │
                    │  │  │      SurrealDB           │              │ │
                    │  │  │       :8000              │              │ │
                    │  │  │  (open-notebook data)    │              │ │
                    │  │  └─────────────────────────┘              │ │
                    │  └─────────────────────────────────────────────┘ │
                    │                                                  │
                    │  ┌────────────────┐                              │
                    │  │ /mnt/recordings│ ← NFS mount (read-only)     │
                    │  └────────────────┘                              │
                    └──────────────────────────────────────────────────┘
                              │                    │
                    ┌─────────▼─────────┐  ┌──────▼──────────┐
                    │  Whisper (local)  │  │  ZhipuAI (GLM)  │
                    │  - STT API        │  │  - GLM-4-FlashX │
                    │  - Container      │  │  :5678 HTTP     │
                    └───────────────────┘  └─────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Telegram Bot API  │
                    │  - Daily digest    │
                    └───────────────────┘
```

---

## 3. Key Architectural Decisions

### 3.1. open-notebook = YES (with caveats)

**Verdict: Подходит для MVP.**

Исследование показало, что open-notebook (lfnovo/open-notebook) имеет **полноценный REST API**:

| Возможность | Поддержка | Endpoint |
|-------------|-----------|----------|
| Создание блокнотов | YES | `POST /notebooks` |
| Добавление источников (текст, файл, URL) | YES | `POST /sources` |
| Привязка к нескольким блокнотам | YES | `POST /notebooks/{id}/sources/{id}` |
| RAG-чат по блокноту | YES | `POST /chat/execute` |
| Векторный поиск | YES | `POST /search` |
| Auto-RAG (поиск + синтез) | YES | `POST /search/ask` |

**LLM-бэкенды**: 16+ провайдеров. GLM-4 через Ollama (локально) или OpenRouter (облако).

**БД**: SurrealDB (граф + вектор + полнотекст).

**Критические ограничения:**
- Нет фильтрации по дате в API → фильтровать в n8n
- Нет bulk-операций → последовательные вызовы
- Аутентификация только по паролю → нужен reverse proxy для prod
- Контекст для чата строится на фронтенде → в n8n строить вручную

### 3.2. File Watcher: Cron Scan вместо LocalFileTrigger

**Проблема**: `LocalFileTrigger` отключён по умолчанию в n8n 2.0. Даже если включить — `inotify` НЕ работает с NFS (файлы, созданные удалённой машиной, не генерируют события).

**Решение**: Schedule Trigger (каждые 5 минут) + сканирование папки + отслеживание обработанных файлов в PostgreSQL.

```
[Schedule: */5 * * * *]
    → Read /mnt/recordings/**/*.{webm,mp3}
    → Filter: NOT IN processed_files (PostgreSQL)
    → For each new file:
        → Convert WebM → MP3 (ffmpeg)
        → Upload to Yandex S3
        → Start SpeechKit async
        → Mark as "processing" in DB
```

### 3.3. Whisper вместо Yandex SpeechKit (ИЗМЕНЕНИЕ v1.1)

**Решение**: Заменили Yandex SpeechKit (25K руб/мес) на self-hosted Whisper (0 руб/мес).

**Почему Whisper лучше для этого MVP:**

| Критерий | Yandex SpeechKit | Whisper (self-hosted) |
|----------|------------------|----------------------|
| Стоимость | ~25,000 руб/мес | **0 руб** |
| Формат WebM | ❌ Не поддерживает | ✅ Нативно |
| Конвертация | Нужна (WebM→MP3) | **Не нужна** |
| S3 upload | Обязателен | **Не нужен** |
| Polling | Асинхронный (сложно) | **Синхронный (просто)** |
| Приватность | Данные уходят в облако | **Всё локально** |
| Качество RU | Отличное | Очень хорошее (medium) |
| Зависимости | API key + S3 + folder_id | **Ничего** |

**Docker**: `onerahmet/openai-whisper-asr-webservice:latest-cpu`  
**Engine**: faster-whisper (CTranslate2 — в 4x быстрее оригинального Whisper)  
**API**: `POST http://whisper:9000/asr?task=transcribe&language=ru&output=json`

**Модели и ресурсы:**

| Модель | RAM | Скорость (60 мин) | WER русский |
|--------|-----|-------------------|-------------|
| tiny | +1 GB | ~5 мин | ~15% |
| base | +1 GB | ~10 мин | ~10% |
| small | +2 GB | ~20 мин | ~7% |
| **medium** | **+3 GB** | **~40 мин** | **~5%** |
| large-v3 | +5 GB | ~90 мин | ~3% |

**Рекомендация**: модель `medium` — баланс качества и скорости. VPS нужен 8 GB RAM.

**Простой flow (без конвертации, без S3, без polling):**
1. n8n отправляет WebM файл напрямую в Whisper
2. Whisper возвращает текст синхронно
3. Готово

Это **радикальное упрощение** по сравнению с SpeechKit (убраны 4 шага).

### 3.4. GLM-4: Выбор модели

| Модель | Контекст | Цена (input/output за 1M tok) | Рекомендация |
|--------|----------|-------------------------------|--------------|
| GLM-4.7-Flash | 200K | **БЕСПЛАТНО** | Для тестирования |
| GLM-4.7-FlashX | 200K | $0.07 / $0.40 | **MVP (production)** |
| GLM-4.7 | 200K | $0.60 / $2.20 | Максимальное качество |

**API endpoint**: `https://api.z.ai/api/paas/v4/chat/completions`  
**Совместимость**: OpenAI-compatible → можно использовать OpenAI-ноду n8n.

**Рекомендация**: GLM-4.7-FlashX для MVP (~$0.005 за суммари одного митинга).

### 3.5. Нет кастомного бэкенда

MVP работает без единой строчки серверного кода:
- **n8n** = автоматизация (workflows)
- **open-notebook** = хранение + RAG + UI
- **PostgreSQL** = метаданные n8n + трекинг обработанных файлов
- **ffmpeg** = конвертация (вызов через n8n Execute Command)

Единственный "код" — JavaScript-сниппеты внутри n8n Code nodes.

---

## 4. Component Responsibilities

| Компонент | Роль | Порт | Данные |
|-----------|------|------|--------|
| **n8n** | Оркестрация всех workflow | 5678 | Метаданные в PostgreSQL |
| **open-notebook** | Хранение транскриптов, RAG, UI для кураторов | 8888 | SurrealDB |
| **PostgreSQL** | n8n persistence + processed files tracker | 5432 | Volumes |
| **SurrealDB** | БД open-notebook (граф + вектор) | 8000 | Volumes |
| **Whisper (self-hosted)** | STT (Speech-to-Text) | 9000 | Local |
| **GLM-4 (ZhipuAI)** | Суммаризация транскриптов | External API | — |
| **Telegram Bot** | Отправка дайджестов | External API | — |

---

## 5. Data Flow

### Workflow 1: New Recording → Transcription (каждые 5 мин)

```
┌──────────────────┐
│ Schedule Trigger  │ ← Каждые 5 минут
│   */5 * * * *     │
└────────┬─────────┘
         │
┌────────▼─────────┐
│ Scan /recordings  │ ← find + sort by mtime (новые первые)
│ *.webm, *.mp3     │   максимум 50 файлов за раз
└────────┬─────────┘
         │
┌────────▼──────────────────┐
│ Parse LEAD_ID              │ ← Regex: /^(\d+)_/
│ from filename              │
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Check PostgreSQL           │ ← COUNT(*) processed_files
│ Is New File?               │   count=0 → новый
└────────┬──────────────────┘
         │ (только новые)
         │
┌────────▼──────────────────┐
│ Mark as Transcribing       │ ← INSERT status='transcribing'
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Read Binary File           │ ← Загрузка файла в память
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Whisper Transcribe         │ ← POST /asr (multipart)
└────────┬──────────────────┘
         │
    ┌────┴────┐
    │ Has     │
    │Transcript│
    └────┬────┘
    yes  │  no
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│Extract│ │ Error │
│ Text  │ │ Mark  │
└───┬───┘ └───────┘
    │
┌────▼──────────────────────┐
│ Get/Create Notebook       │ ← open-notebook API
│ Save Transcript           │   с обработкой ошибок
└────────┬──────────────────┘
         │
    ┌────┴────┐
    │ Save    │
    │ Success?│
    └────┬────┘
    yes  │  no
    ┌────┴────┐
    │         │
    ▼         ▼
┌───────┐ ┌───────┐
│ Mark  │ │ Error │
│ Compl │ │ Mark  │
└───────┘ └───────┘
```

*Workflow 1.5 (polling SpeechKit) УДАЛЁН — с Whisper транскрипция синхронная, polling не нужен.*

### Workflow 2: Daily Digest (23:00)

```
┌──────────────────┐
│ Schedule Trigger  │ ← Каждый день в 23:00
│   0 23 * * *      │
└────────┬─────────┘
         │
┌────────▼──────────────────┐
│ SELECT v_today_completed   │ ← summary_sent=false
│ from PostgreSQL            │    AND status = 'completed'
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Aggregate transcripts      │ ← Code node
│ (max 50K chars, truncate)  │   защита от переполнения
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ GLM-4.7-FlashX summarize   │ ← POST /chat/completions
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Send Telegram digest       │ ← POST /sendMessage
│ (chunks max 3500 chars)    │   разбиение на части
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Update processed_files     │ ← summary_sent=true
└──────────────────────────┘
```

---

## 6. Risk Analysis

### RED (Critical)

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Whisper OOM / model too heavy** | Pipeline stops | Use smaller model (small/medium) or upgrade RAM |
| **NFS mount drops** | No new recordings detected | Health check workflow; alert to Telegram |
| **Whisper timeout on long files** | Transcriptions queue up | Increase HTTP timeout; split long files |
| **open-notebook API changes** | Integration breaks | Pin Docker image version; test before upgrade |

### YELLOW (Medium)

| Risk | Impact | Mitigation |
|------|--------|------------|
| Whisper processing backlog (slow CPU) | Digest delay | Use smaller model; schedule off-peak; scale VPS |
| GLM-4 API instability (China-hosted) | Digest delay | Retry logic; fallback to GLM-4.7-Flash (free) |
| open-notebook SurrealDB data loss | Loss of transcripts | Daily DB backup script; keep original files |
| Duplicate processing | Double transcription costs | Idempotency via PostgreSQL processed_files table |

### GREEN (Low)

| Risk | Impact | Mitigation |
|------|--------|------------|
| Manager forgets LEAD-{ID} naming | File not processed | Alert on "unknown" files; manual reprocessing |
| Telegram bot rate limit | Digest delayed | Single message per day is well under limit |

---

## 7. Migration Path (Phase 0 → Full Vision)

**Phase 0 does NOT paint into a corner** because:

1. **open-notebook supports RAG** → Phase 4 (RAG-чат по клиенту) available immediately
2. **PostgreSQL already present** → Phase 1 (Telegram history) can store data here
3. **n8n is extensible** → Phase 2 (Bitrix24) = new workflow + HTTP nodes
4. **LEAD-{ID} is the universal key** → all phases use the same client identifier
5. **open-notebook multi-notebook** → each client = 1 notebook, all sources linked

### Phase Roadmap

| Phase | Scope | New Components | Effort |
|-------|-------|----------------|--------|
| **0** (current) | Meetings → Transcription → Digest | n8n, open-notebook, Whisper, GLM-4, Telegram | 1-2 weeks |
| **1** | Telegram chat history import | Telegram Bot (webhook) + n8n | 1 week |
| **2** | Bitrix24 call/email summaries | n8n HTTP → Bitrix API | 1 week |
| **3** | Unified client profile | open-notebook notebooks as profiles | 1 week |
| **4** | RAG chat per client | open-notebook /chat/execute | Already built-in |
| **5** | WMS integration + alerts | n8n HTTP → WMS API, alert workflow | 2 weeks |
| **6** | Churn risk detection | GLM-4 analysis workflow, scoring | 2 weeks |

---

## 8. Project Structure

```
mvp-auto-summary/
├── docker-compose.yml          # Infrastructure: n8n + open-notebook + DBs
├── .env.example                # Environment variables template
├── .gitignore                  # Exclude .env, volumes, temp files
│
├── docs/
│   ├── SPECS.md                # This file — architecture & decisions
│   ├── API.md                  # API contracts (external services)
│   └── ERRORS.md               # Known errors & troubleshooting
│
├── n8n-workflows/
│   ├── 01-new-recording.json       # Workflow 1: Scan → Whisper → open-notebook
│   └── 02-daily-digest.json        # Workflow 2: Summarize → Telegram
│
├── scripts/
│   ├── convert-audio.sh        # ffmpeg WebM → MP3 conversion
│   ├── test-connections.sh     # Verify all APIs are reachable
│   ├── backup-db.sh            # Daily database backup
│   └── simulate-recording.sh   # Drop test file for workflow testing
│
├── MVP_PHASE0_TZ.md            # Original requirements doc
└── от_руководства.txt           # Original management instructions
```

---

## 9. Cost Estimate (Monthly) — UPDATED v1.1

| Component | Cost | Notes |
|-----------|------|-------|
| VPS (2 vCPU, 8 GB RAM) | ~2,500 RUB | Ubuntu 22.04 |
| Whisper (self-hosted) | **0 RUB** | Бесплатно, работает на VPS |
| GLM-4.7-FlashX API | ~300 RUB | ~$0.005 per summary |
| **TOTAL** | **~2,800 RUB/month** | |

> **Экономия 90%** по сравнению с первоначальным планом (27,500 → 2,800 руб).

---

## 10. Changes to Original TZ

### Added (not in original TZ)

1. **Self-hosted Whisper** — заменяет Yandex SpeechKit, экономит 25K руб/мес
2. **PostgreSQL tracker** — Idempotency: track processed files to avoid double transcription
3. **Cron scan instead of file watcher** — NFS + inotify = broken; polling is reliable

### Changed (v1.1 — Whisper update)

1. **STT engine**: Yandex SpeechKit → **self-hosted Whisper** (бесплатно, WebM нативно)
2. **Убраны**: Yandex Object Storage, format conversion, async polling workflow
3. **open-notebook port**: 3000 → **8888** (actual default port)
4. **GLM-4 endpoint**: `open.bigmodel.cn` → **`api.z.ai`** (current endpoint)
5. **GLM-4 model**: `glm-4-flash` → **`glm-4.7-flashx`** (better value, 200K context)
6. **File trigger**: `LocalFileTrigger` → **Schedule Trigger + folder scan** (reliability)
7. **Стоимость**: 27,500 → **2,800 руб/мес**

### Open Questions Resolved

1. **open-notebook API**: YES, has full REST API
2. **GLM-4 via n8n**: YES, OpenAI-compatible
3. **Whisper vs SpeechKit**: Whisper побеждает по всем критериям для этого MVP
4. **Yandex Cloud**: НЕ НУЖЕН — Whisper заменяет SpeechKit

### Still Open (НУЖЕН ОТВЕТ ОТ ТЕБЯ)

1. **NFS server IP and path** — ждём от руководителя (настроит Jibri)
2. **Telegram chat ID** — какой групповой чат для дайджестов?
3. **LEAD ID format** — только цифры? Из Bitrix24?

---

## 11. Telegram Chat History (Phase 1 — Архитектура)

> Ответ на вопрос: "Как оттуда каждый день будем получать инфу?"

### Проблема

Telegram Bot API **НЕ может читать историю сообщений**. Бот видит только:
- Сообщения, отправленные ПОСЛЕ добавления бота в чат
- И только через webhook (когда новое сообщение приходит)

### Решение: Webhook + Real-Time накопление

Вместо "каждый день вытягивать историю" — **копить сообщения в реальном времени**:

```
[Telegram группа с клиентом]
        │ (каждое новое сообщение)
        ▼
[Telegram Bot] ← webhook → [n8n Webhook Trigger]
        │
        ▼
[n8n Code node]
  - Извлечь: text, sender, timestamp, chat_id
  - Определить LEAD_ID из названия чата
        │
        ▼
[PostgreSQL: client_messages]
  - Сохранить каждое сообщение
        │
        ▼ (раз в сутки, 23:00)
[n8n Daily Workflow]
  - SELECT messages за сегодня по каждому клиенту
  - GLM-4 суммаризирует
  - Сохранить как Source в open-notebook
  - Включить в дайджест Telegram
```

### Как это настроить:

1. Добавить бота в каждый чат с клиентом (как участника или админа)
2. Настроить webhook в n8n: бот отправляет все новые сообщения в n8n
3. n8n сохраняет каждое сообщение в PostgreSQL
4. Ежедневно суммаризируем накопленные сообщения

### Альтернатива: Telethon (User API)

Если нужна **история до добавления бота**:
- Используется личный аккаунт Telegram (не бот)
- Python-скрипт с Telethon/Pyrogram
- Может читать ВСЮ историю чата
- **Риск**: Telegram может забанить аккаунт при агрессивном использовании
- **Рекомендация**: Использовать только для одноразовой миграции старых данных

### Что нужно от тебя:

1. **В каких чатах** общаетесь с клиентами? (группы, личные сообщения, каналы?)
2. **Нейминг чатов**: есть ли ID клиента в названии чата?
3. **Кто добавит бота** в чаты? (нужно право на это)

---

*Document created: 2026-02-18 | Author: AI Architecture Review*
