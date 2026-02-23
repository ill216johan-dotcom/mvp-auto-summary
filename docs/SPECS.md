# MVP Auto-Summary: Architecture & Specifications

> **Version:** 2.0 | **Date:** 2026-02-22  
> **Status:** Phase 0 — MVP (ПОЛНОСТЬЮ РАБОТАЕТ, готов к тестированию)  
> **Strategy:** Buy over Build — no custom backend

---

## 1. Overview

System for automatic meeting transcription and summarization at a fulfillment company.

**What it does (Phase 0):**
1. Куратор проводит созвон в Jitsi (имя комнаты: `LEAD-{ID}-conf`)
2. Jibri записывает встречу → файл попадает на NFS-сервер
3. n8n каждые 5 мин сканирует `/recordings` → отправляет аудио в Яндекс SpeechKit (асинхронно)
4. SpeechKit транскрибирует → транскрипт сохраняется в open-notebook (ноутбук LEAD-{ID})
5. GLM-4 сразу делает саммари каждого созвона → тоже в open-notebook
6. Каждый день в 23:00: n8n собирает все транскрипты → GLM-4 делает дайджест → Telegram
7. Команда `/report` в Telegram → немедленный промежуточный отчёт по запросу

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
                    │  │  ┌──────────┐  ┌──────────────────────┐   │ │
                    │  │  │   n8n    │  │    open-notebook      │   │ │
                    │  │  │  :5678   │  │  UI:8888 / API:5055  │   │ │
                    │  │  └────┬─────┘  └──────────┬───────────┘   │ │
                    │  │       │                    │               │ │
                    │  │  ┌────┴────────────────────┴────┐         │ │
                    │  │  │          PostgreSQL           │         │ │
                    │  │  │            :5432              │         │ │
                    │  │  │  (n8n metadata + processed    │         │ │
                    │  │  │   files tracker)              │         │ │
                    │  │  └──────────────────────────────┘         │ │
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
                              │                         │
               ┌──────────────▼──────────┐  ┌──────────▼──────────┐
               │  Яндекс SpeechKit       │  │  ZhipuAI (GLM-4)    │
               │  (облачный STT API)     │  │  glm-4.7-flash      │
               │  - асинхронный          │  │  open.bigmodel.cn   │
               │  - polling              │  │  (бесплатно)        │
               └─────────────────────────┘  └─────────────────────┘
                                                        │
                                            ┌───────────▼──────────┐
                                            │  Telegram Bot API    │
                                            │  - Daily digest 23:00│
                                            │  - /report команда   │
                                            └──────────────────────┘
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
    → Read /mnt/recordings/**/*.{webm,mp3,wav}
    → Filter: NOT IN processed_files (PostgreSQL)
    → For each new file:
        → Mark as "transcribing" in DB
        → Send to Yandex SpeechKit (async)
        → Wait 3 min (n8n Wait node)
        → Poll SpeechKit until done
        → Save transcript to open-notebook
        → GLM-4 generates per-call summary → save to open-notebook
        → Mark as "completed" in DB
```

### 3.3. Яндекс SpeechKit — STT-движок (асинхронный)

**Используется**: Яндекс SpeechKit (облачный, асинхронный режим).

**Почему SpeechKit:**
- Высокое качество распознавания русского языка
- Асинхронный API: отправил → подождал → забрал результат
- Нет ограничений по размеру файла

**Flow транскрипции:**
```
1. Загрузить файл в Яндекс Object Storage (S3)
2. Отправить задание в SpeechKit (POST /speech/stt/v3/recognizeFileAsync)
3. Получить operationId
4. Wait node (ждать 3 мин)
5. Polling: GET /operations/{operationId} пока status != DONE
6. Извлечь текст из результата
```

**Ключевые параметры API:**
- `languageCode: "ru-RU"`
- `model: "general"` (общая модель, хорошо для деловых разговоров)
- `audioEncoding: "WEBM_OPUS"` (нативный формат Jibri, конвертация не нужна)

**Переменные окружения:**
- `YANDEX_API_KEY` — IAM-токен или API-ключ
- `YANDEX_FOLDER_ID` — ID папки в Яндекс Облаке
- `YANDEX_BUCKET` — имя S3-бакета для временного хранения аудио

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
| **n8n** | Оркестрация всех workflow (WF01-WF04) | 5678 | Метаданные в PostgreSQL |
| **open-notebook** | Хранение транскриптов + саммари, RAG, UI | UI:8888, API:5055 | SurrealDB |
| **PostgreSQL** | n8n persistence + processed files tracker | 5432 | Volumes |
| **SurrealDB** | БД open-notebook (граф + вектор) | 8000 | Volumes |
| **Яндекс SpeechKit** | STT (Speech-to-Text), асинхронный | External API | — |
| **Яндекс Object Storage** | Временное хранение аудио для SpeechKit | External S3 | — |
| **GLM-4 (ZhipuAI)** | Суммаризация созвонов + дайджест | External API | — |
| **Telegram Bot** | Отправка дайджестов + команда /report | External API | — |

---

## 5. Data Flow

### Workflow 01: New Recording → SpeechKit → open-notebook (каждые 5 мин)

**ID:** `bLd3WCDd8CEdkl54`

```
┌──────────────────┐
│ Schedule Trigger  │ ← Каждые 5 минут
│   */5 * * * *     │
└────────┬─────────┘
         │
