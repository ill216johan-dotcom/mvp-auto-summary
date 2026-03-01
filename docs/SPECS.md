# MVP Auto-Summary: Architecture & Specifications

> **Version:** 1.1 | **Date:** 2026-02-18  
> **Status:** E2E тест пройден. Whisper medium STT. Claude через z.ai.  
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
                    │            10 vCPU / 15 GB RAM               │
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
**API**: `POST http://whisper:8000/asr?task=transcribe&language=ru&output=json`

**Модели и ресурсы:**

| Модель | RAM | Скорость (60 мин) | WER русский |
|--------|-----|-------------------|-------------|
| tiny | +1 GB | ~5 мин | ~15% |
| base | +1 GB | ~10 мин | ~10% |
| small | +2 GB | ~20 мин | ~7% |
| **medium** | **+3 GB** | **~40 мин** | **~5%** |
| large-v3 | +5 GB | ~90 мин | ~3% |

**Рекомендация**: модель `medium` — баланс качества и скорости. VPS нужен 15 GB RAM (medium ~3.5GB + система).

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
| VPS (10 vCPU, 15 GB RAM) | ~4,000 RUB | Ubuntu, Xeon Gold 6240R |
| Whisper medium (self-hosted) | **0 RUB** | Бесплатно, ~3.5GB RAM |
| Claude 3.5 Haiku (z.ai) | ~500 RUB | ~$0.01 per summary |
| **TOTAL** | **~4,500 RUB/month** | |
> **Экономия 85%** по сравнению с первоначальным планом (27,500 → 4,500 руб).

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

## 11. Telegram Chat History — Архитектура и реализация

### Почему не бот

Telegram Bot API **не может читать историю** — бот видит только новые сообщения после добавления в чат. Чтобы получить переписку которая уже была — нужен **Telethon (User API)**: работает от имени обычного аккаунта и читает всю историю.

### Итоговая архитектура (2026-02-20)

```
Один рабочий Telegram-аккаунт
    (добавлен во все групповые чаты с клиентами)
            │
            ▼
  python export_telegram_chat.py
  (запускается на сервере, читает историю через Telethon)
            │
            ▼
  /exports/chats/LEAD-101_chat.json   ← полная история
            │
            ▼
  python import_chat_to_db.py
            │
            ▼
  PostgreSQL: таблица chat_messages
            │
            ▼  (каждый день в 22:00)
  Workflow 03 (n8n)
  → GLM-4 суммаризирует переписку за день
  → Сохраняет в client_summaries
            │
            ▼  (каждый день в 23:00)
  Workflow 02 (n8n)
  → Собирает все summaries
  → Отправляет дайджест в Telegram-бот @ffp_report_bot
```

### Как масштабировать на много клиентов

Используется таблица `lead_chat_mapping`: один раз заполняешь соответствие "договор ↔ чат", дальше скрипт автоматически обходит все записи.

```sql
-- Пример записи:
INSERT INTO lead_chat_mapping (lead_id, lead_name, chat_id, chat_title)
VALUES ('101', 'ООО Ромашка', -1009876543210, 'Ромашка — поставки');
```

Как получить chat_id чата: `python list_telegram_chats.py` — выведет все чаты с ID.

### Какой аккаунт использовать

| Вариант | Плюсы | Минусы |
|---------|-------|--------|
| Личный аккаунт менеджера | Уже есть доступ ко всем чатам | Личная переписка попадёт в систему, риск блокировки |
| Общий рабочий аккаунт | Безопасно, контролируемо | Нужно добавить в все группы вручную |

**Рекомендация**: общий рабочий аккаунт.

### Авторизация (один раз)

1. `python list_telegram_chats.py` на компьютере → QR-вход → вводишь пароль двухфакторки
2. Копируешь `mvp_session.session` на сервер через WinSCP
3. Больше авторизация не нужна — сессия хранится в файле

Подробнее про проблемы авторизации: см. E047–E052 в ERRORS.md

---

---

## 12. Статус развёртывания (2026-02-19, ФИНАЛЬНЫЙ)

### ✅ MVP ПОЛНОСТЬЮ РАБОТАЕТ

