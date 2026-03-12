# MVP Auto-Summary: Архитектура и Спецификации

> **Версия:** 4.2 | **Дата:** 2026-03-12
> **Статус:** Рабочая система — Phase 1 (Bitrix24 интеграция) завершена, **ИСПРАВЛЕН критический баг маппинга датасетов**
> **Сервер:** `root@84.252.100.93` (Ubuntu 22.04, 2 vCPU / 8 GB RAM)

---

## 1. Что делает система

Автоматическая система суммаризации и RAG-доступа к истории коммуникаций с клиентами фулфилмент-компании.

**Два канала коммуникаций:**

| Канал | Источник | Обработка |
|-------|---------|-----------|
| **Jitsi-звонки** | Jibri → NFS `/mnt/recordings` | Whisper → транскрипт → Claude summary → Dify |
| **Bitrix24 CRM** | REST API (лиды, контакты, звонки, письма, комментарии) | PostgreSQL → Claude summary → Dify |

**Итог для пользователя:** RAG-чат "ФФ Ассистент куратора" в Dify. Куратор пишет в свободной форме — "как там ФФ-4405?" — система ищет в блокноте клиента и отвечает по фактам.

---

## 2. Архитектура

```
                    ┌──────────────────────────────────────────────────┐
                    │           VPS root@84.252.100.93                 │
                    │              Ubuntu 22.04                         │
                    │         2 vCPU / 8 GB RAM / 40 GB SSD            │
                    │                                                  │
                    │  ┌─────────────────────────────────────────────┐ │
                    │  │            docker-compose                   │ │
                    │  │                                             │ │
                    │  │  ┌──────────────────────┐                  │ │
                    │  │  │   orchestrator       │                  │ │
                    │  │  │   (Python + APSched) │                  │ │
                    │  │  │   + Telegram Bot     │                  │ │
                    │  │  └──────────┬───────────┘                  │ │
                    │  │             │                               │ │
                    │  │  ┌──────────┴───────────┐                  │ │
                    │  │  │      PostgreSQL       │                  │ │
                    │  │  │       :5432           │                  │ │
                    │  │  │   DB: n8n, user: n8n  │                  │ │
                    │  │  └──────────────────────┘                  │ │
                    │  │                                             │ │
                    │  │  ┌──────────────────────┐                  │ │
                    │  │  │   transcribe         │                  │ │
                    │  │  │   (STT adapter :9001)│                  │ │
                    │  │  └──────────┬───────────┘                  │ │
                    │  │             │                               │ │
                    │  │  ┌──────────┴───────────┐                  │ │
                    │  │  │   Whisper (CPU)      │                  │ │
                    │  │  │   :8000 (profile)    │                  │ │
                    │  │  └──────────────────────┘                  │ │
                    │  │                                             │ │
                    │  │  ┌──────────────────────┐                  │ │
                    │  │  │  summaries-nginx     │                  │ │
                    │  │  │  :8181               │                  │ │
                    │  │  └──────────────────────┘                  │ │
                    │  └─────────────────────────────────────────────┘ │
                    │                                                  │
                    │  ┌────────────────┐  ┌────────────────────────┐ │
                    │  │ /mnt/recordings│  │ Dify (self-hosted)     │ │
                    │  │ NFS mount (ro) │  │ http://84.252.100.93   │ │
                    │  └────────────────┘  │ https://dify-ff.duck.. │ │
                    │                      └────────────────────────┘ │
                    └──────────────────────────────────────────────────┘
                              │                       │
                    ┌─────────▼─────────┐   ┌────────▼────────────┐
                    │  Claude (z.ai)    │   │  Bitrix24 CRM       │
                    │  Anthropic API    │   │  bitrix24.ff-plat.. │
                    │  claude-3-5-haiku │   │  Webhook REST API   │
                    └───────────────────┘   └─────────────────────┘
                              │
                    ┌─────────▼─────────┐
                    │  Telegram Bot API  │
                    │  @ffp_report_bot   │
                    └───────────────────┘
```

---

## 3. Ключевые архитектурные решения

### 3.1 Python Orchestrator вместо n8n (завершено 2026-03-04)

Полная замена n8n на Python. Причины:

| Проблема n8n | Решение Python |
|---|---|
| Workflow JSON — чёрный ящик | Код в git, читаемый Python |
| WF03 сломан (неправильный Anthropic API) | Единый LLMClient |
| Нет нормального retry/backoff | tenacity library |
| ~500MB RAM overhead | ~50MB RAM |
| JS + Python = 2 кодовые базы | Единый Python |

**Структура проекта:**
```
app/
├── main.py                    # Entry point
├── config.py                  # Pydantic Settings (env vars)
├── scheduler.py               # APScheduler (6 jobs)
├── integrations/
│   └── bitrix24.py            # Bitrix24 REST API client
├── core/
│   ├── db.py                  # PostgreSQL (800+ строк, Jitsi + Bitrix методы)
│   ├── llm.py                 # Claude API (Anthropic format)
│   ├── dify_api.py            # Dify KB API (create_dataset + create_document)
│   ├── telegram_api.py        # Telegram Bot API
│   └── logger.py              # Structlog
├── tasks/
│   ├── scan_recordings.py     # WF01: сканирование /recordings
│   ├── individual_summary.py  # WF03: саммари по Jitsi-звонкам
│   ├── deadline_extractor.py  # WF06: задачи и дедлайны
│   ├── daily_digest.py        # WF02: дайджест в Telegram
│   ├── bitrix_sync.py         # Bitrix: лиды/звонки/письма/комментарии
│   └── bitrix_summary.py      # Bitrix: Claude-саммари + Whisper + Dify
└── bot/
    └── handler.py             # WF04: Telegram бот команды
```

### 3.2 Whisper self-hosted (STT)

Self-hosted вместо Yandex SpeechKit (~25K руб/мес → 0 руб/мес).

- **Container**: `fedirz/faster-whisper-server:latest-cpu`
- **Port**: 8000 (внутри docker)
- **Model**: medium (3GB RAM, ~40 мин на 60 мин аудио)
- **API**: `POST http://whisper:8000/v1/audio/transcriptions`
- **Используется для**: Jitsi-записей (через transcribe сервис) + Bitrix voximplant-записей (прямо из bitrix_summary.py)

### 3.3 LLM: Claude 3.5 Haiku (z.ai)

- **Endpoint**: `https://api.z.ai/api/anthropic/v1/messages`
- **Format**: Anthropic Messages API (НЕ OpenAI-compatible!)
- **Auth**: `x-api-key` + `anthropic-version: 2023-06-01`
- **Env-переменные**: `LLM_API_KEY`, `LLM_BASE_URL`, `LLM_MODEL` (в коде); в `.env` называются `GLM4_API_KEY` и т.д. — исторически

### 3.4 Dify.ai для RAG

**Концепция**: Один RAG-чат для всех клиентов. Один блокнот (dataset) на клиента.

| Тип клиента | Имя блокнота | Пример |
|---|---|---|
| Контакт Bitrix с договором ФФ-NNNN | **ФФ-4405** | Извлекается из поля `title` |
| Лид Bitrix (продажники) | BX-LEAD-1035 | Технический |
| Клиент Jitsi (старая схема) | LEAD-42 | Через lead_chat_mapping |

**Важно**: "ФФ Ассистент куратора" — единый чат. Куратор пишет в свободной форме ("как там ФФ-4405?"), Dify ищет в нужном блокноте. Отдельный чат на каждого клиента не нужен.

**Каждый документ в блокноте начинается с шапки:**
```markdown
# Клиент: ФФ-4405
# Номер договора: ФФ-4405
```
Это гарантирует что RAG находит клиента даже по частичному упоминанию.

### 3.5 Bitrix24 CRM — двойная архитектура ID

```
Bitrix Lead   (crm.lead.list):
  если в title есть ФФ-номер   → diffy_lead_id = "ФФ-{num}" (regex: [ФфFf][ФфFf]-?(\d+))
  иначе                      → diffy_lead_id = "BX-LEAD-{lead_id}"

Bitrix Contact (crm.contact.list):
  если в title есть ФФ-номер   → diffy_lead_id = "ФФ-{num}"
  иначе                      → diffy_lead_id = "BX-CONTACT-{id}"
```

**Поле договора** — `UF_CRM_1632960743049`, формат значения: `ФФ-18`, `ФФ-4405`.
Подтверждено через `scripts/bitrix_discover_fields.py`.