┌────────▼─────────┐
│ Scan /recordings  │ ← find *.webm *.mp3 *.wav (новые первые)
└────────┬─────────┘
         │
┌────────▼──────────────────┐
│ Parse LEAD_ID              │ ← Regex: /^(\d+)_/
│ from filename              │   (напр. 1000023_имя.webm → 1000023)
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Check PostgreSQL           │ ← COUNT(*) processed_files
│ Is New File?               │   count=0 → новый файл
└────────┬──────────────────┘
         │ (только новые)
         │
┌────────▼──────────────────┐
│ Mark as Transcribing       │ ← INSERT status='transcribing'
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Upload to Yandex S3        │ ← PUT в Object Storage бакет
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Start SpeechKit Async      │ ← POST /speech/stt/v3/recognizeFileAsync
│                            │   Получить operationId
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Wait 3 min                 │ ← n8n Wait node (180 сек)
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Poll SpeechKit Status      │ ← GET /operations/{operationId}
│ (до DONE / ERROR)          │   Цикл пока status != DONE
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
│ Find/Create Notebook       │ ← GET /api/notebooks → найти LEAD-{ID}
│ (GET/POST open-notebook)   │   или создать новый
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Save Transcript to Notebook│ ← POST http://open-notebook:5055/api/sources/json
└────────┬──────────────────┘
         │
    ┌────┴────┐
    │ Save    │
    │ Success?│ ← проверяем $json.id notEmpty
    └────┬────┘
    yes  │  no
    ┌────┴────┐
    │         │
    ▼         ▼
┌────────┐ ┌───────┐
│GLM-4   │ │ Error │
│Summarize│ │ Mark  │
│per call│ └───────┘
└───┬────┘
    │
┌────▼──────────────────────┐
│ Save Call Summary          │ ← POST /api/sources/json (тип summary)
│ to Notebook                │
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Mark Completed             │ ← UPDATE status='completed'
└──────────────────────────┘
```

### Workflow 02: Daily Digest (23:00)

**ID:** `Bp0AB2bkAgui9Jxo`

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
│ GLM-4 Build Digest         │ ← POST /chat/completions (thinking disabled)
│ (отчёт по кураторам)       │   Евгений, Кристина, Анна, Галина,
└────────┬──────────────────┘   Дарья, Станислав, Андрей
         │
┌────────▼──────────────────┐
│ Save Summary to Notebooks  │ ← POST /api/sources/json для каждого клиента
│ (open-notebook)            │
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Chunk for Telegram         │ ← разбиение на части ≤3500 символов
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Send Telegram              │ ← POST /sendMessage
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Mark Summary Sent          │ ← UPDATE summary_sent=true
└──────────────────────────┘
```

### Workflow 03: Individual Summaries (22:00)

**ID:** `nrrobKTLlKNgZ37A`

Запускается в 22:00, сохраняет индивидуальные саммари в таблицу `client_summaries` PostgreSQL.

### Workflow 04: Telegram Bot Commands

**ID:** `wf04-bot-commands-001`