| Компонент | Статус | Примечания |
|-----------|--------|------------|
| PostgreSQL | ✅ Running | Healthy |
| SurrealDB | ✅ Running | v2, требует `chmod 777` на volume при первом запуске |
| Whisper STT | ✅ Running | Протестирован, транскрибирует русский язык (модель medium) |
| open-notebook | ✅ Running | UI на :8888, воркер стабилен |
| n8n | ✅ Running | UI на :5678, workflows активны |
| Telegram Bot | ✅ Работает | `@ffp_report_bot`, отправляет дайджесты |
| **Workflow 01** | ✅ Полностью работает | Файл → Whisper → open-notebook → PostgreSQL ✅ |
| **Workflow 02** | ✅ Полностью работает | PostgreSQL → GLM-4 → Telegram ✅ |

### ✅ Полный E2E тест пройден (2026-02-19)

**Workflow 01 (транскрипция):**
```
Тест: /mnt/recordings/2026/02/18/77777_2026-02-18_17-30.wav
Результат:
  ✅ n8n нашёл файл через List Recording Files
  ✅ Parse Filenames извлёк LEAD_ID
  ✅ Check If Already Processed — файл новый
  ✅ Mark as Transcribing — запись в PostgreSQL
  ✅ Whisper Transcribe — расшифровка
  ✅ Save Transcript to Notebook
  ✅ Mark Completed
```

**Workflow 02 (дайджест):**
```
Тест: Тестовые записи в processed_files (IDs 18, 19, 20)
Результат:
  ✅ Load Today's Transcripts → данные загружены
  ✅ Aggregate Transcripts → combined text готов
  ✅ Has Data? → true ветка
  ✅ GLM-4 Summarize → успешный ответ (thinking disabled)
  ✅ Build Digest → корректный дайджест
  ✅ Chunk for Telegram → разбиение на части
  ✅ Send Telegram → сообщение доставлено в @ffp_report_bot
  ✅ Mark Summary Sent → summary_sent = true
```

### 🔧 Исправленные проблемы (сессии 1-3)

| Проблема | Ошибка | Решение |
|----------|--------|---------|
| GLM-4 API баланс | E041 | Сменили на open.bigmodel.cn + рабочий ключ |
| Telegram $env заблокирован | E042 | Хардкодировали токен и chat_id в ноде |
| GLM-4 thinking mode | E043 | Добавили `thinking: {type: "disabled"}` |
| Build Digest пустой | E043 | Fallback на reasoning_content |
| Load Today's Transcripts стоп | E044 | Сброс summary_sent = false |
| INSERT без filepath | E045 | Добавили обязательное поле filepath |

### 📋 Что было сделано (summary)

**Сессия 1:**
- Развернута инфраструктура (docker-compose up)
- Исправлены E020-E040 (SurrealDB, n8n cookie, env vars)
- Workflow 01 протестирован и работает

**Сессия 2:**
- GLM-4 ключи перебраны, найден рабочий
- Сменён endpoint: api.z.ai → open.bigmodel.cn
- Telegram токен захардкожен в ноду
- Первый тест Workflow 02 — сообщение в Telegram получено

**Сессия 3:**
- Обнаружена проблема GLM-4 thinking mode (E043)
- Добавлен `thinking: {type: "disabled"}` в запрос GLM-4
- Добавлен fallback на reasoning_content в Build Digest
- Исправлена проблема с тестовыми данными (E044, E045)
- **Финальный E2E тест — УСПЕШНО ✅**

### 🔑 Доступы (сохранить в надёжном месте)

| Сервис | URL | Данные |
|--------|-----|--------|
| n8n UI | `http://84.252.100.93:5678` | `rod@zevich.ru` / `Ill216johan511lol2` |
| open-notebook | `http://84.252.100.93:8888` | Пароль из `.env` (`OPEN_NOTEBOOK_TOKEN`) |
| Telegram Bot | `@ffp_report_bot` | Token: `8527521201:AAHpyrPn4cig-zq0Xymt7lZ94qBIEXnYAeQ` |
| Telegram Chat ID | `-1003872092456` | Группа "Отчёты ФФ Платформы" |

### 🔑 GLM-4 API — рабочий ключ