**ФФ-номер из title:** Многие лиды не имеют заполненного поля договора, но в `TITLE` прописано "Иван, ФФ-4405". Функция `_extract_ff_number(title)` в `bitrix_summary.py` извлекает номер регулярным выражением `[ФфFf][ФфFf]-?(\d+)`.

---

## 4. Расписание задач

| ID | Время (MSK) | Задача | Файл |
|----|-------------|--------|------|
| WF01 | каждые 5 мин | Скан `/recordings` → транскрипция | `scan_recordings.py` |
| WF03 | 22:00 | Per-client summaries (Jitsi) | `individual_summary.py` |
| WF06 | 22:30 | Задачи и дедлайны из транскриптов | `deadline_extractor.py` |
| WF02 | 23:00 | Дайджест → Telegram | `daily_digest.py` |
| **BITRIX** | **06:00** | **Bitrix24 CRM полный синк** | `bitrix_sync.py` + `bitrix_summary.py` |
| WF04 | по запросу | Telegram бот команды | `bot/handler.py` |

**Текущий статус:** `jobs=6` в scheduler — подтверждено в логах.

---

## 5. База данных

### Jitsi-таблицы (оригинальные)

```sql
processed_files      -- аудиозаписи, статусы, транскрипты
chat_messages        -- история Telegram-переписки
client_summaries     -- ежедневные саммари (звонки + чаты)
lead_chat_mapping    -- lead_id ↔ chat_id ↔ dify_dataset_id
prompts              -- LLM-промпты с версионированием
extracted_tasks      -- задачи из транскриптов (WF06)
system_settings      -- глобальные настройки
```

### Bitrix-таблицы (добавлены migrate_db_v3.sql)

```sql
bitrix_leads         -- все лиды и контакты из Bitrix
                     -- поля: bitrix_lead_id, bitrix_entity_type, diffy_lead_id,
                     --       title, name, contract_number, phone, email,
                     --       responsible_id, stage_id, status_id, created_at,
                     --       dify_dataset_id ← Dify блокнот (ИСПРАВЛЕНО 2026-03-12)

bitrix_calls         -- звонки из crm.activity (TYPE_ID=1) + voximplant
                     -- поля: bitrix_activity_id, diffy_lead_id, direction,
                     --       call_duration, call_date, responsible_name,
                     --       record_url, transcript_text, transcript_status

bitrix_emails        -- письма из crm.activity (TYPE_ID=4), ПОЛНЫЙ ТЕКСТ
                     -- поля: bitrix_activity_id, diffy_lead_id, direction,
                     --       subject, email_body, email_from, email_to, email_date

bitrix_comments      -- комментарии из crm.timeline.comment.list
                     -- поля: bitrix_comment_id, diffy_lead_id,
                     --       comment_text, author_name, comment_date

bitrix_summaries     -- ежедневные Claude-саммари по лидам
                     -- поля: diffy_lead_id, summary_date,
                     --       calls_count, emails_count, comments_count,
                     --       summary_text, dify_doc_id
                     -- UNIQUE: (diffy_lead_id, summary_date)

bitrix_sync_log      -- лог каждого запуска синхронизации
                     -- поля: sync_type, status, leads_synced, calls_synced,
                     --       emails_synced, comments_synced, error_message,
                     --       started_at, completed_at
```

**Связь таблиц:**
- **Bitrix → Dify:** `bitrix_leads.dify_dataset_id` (✅ ИСПРАВЛЕНО 2026-03-12)
- **Telegram → Dify:** `lead_chat_mapping.dify_dataset_id` (только для Telegram чатов)

**ВАЖНО:** После исправления бага (2026-03-12):
- Bitrix данные используют `bitrix_leads.dify_dataset_id` ✅
- Telegram данные используют `lead_chat_mapping.dify_dataset_id` ✅
- Ранее был баг: Bitrix использовал `lead_chat_mapping` (неправильно) ❌

### Подключение к БД

```bash
# Снаружи (с хоста):
postgresql://n8n:ill216johan511lol2@localhost:5432/n8n

# Изнутри docker:
postgresql://n8n:ill216johan511lol2@postgres:5432/n8n

# psql команда:
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n
```

---

## 6. Bitrix24 синхронизация — подробно

### Что синхронизируется