```
┌──────────────────┐
│ Schedule Trigger  │ ← Каждые 30 секунд (polling)
└────────┬─────────┘
         │
┌────────▼──────────────────┐
│ getUpdates                 │ ← GET Telegram API (offset tracking)
└────────┬──────────────────┘
         │
    ┌────┴────┐
    │ Has     │
    │Updates? │
    └────┬────┘
         │ yes
┌────────▼──────────────────┐
│ Filter /report command     │ ← только команды от авторизованных
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Load Unsent Transcripts    │ ← WHERE summary_sent=false
│ from PostgreSQL            │
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ GLM-4 Build Report         │ ← тот же промпт что WF02
└────────┬──────────────────┘
         │
┌────────▼──────────────────┐
│ Send to Telegram           │ ← POST /sendMessage
└──────────────────────────┘
```

---

## 6. Risk Analysis

### RED (Critical)

| Risk | Impact | Mitigation |
|------|--------|------------|
| **Яндекс SpeechKit API недоступен** | Транскрипции не создаются | Retry-логика; мониторинг через алерт в Telegram |
| **NFS mount drops** | Новые записи не обнаруживаются | Healthcheck workflow; алерт в Telegram |
| **Яндекс S3 квота/лимиты** | Загрузка аудио не работает | Мониторинг S3; очистка старых файлов |
| **open-notebook API changes** | Интеграция ломается | Пинить версию Docker-образа; тестировать перед апгрейдом |

### YELLOW (Medium)