| Ключ | Статус | Эндпоинт | Модель |
|------|--------|----------|--------|
| `fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6` | ✅ Рабочий | `https://open.bigmodel.cn/api/paas/v4/chat/completions` | `glm-4.7-flash` |

### ⚠️ Перед продакшеном

1. **Очистить тестовые данные**: `DELETE FROM processed_files WHERE filename LIKE 'TEST%' OR filename LIKE 'test%';`
2. **Подключить NFS** — когда руководитель настроит Jibri (записи реальных созвонов)
3. **Добавить healthcheck для SurrealDB** (см. секцию 13)

---

## 13. docker-compose.yml — рекомендуемые улучшения для продакшена

Добавить в `docker-compose.yml` перед деплоем:

```yaml
# 1. Healthcheck для SurrealDB (устраняет race condition с open-notebook)
surrealdb:
  healthcheck:
    test: ["CMD-SHELL", "printf 'GET /health HTTP/1.0\r\n\r\n' | nc localhost 8000 | grep -q 'ok' || exit 1"]
    interval: 10s
    timeout: 5s
    retries: 5
    start_period: 15s

# 2. open-notebook depends_on surrealdb healthy
open-notebook:
  depends_on:
    surrealdb:
      condition: service_healthy
```

---

---

## 14. Фаза 2: Telegram чаты + индивидуальные summaries (2026-02-20)

### 14.1. Новые компоненты

| Компонент | Описание |
|-----------|----------|
| `chat_messages` (PostgreSQL) | Хранит историю Telegram переписки по клиентам |
| `client_summaries` (PostgreSQL) | Хранит индивидуальные summaries (созвон / чат) |
| `Workflow 03` (n8n) | Генерирует индивидуальные summaries из звонков и чатов |
| `export_telegram_chat.py` | Выгрузка истории чата через Telethon (личный аккаунт) |
| `import_chat_to_db.py` | Импорт выгруженного чата в PostgreSQL |
| `generate_individual_summary.py` | Генерация summary на основе данных из БД (звонки + чаты) |
| `combine_client_data.py` | Объединение summaries и генерация daily digest |

### 14.2. Новые таблицы PostgreSQL

```sql
-- Таблица для хранения истории Telegram чатов
CREATE TABLE chat_messages (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR(50),
    chat_title VARCHAR(255),
    sender VARCHAR(100),
    message_text TEXT,
    message_date TIMESTAMP,
    imported_at TIMESTAMP DEFAULT NOW(),
    summary_sent BOOLEAN DEFAULT FALSE
);

-- Таблица для индивидуальных summaries
CREATE TABLE client_summaries (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR(50),
    source_type VARCHAR(20),  -- 'call' или 'chat'
    source_id INTEGER,
    summary_text TEXT,
    summary_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);
```

### 14.3. Workflow 03: Индивидуальные summaries

```
[Schedule 22:00]
    │
    ├── Load Today's Calls (processed_files)
    │       → Prepare Calls
    │       → GLM-4: Summarize Call (промпт для созвона)
    │       → Extract Call Summary → Save to client_summaries
    │
    └── Load Today's Chats (chat_messages, агрегация по lead_id)
            → Prepare Chats
            → GLM-4: Summarize Chat (промпт для чата)
            → Extract Chat Summary → Save to client_summaries
```

### 14.4. Как загрузить Telegram чаты

**Вариант A (рекомендуется): через скрипт (Telethon)**

```bash
# Шаг 1: Посмотреть список своих чатов (получить их ID)
cd /root/mvp-auto-summary/scripts
python3 list_telegram_chats.py
# Покажет все чаты с числовыми ID вида -1009876543210

# Шаг 2: Выгрузить конкретный чат по ID
python3 export_telegram_chat.py --chat -1009876543210 --lead-id 101
# Результат: exports/chats/LEAD-101_chat.json

# Шаг 3: Загрузить в базу
python3 import_chat_to_db.py --lead-id 101 --file ../exports/chats/LEAD-101_chat.json
```

**API credentials (получены 2026-02-20, вшиты в скрипты):**
- api_id: `32782815`
- api_hash: `a4c241e64433835b4a335b62520ab005`