| Шаг | API метод | Результат |
|-----|-----------|-----------|
| 1 | `crm.lead.list` | 30 324 лидов → `bitrix_leads` |
| 2 | `crm.contact.list` | 3 774 контактов → `bitrix_leads` |
| 3 | `crm.activity.list` (TYPE_ID=1) | Звонки → `bitrix_calls` |
| 4 | `voximplant.statistic.get` | URL записей звонков → `bitrix_calls.record_url` |
| 5 | `crm.activity.list` (TYPE_ID=4) | Письма (полный текст) → `bitrix_emails` |
| 6 | `crm.timeline.comment.list` | Комментарии → `bitrix_comments` |
| 7 | Whisper | Транскрипция записей звонков |
| 8 | Claude | Саммари по каждому лиду за каждую дату |
| 9 | Dify API | Создание датасетов + пуш документов |

### Первый запуск (историческая синхронизация)

**Запущена: 2026-03-09 23:11 MSK, PID 804062.**

Скрипт: `/root/mvp-auto-summary/scripts/run_historical_sync.py` (скопирован в контейнер как `/app/run_historical_sync.py`)

Лог: `/root/bitrix_sync.log`

```bash
# Следить за прогрессом:
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 "tail -50 /root/bitrix_sync.log"
```

### Конфигурация

```env
BITRIX_WEBHOOK_URL=https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/
BITRIX_CONTRACT_FIELD=UF_CRM_1632960743049
BITRIX_SYNC_HOUR=6
BITRIX_SYNC_ENABLED=True
```

---

## 7. Dify — блокноты клиентов

### Именование датасетов

| Условие | Имя в Dify | Пример |
|---------|-----------|--------|
| Контакт/лид с ФФ-номером в `title`, без `BX-LEAD-` | **ФФ-4405** | Поиск по `[ФфFf][ФфFf]-?(\d+)` |
| Лид (BX-LEAD-*) без ФФ-номера | BX-LEAD-1035 | Технический ID |
| Jitsi-клиент (старая схема) | LEAD-42 | Из lead_chat_mapping |

### Формат документа в Dify

Каждый документ имеет шапку:
```markdown
# Клиент: ФФ-4405
# Номер договора: ФФ-4405

## Резюме (2026-03-08)
(Claude-саммари за день)

## Звонки (3 шт.)
...

## Письма (2 шт.)
...
```

### Автосоздание датасетов

Реализовано в `bitrix_summary.py`. При первом саммари для лида:
1. Определяется имя: `ФФ-NNNN` (если есть) или `BX-LEAD-NNNN`
2. `dify.create_dataset(name)` → новый UUID
3. `db.save_bitrix_dataset_mapping(diffy_lead_id, dataset_id)` → запись в `bitrix_leads.dify_dataset_id` ✅
4. Все последующие документы пушатся в этот датасет

**ИСПРАВЛЕНО 2026-03-12:** Раньше использовался `lead_chat_mapping` (баг), теперь `bitrix_leads` (правильно).

---

## 8. Доступы

| Сервис | URL / Доступ |
|--------|-------------|
| **VPS** | `ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93` |
| **Dify UI** | `https://dify-ff.duckdns.org` |
| **Dify API** | `http://84.252.100.93/v1` (dataset API key в `.env`) |
| **Summaries** | `http://84.252.100.93:8181/summaries/` |
| **Telegram Bot** | `@ffp_report_bot` |
| **Telegram Chat** | `-1003872092456` ("Отчёты ФФ Платформы") |
| **Bitrix24** | `https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/` |

> SSH ключ: `C:\Users\User\.ssh\mvp_server`
> Пароль сервера: `xe1ZlW0Rpiyk`
> Подробнее: `docs/CREDENTIALS.md` (локально, в .gitignore)

---

## 9. Стоимость (ежемесячно)

| Компонент | Стоимость | Примечание |
|-----------|-----------|------------|
| VPS (2 vCPU, 8 GB) | ~2,500 руб | Ubuntu 22.04 |
| Claude 3.5 Haiku (z.ai) | ~300–3000 руб | Зависит от объёма саммари |
| Whisper (self-hosted) | **0 руб** | На VPS |
| Dify (self-hosted) | **0 руб** | На VPS |
| Bitrix24 | Уже оплачен | Только чтение по webhook |
| **ИТОГО** | **~2,800–5,500 руб** | Расчёт при 30к лидов |