| Risk | Impact | Mitigation |
|------|--------|------------|
| SpeechKit polling timeout (долгая обработка) | Транскрипт задерживается | Увеличить Wait node; реализовать retry |
| GLM-4 API нестабильность (Китай-хостинг) | Задержка дайджеста | Retry-логика; fallback на GLM-4.7-Flash (бесплатно) |
| open-notebook SurrealDB data loss | Потеря транскриптов | Ежедневный бэкап БД; оригинальные файлы сохранены на NFS |
| Дублирование обработки | Двойные расходы API | Идемпотентность через таблицу processed_files |

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
├── docker-compose.yml              # Infrastructure: n8n + open-notebook + DBs
├── .env.example                    # Environment variables template
├── .gitignore                      # Exclude .env, volumes, temp files
│
├── docs/
│   ├── SPECS.md                    # This file — architecture & decisions
│   ├── API.md                      # API contracts (external services)
│   ├── ERRORS.md                   # Known errors & troubleshooting
│   └── N8N_WORKFLOW_UPDATE.md      # Инструкция по обновлению workflows
│
├── n8n-workflows/
│   ├── 01-new-recording.json       # WF01: Scan → SpeechKit → open-notebook
│   └── 02-daily-digest.json        # WF02: Summarize → Telegram
│   (WF03 и WF04 — только в PostgreSQL n8n, не в файлах)
│
├── scripts/
│   ├── update_workflow02_digest_format.py  # Обновление GLM промпта WF02
│   ├── add_save_summary_node.py            # Добавил Save Summary в WF02
│   ├── add_per_call_summary.py             # Добавил GLM+Save в WF01
│   ├── create_wf04_via_db.py               # Создал WF04 (Telegram bot)
│   ├── export_telegram_chat.py             # Telethon (не интегрирован)
│   ├── import_chat_to_db.py                # Telethon (не интегрирован)
│   └── generate_individual_summary.py      # Telethon (не интегрирован)
│
├── MVP_PHASE0_TZ.md                # Original requirements doc
└── от_руководства.txt              # Original management instructions
```

---

## 9. Cost Estimate (Monthly) — UPDATED v2.0

| Component | Cost | Notes |
|-----------|------|-------|
| VPS (2 vCPU, 8 GB RAM) | ~2,500 RUB | Ubuntu 22.04 |
| Яндекс SpeechKit | ~500–2,000 RUB | Зависит от объёма созвонов (~1,5 руб/мин) |
| Яндекс Object Storage | ~50 RUB | Временное хранение аудио |
| GLM-4.7-Flash API | **0 RUB** | Бесплатная модель, достаточно для MVP |
| **TOTAL** | **~3,000–4,500 RUB/month** | |

---

## 10. Changes to Original TZ

### Added (не было в исходном ТЗ)

1. **PostgreSQL tracker** — идемпотентность: отслеживание обработанных файлов
2. **Cron scan вместо file watcher** — NFS + inotify = не работает; polling надёжнее
3. **Per-call summary** — GLM-4 делает саммари каждого созвона сразу (не ждёт вечернего дайджеста)
4. **Save Summary to Notebooks** — дневное саммари сохраняется в open-notebook каждого клиента
5. **Workflow 04** — Telegram бот с командой `/report` для промежуточного отчёта

### Resolved (вопросы закрыты)

1. **open-notebook API**: YES, есть полноценный REST API (порт 5055)
2. **open-notebook порты**: UI = :8888, API = :5055 (НЕ путать!)
3. **GLM-4 via n8n**: YES, OpenAI-compatible
4. **STT движок**: используется **Яндекс SpeechKit** (асинхронный, с polling)
5. **GLM-4 thinking mode**: отключён (`thinking: {type: "disabled"}`)
6. **Telegram webhook vs polling**: используем polling (getUpdates каждые 30 сек)
7. **Telegram chat ID**: `-1003872092456`

### Still Open (нужны действия)

1. **E2E тест** — файлы на диске есть, ждём когда WF01 подхватит и обработает
2. **Второй Telegram chat_id** — если нужна вторая группа (добавить бота в группу)
3. **Telethon интеграция** — скрипты готовы, не интегрированы в workflow

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

---

## 12. Статус развёртывания (2026-02-22, ТЕКУЩИЙ)

### ✅ Инфраструктура и workflows полностью настроены

| Компонент | Статус | Примечания |
|-----------|--------|------------|
| PostgreSQL | ✅ Running | Healthy |
| SurrealDB | ✅ Running | v2, требует `chmod 777` на volume при первом запуске |
| open-notebook | ✅ Running | UI на :8888, API на :5055, воркер стабилен |
| n8n | ✅ Running | UI на :5678, все 4 workflows активны |
| Telegram Bot | ✅ Работает | `@ffp_report_bot`, дайджесты + `/report` |
| **Workflow 01** | ✅ Настроен | Файл → SpeechKit (async+polling) → open-notebook + GLM саммари |
| **Workflow 02** | ✅ Настроен | PostgreSQL → GLM-4 → open-notebook → Telegram |
| **Workflow 03** | ✅ Активен | Индивидуальные саммари в 22:00 |
| **Workflow 04** | ✅ Активен | Telegram bot polling + /report команда |

### 🔧 Все исправленные проблемы (сессии 1-5)

| Проблема | Ошибка | Решение |
|----------|--------|---------|
| GLM-4 API баланс | E041 | Сменили на open.bigmodel.cn + рабочий ключ |
| Telegram $env заблокирован | E042 | Хардкодировали токен и chat_id в ноде |
| GLM-4 thinking mode | E043 | Добавили `thinking: {type: "disabled"}` |
| Build Digest пустой | E043 | Fallback на reasoning_content |
| Load Today's Transcripts стоп | E044 | Сброс summary_sent = false |
| INSERT без filepath | E045 | Добавили обязательное поле filepath |
| Save Success? всегда FALSE | E046 | Изменили проверку на `$json.id` notEmpty |
| 404 при сохранении в open-notebook | E047 | Правильный endpoint: `/api/sources/json`, порт 5055 |
| JSON parameter invalid | E048 | Переключить Body на Expression + JSON.stringify |
| WinSCP не обновляет workflow | E049 | n8n хранит workflow в PostgreSQL, не в файлах |
| Дубликаты ноутбуков | — | `$input.all()` вместо `$input.first()` в Find Client Notebook |
| open-notebook красная плашка | — | Добавлен `OPEN_NOTEBOOK_ENCRYPTION_KEY` в docker-compose |

### 📋 Что было сделано по сессиям

**Сессии 1-3:** Развёртывание инфраструктуры, первый E2E тест (с Whisper).

**Сессия 4 (2026-02-21):**
- Переход с Whisper на Яндекс SpeechKit (async + polling)
- Исправлена логика Save Success? (E046)
- Открыт порт 5055 для open-notebook API
- Исправлены порты docker-compose: 8888:8502 → 8888:8888 (UI)

**Сессия 5 (2026-02-22):**
- Добавлен per-call summary (GLM-4 сразу после транскрипции, WF01)
- Добавлена нода Save Summary to Notebooks в WF02
- Создан Workflow 04 (Telegram bot + /report)
- Исправлен баг с дубликатами ноутбуков (`$input.all()`)
- Добавлен `OPEN_NOTEBOOK_ENCRYPTION_KEY` (убрана красная плашка UI)
- Данные очищены для чистого E2E теста
- **Статус: готов к полному E2E тесту с реальными файлами SpeechKit**

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

## 14. ✅ РАБОЧАЯ КОНФИГУРАЦИЯ (проверено 2026-02-22)

### Workflow 01 — правильные URL нод

| Нода | URL |
|------|-----|
| Get Notebooks | `http://open-notebook:5055/api/notebooks` |
| Create Notebook | `http://open-notebook:5055/api/notebooks` |
| Save Transcript to Notebook | `http://open-notebook:5055/api/sources/json` |