**Таблица маппинга** `lead_chat_mapping`: связь договор ↔ Telegram чат.
Заполняется один раз вручную, потом используется для автоматической ежедневной выгрузки всех чатов.

**Вариант B (ручной): copy-paste из Telegram Desktop**

1. Открой чат → скопируй сообщения в текстовый файл
2. Сохрани как `LEAD-101_chat.txt` в формате `[ДД.ММ.ГГГГ ЧЧ:ММ] Имя: текст`
3. Загрузи через WinSCP в `/root/mvp-auto-summary/exports/chats/`
4. Запусти: `python3 import_chat_to_db.py --lead-id 101 --file LEAD-101_chat.txt --format txt`

### 14.5. Структура файлов summaries

```
/root/mvp-auto-summary/exports/summaries/2026-02-20/
├── LEAD-101_call_10-30_2026-02-20.md    ← summary созвона
├── LEAD-101_chat_2026-02-20.md          ← summary чата
├── LEAD-101_combined_2026-02-20.md      ← объединённое
├── LEAD-102_call_14-00_2026-02-20.md
├── LEAD-102_combined_2026-02-20.md
└── daily_digest_2026-02-20.md           ← краткий дайджест для Telegram
```

### 14.6. Полный порядок действий на 2026-02-20

```bash
# 1. Настройка сервера (один раз):
bash /root/mvp-auto-summary/scripts/setup_server_2026-02-20.sh

# 2. Загрузить аудио через WinSCP:
#    /mnt/recordings/2026/02/20/101_2026-02-20_10-30.mp3

# 3. Запустить транскрипцию (Workflow 01 в n8n UI):
#    http://84.252.100.93:5678 → Workflow 01 → Execute

# 4. Загрузить чаты:
python3 export_telegram_chat.py --chat "@клиент" --lead-id 101 ...
python3 import_chat_to_db.py --lead-id 101 --file LEAD-101_chat.json ...

# 5. Генерировать summaries:
python3 generate_individual_summary.py --lead-id all --source both --db-password ПАРОЛЬ

# 6. Финальный дайджест:
python3 combine_client_data.py --send-telegram --bot-token ТОКЕН --chat-id -1003872092456
```

---

---

## 15. Статус на 2026-02-20 (тестирование с реальными данными)

### Сессия 4 — что сделано (2026-02-20, утро)

| Действие | Результат |
|----------|-----------|
| Авторизован рабочий Telegram аккаунт (session_evgenii) | ✅ |
| Выгружены 6 чатов через export_telegram_chat.py | ✅ 3153 сообщения суммарно |
| Залиты в PostgreSQL (chat_messages) | ✅ |
| Заполнена таблица lead_chat_mapping | ✅ 6 записей |
| Сгенерированы summaries (--all-history) по всей истории | ✅ 6 .md файлов |
| Добавлено поле `curators` в lead_chat_mapping | ✅ (пустое, заполнить вручную) |
| ffmpeg статический бинарь установлен на хосте | ✅ `/usr/local/bin/ffmpeg` v7.0.2-static |
| ffmpeg проброшен в n8n контейнер через volume | ✅ работает внутри контейнера |
| Workflow 01 обновлён: ffmpeg → ogg → Whisper | ✅ (оба узла обновлены через API) |
| Workflow 01 обновлён: фильтр файлов > 100MB | ✅ |
| Workflow 01 обновлён: поддержка тире в имени файла | ✅ `4590-фф.webm` → lead_id=4590 |
| Дублирующие workflows деактивированы | ✅ активен только ZCtnggR6qrPy7bS6 |
| Whisper контейнер пересоздан (v1.4.0, medium модель) | ✅ faster-whisper v1.0.1 |
| Зависшие `transcribing` записи сброшены | ✅ processed_files чистый |
| docker-compose.yml синхронизирован с сервером | ✅ |

### Договоры в системе

Подробнее: см. `docs/CONTRACTS_AND_RAG.md`