> **Внимание**: при первой исторической синхронизации 30к лидов стоимость Claude API может быть выше — каждая дата активности генерирует отдельный вызов.

---

## 10. Telegram бот команды

| Команда | Действие |
|---------|----------|
| `/report` | Промежуточный отчёт по звонкам сегодня |
| `/status` | Статус системы + очереди + клиенты |
| `/rag` | Ссылка на Dify RAG-ассистент |
| `/help` | Справка по командам |

---

## 11. История версий

| Версия | Дата | Что сделано |
|--------|------|-------------|
| 1.0 | 2026-02-18 | Первый запуск n8n + Jitsi pipeline |
| 2.0 | 2026-03-04 | Миграция n8n → Python orchestrator (WF01-06) |
| 3.0 | 2026-03-09 | Bitrix24 интеграция: 6 таблиц, sync, Claude summaries, Whisper |
| **4.0** | **2026-03-09** | **Dify автосоздание датасетов, ФФ-именование блокнотов, историческая синхронизация** |
| **4.1** | **2026-03-10** | **Исправление ФФ-именования: экстракция из title при синке (bitrix_sync.py)** |

### v4.1 Детали (2026-03-10)

**Исправленные баги:**
- **E073**: Dify API `400 Bad Request` — убран `indexing_technique` из payload создания датасета
- **E074**: ФФ-именование не работало — `_extract_contract_number` добавлена в `bitrix_sync.py`
- **E076**: Контакты с договором назывались `LEAD-4405` — исправлено на `ФФ-4405`

**Изменения в `bitrix_sync.py`:**
```python
# Логика diffy_lead_id теперь в Step 1 (синк лидов):
ff_number = _extract_contract_number(lead.get("TITLE", ""))
diffy_lead_id = ff_number if ff_number else f"BX-LEAD-{lead_id}"
```

**Результат:**
- ~2,044 лидов из 31,005 теперь имеют `diffy_lead_id = "ФФ-XXXX"`
- Блокноты Dify создаются с правильными именами (`ФФ-4405` вместо `BX-LEAD-1035`)
- Куратор может спрашивать "как там ФФ-4405?" без технических ID

### v4.0 Детали (2026-03-09)

**Новые методы в `dify_api.py`:**
- `create_dataset(name)` — создаёт новый датасет в Dify через `POST /v1/datasets`

**Новые методы в `db.py`:**
- `save_dataset_mapping(lead_id, dataset_id)` — upsert в `lead_chat_mapping`
- `get_bitrix_activity_dates(diffy_lead_id)` — уникальные даты из calls + emails + comments (для исторической генерации саммари)

**Изменения в `bitrix_summary.py`:**
- `_extract_ff_number(title)` — извлекает `ФФ-NNNN` из названия лида
- `generate_bitrix_summaries(target_date=None)` — при `None` обрабатывает ВСЮ историю по датам
- Автосоздание Dify датасета при первом саммари для лида
- Шапка каждого документа: `# Клиент: ФФ-4405`
- Имя датасета: `ФФ-4405` для клиентов, `BX-LEAD-N` для лидов

**Добавлено в `requirements.txt`:**
- `requests>=2.31.0` (нужен для скачивания записей звонков в `bitrix_summary.py`)

---

## 12. Известные ограничения и открытые вопросы

| # | Описание | Статус |
|---|----------|--------|
| 1 | Историческая синхронизация 30к лидов — несколько часов | ✅ Завершена (2026-03-10 05:33, с ФФ-именованием) |
| 2 | Саммари генерируются только для лидов с activity (calls/emails/comments) | ✅ Ожидаемо |
| 3 | Записи Jitsi-звонков → отдельный pipeline (transcribe сервис), НЕ через bitrix_summary | ✅ Так и задумано |
| 4 | tmux не установлен на сервере — используется `nohup &` | ℹ️ Норм |
| 5 | Dify датасеты создаются при генерации саммари, НЕ при синке лидов | ℹ️ Намеренно (нет смысла создавать пустые датасеты) |

---

*Создано: 2026-02-18 | Обновлено: 2026-03-10 v4.1 — Исправление ФФ-именования, экстракция из title*
*Создано: 2026-02-18 | Обновлено: 2026-03-09 v4.0 — Dify автосоздание, ФФ-именование, историческая синхронизация*