**Порт 5055** — API open-notebook внутри Docker (не 8888 — это Web UI!)

### Save Transcript — правильный jsonBody

```javascript
={{ JSON.stringify({ 
  notebooks: [$json.notebookId], 
  type: "text", 
  content: $('Extract Transcript').first().json.transcript, 
  title: $('Extract Transcript').first().json.sourceTitle, 
  embed: true, 
  async_processing: false 
}) }}
```

### Как обновить workflow если что-то сломалось

**n8n НЕ читает файлы с диска!** Workflows хранятся в PostgreSQL.

**Способ 1 — через UI:**
1. n8n → workflow → ⋮ → Import from File
2. Выбери `.json` файл
3. Save!

**Способ 2 — исправить прямо в базе (через Python скрипт):**
```bash
# Посмотреть какой workflow активный и свежий
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "SELECT id, name, active, \"updatedAt\" FROM workflow_entity ORDER BY \"updatedAt\" DESC LIMIT 5;"

# Исправить URL через Python
cat > /tmp/fix.py << 'EOF'
import subprocess, json

result = subprocess.run([
    'docker', 'exec', 'mvp-auto-summary-postgres-1',
    'psql', '-U', 'n8n', '-d', 'n8n', '-t', '-A',
    '-c', "SELECT nodes::text FROM workflow_entity WHERE id = 'ВАШ_ID';"
], capture_output=True, text=True)

nodes = json.loads(result.stdout.strip())

for node in nodes:
    if node.get('name') == 'Save Transcript to Notebook':
        node['parameters']['url'] = 'http://open-notebook:5055/api/sources/json'
        node['parameters']['jsonBody'] = """={{ JSON.stringify({ notebooks: [$json.notebookId], type: "text", content: $('Extract Transcript').first().json.transcript, title: $('Extract Transcript').first().json.sourceTitle, embed: true, async_processing: false }) }}"""

sql = f"UPDATE workflow_entity SET nodes = '{json.dumps(nodes).replace(chr(39), chr(39)+chr(39))}'::json WHERE id = 'ВАШ_ID';"
subprocess.run(['docker', 'exec', '-i', 'mvp-auto-summary-postgres-1', 'psql', '-U', 'n8n', '-d', 'n8n'], input=sql, text=True)
print("Done!")
EOF
python3 /tmp/fix.py
```

### Диагностика за 30 секунд

```bash
# 1. Все контейнеры живы?
docker ps --format "table {{.Names}}\t{{.Status}}"

# 2. Файлы обрабатываются?
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT id, filename, status FROM processed_files ORDER BY id DESC LIMIT 5;"

# 3. open-notebook API работает?
docker exec mvp-auto-summary-open-notebook-1 curl -s http://localhost:5055/api/notebooks | head -100

# 4. Логи open-notebook (ищи ошибки)
docker logs mvp-auto-summary-open-notebook-1 --tail=30

# 5. Зависшие файлы (transcribing > 30 мин)
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT filename, status, created_at FROM processed_files WHERE status='transcribing' AND created_at < NOW() - INTERVAL '30 minutes';"
```

### Починить зависшие файлы

```bash
# Сбросить зависшие transcribing → чтобы workflow подхватил снова
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "DELETE FROM processed_files WHERE status='transcribing' AND created_at < NOW() - INTERVAL '30 minutes';"
```

---

*Document created: 2026-02-18 | Updated: 2026-02-22 — ПОБЕДА! Workflow 01 полностью работает. Добавлена рабочая конфигурация и инструкции по восстановлению.*