| lead_id | Чат | Сообщений | Куратор |
|---------|-----|-----------|---------|
| 4405 | Фулфилмент Платформа ФФ-4405 | 1463 | ? |
| 987 | Фулфилмент ФФ-987 | 297 | ? |
| 1381 | ФФ-1381_ТМП/Юнна | 1341 | ? |
| 2048 | Александр ФФ-2048 | 2 | ? |
| 4550 | Александр ФФ-4550 | 38 | ? |
| 506 | Юлия ФФ-506 | 12 | ? |

> **Нужно заполнить**: поле `curators` в таблице `lead_chat_mapping`. Спросить у руководителя.

### Реальные аудиозаписи в /mnt/recordings/2026/02/20/

| Файл | Размер | lead_id | Статус |
|------|--------|---------|--------|
| 4590-фф.webm | 47MB | 4590 | ⏳ ожидает (< 100MB, будет обработан) |
| 1000023_ракурс техно.webm | 71MB | 1000023 | ⏳ ожидает (нет в lead_chat_mapping) |
| 2026-02-13T15_31_43.482Z.webm | 19MB | UNKNOWN | ⏳ ожидает (нет LEAD_ID) |
| 2048-ФФ.webm | 187MB | 2048 | ❌ пропущен (> 100MB) |
| 2239-фф.webm | 414MB | 2239 | ❌ пропущен (> 100MB) |
| 1000097_2026-02-13.webm | 978MB | 1000097 | ❌ пропущен (> 100MB) |
| 0_путь_писат.webm | 298MB | UNKNOWN | ❌ пропущен (> 100MB) |

> **Большие файлы** (> 100MB) превышают n8n execution timeout (30 мин при скорости 1.5x).
> Для них нужна отдельная ручная обработка или увеличение EXECUTIONS_TIMEOUT.

### Производительность Whisper (измерено 2026-02-20)

- **Модель**: medium (faster-whisper v1.0.1, CPU-only)
- **Скорость**: ~1.5x реального времени (45 сек на 30 сек аудио)
- **Качество**: отличное распознавание русского (пример: `"То есть вы еще ранее, да, работали?"`)
- **Рекомендация**: файлы > 30 минут не влезают в 30-минутный n8n таймаут

### Что нужно сделать дальше

| Задача | Приоритет | Кто делает |
|--------|-----------|------------|
| Запустить Workflow 01 вручную (кнопка Execute в n8n UI) | 🔴 HIGH | Вручную |
| Заполнить поле `curators` в lead_chat_mapping | 🟡 MEDIUM | Вручную (спросить у руководителя) |
| Переработать промпты GLM-4 (STATS_JSON + SUMMARY_MD) | 🟡 MEDIUM | Авто |
| Новый формат Telegram-дайджеста (по кураторам) | 🟡 MEDIUM | Авто |
| Поднять nginx на порту 8080 для раздачи .md файлов | 🟡 MEDIUM | Авто |
| Обработать большие файлы (> 100MB) вручную | 🟠 LOW | Вручную / Авто |

---

## 16. Архитектура ffmpeg в n8n (2026-02-20)

### Проблема

n8n использует Docker Hardened Images на Alpine (musl libc). Ubuntu-системный ffmpeg (glibc) несовместим.

### Решение

Статический ffmpeg бинарь (musl-совместимый) монтируется в контейнер:

```
Хост: /usr/local/bin/ffmpeg   (johnvansickle.com, v7.0.2-static, 77MB)
    ↓ volume mount (read-only)
Контейнер n8n: /usr/bin/ffmpeg   (работает нативно без доп. библиотек)
```

docker-compose.yml:
```yaml
volumes:
  - /usr/local/bin/ffmpeg:/usr/bin/ffmpeg:ro   # статический (musl-совместимый)
```

### Pipeline транскрипции (обновлён)

```
.webm файл (до 100MB)
    ↓ ffmpeg (внутри n8n контейнера)
    ↓ -vn -acodec libopus -b:a 32k → /tmp/audio_TIMESTAMP.ogg
    ↓ curl POST http://whisper:9000/asr
    ↓ JSON { text: "расшифровка..." }
    ↓ rm /tmp/audio_TIMESTAMP.ogg
    → PostgreSQL processed_files (status=completed)
    → open-notebook (сохранить транскрипт)
```

---

*Document created: 2026-02-18 | Updated: 2026-03-02 (сессия 5) — E2E тест, сервер 15GB/10CPU, Whisper medium, z.ai/Claude*

---

## 18. Текущее состояние системы (2026-03-02, после E2E теста)

### Серверные ресурсы (обновлены 2026-03-01)

| Параметр | Было | Стало |
|----------|------|-------|
| RAM | 7.8 GB | **15 GB** |
| CPU | ? | **10 cores (Xeon Gold 6240R)** |
| OS | Ubuntu 22.04 | Ubuntu 22.04 |
| IP | 84.252.100.93 | 84.252.100.93 |

### STT: Whisper self-hosted (medium)

- **Провайдер**: `STT_PROVIDER=whisper`
- **URL**: `http://whisper:8000` (внутри Docker network)
- **Модель**: `medium` (faster-whisper, ~3.5 GB RAM)
- **Качество**: Отличное распознавание русского (1574 символов из 2:12 аудио)
- **Скорость**: ~5 мин на 2:12 аудио (CPU-only)
- **Особенность**: НЕ галлюцинирует на тишине (возвращает 0 символов)
- **ВАЖНО**: `WHISPER_URL` должен быть `http://whisper:8000` (не 9000!)

### LLM: Claude 3.5 Haiku через z.ai

- **КРИТИЧНО**: Несмотря на имя переменных `GLM4_*`, API = **Anthropic Messages API**
- **Endpoint**: `POST https://api.z.ai/api/anthropic/v1/messages`
- **Модель**: `claude-3-5-haiku-20241022`
- **Авторизация**: `x-api-key` header + `anthropic-version: 2023-06-01`
- **НЕ OpenAI формат**: не `/chat/completions`, не `Authorization: Bearer`

### RAG: Dify.ai

- **UI**: `http://84.252.100.93` (порт 80)
- **Chatbot**: `http://84.252.100.93/chat/71pymtobibxuwqbc` (app: «ФФ Ассистент Куратора»)
- **App API key**: `app-UWjC7PoQEUMIPQB4ZlKRI1jh`
- **Dataset API key**: `dataset-k7rrBrS6TsEixGGIyAvywfb0`
- **Проблема**: Embedding-модель НЕ настроена → RAG на keyword-search → качество низкое
- **Контейнер embeddings**: `text-embeddings-inference` на порту 8081 (работает, но Dify не подключён)

### Архитектура STT: Strategy Pattern

```
transcribe_server.py
    ├── STTAdapter (абстрактный)
    │   ├── SpeechKitAdapter   → Yandex SpeechKit API
    │   ├── WhisperAdapter     → self-hosted faster-whisper (порт 8000)
    │   └── AssemblyAIAdapter  → AssemblyAI API
    │
    └── Выбор через .env: STT_PROVIDER=whisper|speechkit|assemblyai
```

Переключение провайдера: изменить `STT_PROVIDER` в `.env` → `docker compose up -d`.

### E2E тест — результаты (2026-03-02)

| Этап | Вход | Выход | Статус |
|------|------|-------|--------|
| WF01 | `4405_тестовый_2026-03-01.webm` (2:12) | 1574 символов транскрипт | ✅ |
| WF03 | Транскрипт | 1521 символ Markdown summary + Dify doc | ✅ |
| WF02 | Summary | Telegram message_id=350 | ✅ |
| Dify RAG | Вопрос через chatbot | Ошибка индексации | ⚠️ |

### Docker Compose — ключевое

- `docker compose restart` **НЕ** перезагружает `.env` — нужно `docker compose up -d`
- Все контейнеры имеют `restart: unless-stopped` — автостарт после reboot
- Whisper medium стабилен при 15GB RAM (ранее OOM при 7.8GB)

### Нерешённые проблемы

1. **Dify embedding**: Настроить Model Provider в Dify UI для векторного поиска
2. **WF03 API формат**: n8n хардкодит OpenAI формат, а LLM = Anthropic через z.ai
3. **WF01 retry timeout**: Транскрипт готов, но WF01 помечает как error (race condition)
4. **Большие файлы**: >30 мин аудио → timeout при транскрипции на CPU

*Обновлено: 2026-03-02*
