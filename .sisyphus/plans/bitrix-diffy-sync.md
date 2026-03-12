# Интеграция Битрикс24 CRM → Diffy (Ежедневная синхронизация)

## TL;DR

> **Quick Summary**: Создать ежедневную одностороннюю синхронизацию данных из Битрикс24 CRM в Diffy: звонки (метаданные + транскрипция через Whisper), письма (метаданные + ПОЛНЫЙ ТЕКСТ), комментарии сотрудников. Синхронизация И Лидов И Контактов из Битрикса → два блокнота на клиента в Diffy (BX-LEAD-* для периода продаж + LEAD-* для периода фулфилмента). Данные в PostgreSQL + Dify KB, саммари через Claude.
> 
> **Deliverables**:
> - Модуль `app/integrations/bitrix24.py` — клиент Bitrix24 REST API
> - Новые таблицы в PostgreSQL (bitrix_leads, bitrix_calls, bitrix_emails, bitrix_comments, bitrix_sync_log, bitrix_summaries)
> - Миграция `scripts/migrate_db_v3.sql`
> - Scheduled job `app/tasks/bitrix_sync.py` — ежедневная синхронизация
> - Scheduled job `app/tasks/bitrix_summary.py` — саммари данных Битрикса через Claude → Dify KB
> - Обновление конфигурации и точки входа
> 
> **Estimated Effort**: Medium-Large
> **Parallel Execution**: YES — 4 волны
> **Critical Path**: Task 1 → Task 3 → Task 5 → Task 6 → Task 12 → Task 13 → F1-F4

---

## Context

### Original Request
Подтягивать звонки, письма и комментарии сотрудников из Битрикс24 CRM в Diffy. Связь через пользовательское поле с номером договора (ФФ-XXXX). Данные должны быть доступны для RAG-поиска через Dify и суммаризироваться через Claude.

### Interview Summary
**Key Discussions**:
- **Связь лидов**: В Битриксе есть пользовательское поле (UF_*) с номером договора в формате "ФФ-4405", что соответствует LEAD-4405 в Diffy
- **Воронка**: Лид (отдел продаж) → Контакт (заезд на фулфилмент, номер договора). Лиды без договоров тоже нужны в Diffy
- **Частота**: Раз в день достаточно
- **Звонки**: Метаданные + транскрипция (через Whisper если нет в Битриксе)
- **Письма**: ПОЛНЫЙ ТЕКСТ + метаданные (тема, от/кому, дата, ТЕЛО) — критично для претензий клиентов
- **Комментарии**: Любые текстовые записи сотрудников на таймлайне лида
- **Хранение**: PostgreSQL + Dify KB для RAG
- **Саммари**: Claude генерирует ежедневную сводку по коммуникациям каждого лида

**Research Findings**:
- Diffy: Python 3.11, PostgreSQL 16, APScheduler, Docker Compose
- Bitrix API: webhook auth (бессрочный), 50 записей/стр, batch до 50 команд
- Звонки в двух местах: `crm.activity` (TYPE_ID=1) + `voximplant.statistic.get` (с URL записи)
- Записи звонков: поле `CALL_RECORD_URL` / `SRC_URL` в voximplant.statistic
- Транскрипция в Битрикс: не гарантирована → нужен fallback на Whisper
- Emails: `crm.activity` с TYPE_ID=4, поля SUBJECT, DIRECTION
- Comments: `crm.timeline.comment.list` (entityType="lead", entityId=N)
- Users: `user.get` для резолва RESPONSIBLE_ID → ФИО
- 4 из 8 таблиц Diffy не имеют DDL в репозитории → миграция должна быть самодостаточной

### Двойная сущность в Bitrix24 (CRITICAL)
**Битрикс: две сущности на клиента**:
- **Лид** (ID=123, без договора): период работы отдела продаж. Коммуникации (OWNER_TYPE_ID=1).
- **Контакт** (ID=456, с договором ФФ-4405): период после регистрации на фулфилменте. Коммуникации (OWNER_TYPE_ID=3).

**ВАЖНО**: Старые данные (из периода "Лида") **ОСТАЮТСЯ привязаны** к сущности "Лид" (ID=123). Новые данные (после регистрации) идут в сущность "Контакт" (ID=456). Это **ДВЕ РАЗНЫЕ записи** в CRM.

**Diffy: ДВА блокнота на клиента**:
- **BX-LEAD-123** (период лида, отдел продаж): звонки, письма, комменты из Bitrix Lead ID=123. Отдельный Dify dataset.
- **LEAD-4405** (период контакта, фулфилмент): звонки, письма, комменты из Bitrix Contact ID=456. Существующий Dify dataset (уже есть в Diffy).

**Синхронизация**: И Лидов (OWNER_TYPE_ID=1) И Контактов (OWNER_TYPE_ID=3) из Битрикса → два блокнота в Diffy.
### Metis Review
**Identified Gaps** (addressed):
- UF_* поле с номером договора: нужно определить его имя через `crm.lead.fields` перед началом синхронизации
- Лиды без договоров: нет номера ФФ → маппинг по Bitrix Lead ID (bitrix_lead_id)
- Транскрипция: нет гарантии наличия в Битриксе → скачиваем аудио + Whisper
- «Призрачные» таблицы: FK к lead_chat_mapping через строковый diffy_lead_id, не через FK constraint
- Дедупликация: нужен tracking уже синхронизированных записей (bitrix_activity_id)
- Batch-запросы: для эффективности при 100+ лидах

---

## Work Objectives

### Core Objective
Создать ежедневный pipeline: Bitrix24 API → PostgreSQL → Claude Summary → Dify KB, который автоматически подтягивает все коммуникации (звонки, письма, комментарии) по каждому лиду и делает их доступными для RAG-поиска и AI-сводок.

### Concrete Deliverables
- `app/integrations/bitrix24.py` — API клиент с пагинацией, batch, rate limiting
- `app/tasks/bitrix_sync.py` — scheduled job ежедневной синхронизации
- `app/tasks/bitrix_summary.py` — scheduled job для саммари + push в Dify
- `scripts/migrate_db_v3.sql` — новые таблицы для данных из Битрикса
- Обновление `app/config.py` — новые параметры конфигурации
- Обновление `app/scheduler.py` — регистрация новых jobs
- Обновление `app/main.py` — инициализация Bitrix-модуля
- Обновление `app/core/db.py` — SQL-запросы для новых таблиц

### Definition of Done
- [ ] `python -c "from app.integrations.bitrix24 import Bitrix24Client"` → no errors
- [ ] `psql -f scripts/migrate_db_v3.sql` → таблицы созданы без ошибок
- [ ] Ручной запуск синхронизации → данные появились в PostgreSQL
- [ ] Саммари сгенерировано через Claude и загружено в Dify KB
- [ ] Scheduler корректно регистрирует новые jobs

### Must Have
- Пагинация через все страницы (не терять данные >50 записей)
- Дедупликация — повторный запуск не создаёт дубликаты
- Маппинг лидов через UF_* поле с номером договора
- Создание новых лидов в Diffy для лидов Битрикса без договоров
- Обработка ошибок API (таймауты, 429 rate limit, 5xx)
- Логирование всех операций синхронизации
- Конфигурация через переменные окружения (не хардкод URL/ключей)

### Must NOT Have (Guardrails)
- НЕ хардкодить webhook URL или ключ API в коде (только через config/env)
- НЕ делать real-time синхронизацию / webhooks от Битрикса
- НЕ записывать данные обратно в Битрикс (только чтение)
- НЕ сохранять полный текст писем (только метаданные)
- НЕ создавать отдельный микросервис — встраиваем в существующий проект
- НЕ менять существующую логику транскрипций Jitsi
- НЕ создавать FK constraints к lead_chat_mapping (DDL неизвестна)
- НЕ использовать OAuth — только webhook auth
- НЕ писать избыточные комментарии или JSDoc (AI slop)
- НЕ создавать абстрактные "базовые классы" там где достаточно простой функции

---

## Verification Strategy

> **ZERO HUMAN INTERVENTION** — ALL verification is agent-executed. No exceptions.

### Test Decision
- **Infrastructure exists**: YES (частично — есть pytest в зависимостях)
- **Automated tests**: Tests-after (для ключевых модулей)
- **Framework**: pytest
- **Стратегия**: Unit-тесты для Bitrix24Client (mock HTTP), интеграционные тесты для DB-запросов

### QA Policy
Every task MUST include agent-executed QA scenarios.
Evidence saved to `.sisyphus/evidence/task-{N}-{scenario-slug}.{ext}`.

- **API Client**: Use Bash (python script) — вызвать реальный API, проверить ответ
- **Database**: Use Bash (psql) — проверить таблицы, данные, constraints
- **Scheduler**: Use Bash (python) — проверить регистрацию jobs
- **Summary**: Use Bash (python) — проверить генерацию саммари

---

## Execution Strategy

### Parallel Execution Waves

```
Wave 1 (Start Immediately — foundation):
├── Task 1: Конфигурация Bitrix24 (config.py, .env) [quick]
├── Task 2: Миграция БД v3 (новые таблицы) [quick]
├── Task 3: Bitrix24 API Client (базовый) [unspecified-high]
└── Task 4: Исследование UF_* поля договора [quick]

Wave 2 (After Wave 1 — core sync logic):
├── Task 5: Синхронизация лидов (маппинг + создание новых) [deep]
├── Task 6: Синхронизация звонков (мета + транскрипция) [deep]
├── Task 7: Синхронизация писем (метаданные) [quick]
└── Task 8: Синхронизация комментариев [quick]

Wave 3 (After Wave 2 — processing + integration):
├── Task 9: DB-запросы для новых таблиц (db.py) [unspecified-high]
├── Task 10: Саммари через Claude + push в Dify KB [deep]
└── Task 11: Транскрипция звонков через Whisper [deep]

Wave 4 (After Wave 3 — orchestration + wiring):
├── Task 12: Главный sync pipeline (оркестрация) [deep]
├── Task 13: Scheduler jobs + main.py wiring [quick]
└── Task 14: Тестирование с реальным API [unspecified-high]

Wave FINAL (After ALL tasks — verification):
├── Task F1: Plan compliance audit [oracle]
├── Task F2: Code quality review [unspecified-high]
├── Task F3: Real QA — полный цикл [unspecified-high]
└── Task F4: Scope fidelity check [deep]

Critical Path: Task 1 → Task 3 → Task 5 → Task 6 → Task 12 → Task 13 → F1-F4
Max Concurrent: 4 (Waves 1 & 2)
```

### Dependency Matrix

| Task | Depends On | Blocks | Wave |
|------|-----------|--------|------|
| 1 | — | 3, 4, 5-8 | 1 |
| 2 | — | 5-9 | 1 |
| 3 | 1 | 4, 5-8 | 1 |
| 4 | 1, 3 | 5 | 1 |
| 5 | 2, 3, 4 | 6-8, 12 | 2 |
| 6 | 2, 3, 5 | 11, 12 | 2 |
| 7 | 2, 3, 5 | 12 | 2 |
| 8 | 2, 3, 5 | 12 | 2 |
| 9 | 2 | 10, 12 | 3 |
| 10 | 6, 8, 9 | 12 | 3 |
| 11 | 6 | 12 | 3 |
| 12 | 5-11 | 13, 14 | 4 |
| 13 | 12 | 14 | 4 |
| 14 | 12, 13 | F1-F4 | 4 |

---

## TODOs

> Implementation + Test = ONE Task. Never separate.
> EVERY task MUST have: Agent Profile + Parallelization + QA Scenarios.

### Wave 1 — Foundation (Start Immediately)

- [ ] 1. Конфигурация Bitrix24 (config.py + .env)

  **What to do**:
  - Добавить в `app/config.py` (класс Settings на Pydantic) новые поля:
    - `BITRIX_WEBHOOK_URL: str` — полный URL вебхука
    - `BITRIX_CONTRACT_FIELD: str = ""` — имя UF_* поля с номером договора (определится в Task 4)
    - `BITRIX_SYNC_HOUR: int = 6` — час запуска ежедневной синхронизации
    - `BITRIX_SYNC_ENABLED: bool = True` — флаг включения/выключения
  - Добавить в `.env.example` примеры этих переменных с комментариями
  - НЕ менять существующие параметры конфигурации

  **Must NOT do**: Не хардкодить URL. Не менять существующие поля Settings.

  **Agent Profile**: `quick`, Skills: []
  **Parallelization**: Wave 1 (parallel) | Blocks: 3, 4, 5-8 | Blocked By: None

  **References**:
  - `app/config.py` — текущий класс Settings, паттерн добавления полей
  - `.env.example` — формат переменных окружения

  **Acceptance Criteria**:
  - [ ] `python -c "from app.config import settings; print(settings.BITRIX_WEBHOOK_URL)"` выводит URL
  - [ ] `.env.example` содержит все BITRIX_* переменные

  **QA Scenarios:**
  ```
  Scenario: Config loads correctly
    Tool: Bash (python)
    Steps: python -c "from app.config import settings; print(settings.BITRIX_WEBHOOK_URL)"
    Expected: URL printed without import errors
    Evidence: .sisyphus/evidence/task-1-config-load.txt

  Scenario: Missing required field
    Tool: Bash (python)
    Steps: Remove BITRIX_WEBHOOK_URL from .env, import config
    Expected: Pydantic ValidationError
    Evidence: .sisyphus/evidence/task-1-config-missing.txt
  ```

  **Commit**: YES (groups with Task 2) — `feat(bitrix): добавить конфигурацию и миграцию`

---

- [ ] 2. Миграция БД v3 — новые таблицы для данных Битрикса

  **What to do**:
  - Создать `scripts/migrate_db_v3.sql` с 6 таблицами (все CREATE TABLE IF NOT EXISTS):
    - **bitrix_leads**: bitrix_lead_id INT UNIQUE, diffy_lead_id VARCHAR(50), title, name, phone, email, status_id, responsible_id INT, responsible_name, contract_number, source_id, created_at, last_synced_at
    - **bitrix_calls**: bitrix_activity_id INT UNIQUE, bitrix_call_id VARCHAR(100), bitrix_lead_id INT, diffy_lead_id, direction INT (1=вх 2=исх), phone_number, call_duration INT (сек), call_date TIMESTAMPTZ, responsible_id/name, record_url TEXT, transcript_text TEXT, transcript_status VARCHAR(20) DEFAULT 'pending'
    - **bitrix_emails**: bitrix_activity_id INT UNIQUE, bitrix_lead_id INT, diffy_lead_id, direction INT, subject VARCHAR(1000), email_body TEXT (ПОЛНЫЙ текст письма HTML), email_from, email_to, email_date, responsible_id/name
    - **bitrix_comments**: bitrix_comment_id INT UNIQUE, bitrix_lead_id INT, diffy_lead_id, comment_text TEXT, author_id INT, author_name, comment_date
    - **bitrix_sync_log**: sync_type VARCHAR(30), status VARCHAR(20), leads/calls/emails/comments_synced INT, error_message TEXT, started_at, completed_at
    - **bitrix_summaries**: diffy_lead_id, summary_date DATE, calls/emails/comments_count INT, summary_text TEXT, dify_doc_id, UNIQUE(diffy_lead_id, summary_date)
  - НЕ использовать FK к существующим таблицам. Связь через строковый diffy_lead_id.

  **Must NOT do**: Не менять существующие таблицы. Не создавать FK constraints.

  **Agent Profile**: `quick`, Skills: []
  **Parallelization**: Wave 1 (parallel) | Blocks: 5-9 | Blocked By: None

  **References**:
  - `scripts/init-db.sql` — формат CREATE TABLE
  - `scripts/migrate_db_v2.sql` — паттерн миграций
  - `app/core/db.py` — naming convention

  **Acceptance Criteria**:
  - [ ] `psql -f scripts/migrate_db_v3.sql` создаёт 6 таблиц без ошибок
  - [ ] Повторный запуск — без ошибок (идемпотентность)

  **QA Scenarios:**
  ```
  Scenario: Migration creates all tables
    Tool: Bash (psql)
    Steps: psql -f migrate_db_v3.sql; SELECT tablename FROM pg_tables WHERE tablename LIKE 'bitrix_%'
    Expected: 6 rows: bitrix_calls, bitrix_comments, bitrix_emails, bitrix_leads, bitrix_summaries, bitrix_sync_log
    Evidence: .sisyphus/evidence/task-2-migration-tables.txt

  Scenario: Idempotency
    Tool: Bash (psql)
    Steps: Run migration twice
    Expected: No errors on second run
    Evidence: .sisyphus/evidence/task-2-migration-idempotent.txt
  ```

  **Commit**: YES (groups with Task 1)

---

- [ ] 3. Bitrix24 API Client — базовый модуль

  **What to do**:
  - Создать `app/integrations/__init__.py` (пустой)
  - Создать `app/integrations/bitrix24.py` с классом Bitrix24Client:
    - `__init__(self, webhook_url: str)` — URL + requests.Session
    - `call(method, params=None) -> dict` — один вызов с retry@429, logging, error handling
    - `call_list(method, params=None) -> list` — автопагинация через next (ВСЕ страницы)
    - `call_batch(commands: dict) -> dict` — batch до 50 команд
    - `get_leads(filter, select) -> list` — обёртка crm.lead.list
    - `get_activities(owner_type_id, owner_id, type_id=None) -> list` — crm.activity.list
    - `get_call_history(filter) -> list` — voximplant.statistic.get
    - `get_timeline_comments(entity_type, entity_id) -> list` — crm.timeline.comment.list
    - `get_users(user_ids) -> dict` — user.get с кэшированием
    - `get_lead_fields() -> dict` — crm.lead.fields
  - Использовать requests (уже в проекте) + logging. URL в конструктор (не из config).

  **Must NOT do**: Не хардкодить URL. Не создавать абстрактные базовые классы. Не импортировать config.

  **Agent Profile**: `unspecified-high`, Skills: []
  **Parallelization**: Wave 1 | Blocks: 4, 5-8 | Blocked By: Task 1

  **References**:
  - `app/core/dify_api.py` — паттерн API-клиента (requests, headers, error handling)
  - `app/core/telegram_api.py` — ещё один пример
  - Bitrix24 API: пагинация через next, batch POST /batch с cmd, при 429 sleep+retry

  **Acceptance Criteria**:
  - [ ] `python -c "from app.integrations.bitrix24 import Bitrix24Client; print('OK')"` -> OK
  - [ ] call('crm.lead.list') возвращает dict с result
  - [ ] call_list проходит пагинацию (все страницы)

  **QA Scenarios:**
  ```
  Scenario: Get leads from real API
    Tool: Bash (python)
    Steps: Create client, call('crm.lead.list', {'select': ['ID','TITLE'], 'start': 0})
    Expected: total > 0, result contains objects with ID and TITLE
    Evidence: .sisyphus/evidence/task-3-api-lead-list.txt

  Scenario: Auto-pagination
    Tool: Bash (python)
    Steps: call_list('crm.lead.list', {'select': ['ID']})
    Expected: len(result) == total
    Evidence: .sisyphus/evidence/task-3-api-pagination.txt

  Scenario: Error handling
    Tool: Bash (python)
    Steps: call('invalid.method.name')
    Expected: Exception with error description
    Evidence: .sisyphus/evidence/task-3-api-error.txt
  ```

  **Commit**: YES (groups with Task 4) — `feat(bitrix): создать API клиент Битрикс24`

---

- [ ] 4. Исследование UF_* поля с номером договора

  **What to do**:
  - Создать `scripts/bitrix_discover_fields.py`:
    - Вызвать crm.lead.fields -> все UF_* поля с человеческими названиями
    - Вызвать crm.lead.list с select: ['ID', 'TITLE', 'UF_*'] -> первые 10 лидов
    - Вывести таблицу: имя_поля | название | примеры_значений
    - Найти поле с 'ФФ-' -> рекомендация
    - Обновить .env.example с найденным BITRIX_CONTRACT_FIELD

  **Must NOT do**: Не хардкодить имя поля.

  **Agent Profile**: `quick`, Skills: []
  **Parallelization**: Wave 1 (после 1, 3) | Blocks: 5 | Blocked By: 1, 3

  **References**:
  - `app/integrations/bitrix24.py` (Task 3) — API клиент
  - Bitrix24 API: crm.lead.fields, crm.lead.list с select: ['UF_*']

  **Acceptance Criteria**:
  - [ ] Скрипт выводит UF_* поля с примерами значений
  - [ ] Найдено поле с номерами договоров
  - [ ] .env.example обновлён

  **QA Scenarios:**
  ```
  Scenario: Discover contract field
    Tool: Bash (python)
    Steps: python scripts/bitrix_discover_fields.py
    Expected: Found UF_CRM_* field with values like FF-4405
    Evidence: .sisyphus/evidence/task-4-discover-fields.txt

  Scenario: Field not found fallback
    Tool: Bash (python)
    Steps: If no field contains 'FF-'
    Expected: WARNING with full list of UF fields for manual selection
    Evidence: .sisyphus/evidence/task-4-discover-fallback.txt
  ```

  **Commit**: YES (groups with Task 3)

---

### Wave 2 — Core Sync Logic (After Wave 1)

- [ ] 5. Синхронизация Лидов И Контактов (маппинг Bitrix -> Diffy + создание двух блокнотов)

  **What to do**:
  - В `app/tasks/bitrix_sync.py` создать функции:
    - `sync_bitrix_leads(client, db_conn) -> dict`: синхронизация Битрикс "Лидов" (OWNER_TYPE_ID=1)
      - Получить все лиды: client.get_leads(select=['ID','TITLE','NAME','LAST_NAME','PHONE','EMAIL','STATUS_ID','SOURCE_ID','ASSIGNED_BY_ID'])
      - Получить сотрудников: client.get_users() для резолва responsible_id -> ФИО
      - Для каждого лида:
        - diffy_lead_id = "BX-LEAD-" + bitrix_lead_id (пример: BX-LEAD-123)
        - INSERT INTO bitrix_leads (bitrix_lead_id, diffy_lead_id, title, name, ...) ON CONFLICT DO UPDATE
        - Проверить lead_chat_mapping: если нет BX-LEAD-123 -> создать запись + Dify dataset
    - `sync_bitrix_contacts(client, db_conn) -> dict`: синхронизация Битрикс "Контактов" (OWNER_TYPE_ID=3)
      - Получить все контакты: client.call_list('crm.contact.list', select=[..., config.BITRIX_CONTRACT_FIELD])
      - Извлечь номер договора из UF_* поля
      - Для каждого контакта с договором:
        - diffy_lead_id = "LEAD-" + число из договора (ФФ-4405 -> LEAD-4405)
        - INSERT INTO bitrix_leads (bitrix_lead_id=bitrix_contact_id, diffy_lead_id, contract_number, ...) ON CONFLICT DO UPDATE
        - Проверить lead_chat_mapping: если нет LEAD-4405 -> создать + Dify dataset
    - `sync_leads_and_contacts()`: вызвать обе функции, вернуть объединённую статистику
  - Если один лид/контакт падает — логировать, продолжить
  - Return {bitrix_leads_synced: N, bitrix_contacts_synced: M, created: N+M, updated: K, errors: []}
  - Если один лид падает — логировать, продолжить

  **Must NOT do**: Не останавливать sync из-за одного лида. Не удалять данные.

  **Agent Profile**: `deep`, Skills: []
  **Parallelization**: Wave 2 | Blocks: 6-8, 12 | Blocked By: 2, 3, 4

  **References**:
  - `app/core/db.py` — паттерн SQL (psycopg2, cursor, conn.commit())
  - `app/tasks/scan_recordings.py` — паттерн task-функций
  - `scripts/migrate_db_v3.sql` (Task 2) — схема bitrix_leads
  - Bitrix API: crm.lead.list (OWNER_TYPE_ID=1), crm.contact.list (OWNER_TYPE_ID=3), обе с пагинацией

  **Acceptance Criteria**:
  - [ ] sync_leads_and_contacts() возвращает dict со статистикой
  - [ ] Битрикс Лиды маппятся на BX-LEAD-{id}
  - [ ] Битрикс Контакты с договором маппятся на LEAD-{contract_num}
  - [ ] Повторный запуск = upsert, не дубликаты

  **QA Scenarios:**
  ```
  Scenario: Sync Bitrix Leads + Contacts
    Tool: Bash (python + psql)
    Steps: sync_leads_and_contacts(); SELECT diffy_lead_id FROM bitrix_leads
    Expected: Есть diffy_lead_id формата BX-LEAD-* (лиды) и LEAD-* (контакты с договором)
    Evidence: .sisyphus/evidence/task-5-sync-leads-and-contacts.txt

  Scenario: Deduplication
    Tool: Bash (python + psql)
    Steps: sync_leads() twice; check count doesn't change
    Expected: Same count after second run
    Evidence: .sisyphus/evidence/task-5-dedup.txt
  ```

  **Commit**: YES (groups with 6, 7, 8) — `feat(bitrix): синхронизация лидов, звонков, писем, комментов`

---

- [ ] 6. Синхронизация звонков (метаданные + подготовка к транскрипции)

  **What to do**:
  - В `app/tasks/bitrix_sync.py` создать `sync_calls(client, db_conn, bitrix_leads) -> dict`:
    - Для каждого лида:
      - get_activities(owner_type_id=1, owner_id=lead_id, type_id=1) — звонки из CRM
      - get_call_history(filter={'CRM_ENTITY_TYPE':'LEAD','CRM_ENTITY_ID':lead_id}) — для CALL_RECORD_URL
      - INSERT INTO bitrix_calls ON CONFLICT (bitrix_activity_id) DO NOTHING
      - direction, phone_number, call_duration, call_date, record_url
      - transcript_status = 'pending' если record_url, 'no_record' если нет
    - Резолвить responsible_id через кэш
    - Batch-запросы для оптимизации

  **Must NOT do**: Не транскрибировать здесь (Task 11). Не качать аудио.

  **Agent Profile**: `deep`, Skills: []
  **Parallelization**: Wave 2 (parallel) | Blocks: 11, 12 | Blocked By: 2, 3, 5

  **References**:
  - Bitrix API: OWNER_TYPE_ID=1 (Lead), TYPE_ID=1 (Call), DIRECTION 1=in 2=out
  - voximplant.statistic.get: CALL_RECORD_URL / SRC_URL
  - `scripts/migrate_db_v3.sql` — схема bitrix_calls

  **Acceptance Criteria**:
  - [ ] Звонки сохранены в bitrix_calls
  - [ ] record_url заполнен для звонков с записью
  - [ ] transcript_status корректен
  - [ ] Дедупликация через UNIQUE

  **QA Scenarios:**
  ```
  Scenario: Sync calls
    Tool: Bash (python + psql)
    Steps: sync_calls(); SELECT direction, call_duration, record_url FROM bitrix_calls LIMIT 5
    Expected: Data filled, record_url present where available
    Evidence: .sisyphus/evidence/task-6-sync-calls.txt

  Scenario: Lead with no calls
    Tool: Bash (python)
    Steps: sync_calls() for lead without calls
    Expected: No errors, 0 records for that lead
    Evidence: .sisyphus/evidence/task-6-no-calls.txt
  ```

  **Commit**: YES (groups with 5, 7, 8)

---

- [ ] 7. Синхронизация писем (метаданные + ПОЛНЫЙ ТЕКСТ)

  **What to do**:
  - В `app/tasks/bitrix_sync.py` создать `sync_emails(client, db_conn, bitrix_leads) -> dict`:
    - Для каждого лида/контакта: get_activities(owner_type_id, owner_id, type_id=4) — Email (OWNER_TYPE_ID: 1=Lead, 3=Contact)
    - Извлечь: SUBJECT, DESCRIPTION (тело письма HTML), DIRECTION, START_TIME (email_date)
    - Для email_from/email_to: извлечь из полей активности (SETTINGS или EMAIL_META)
    - INSERT INTO bitrix_emails (subject, email_body, direction, email_from, email_to, email_date...) ON CONFLICT DO NOTHING

  **Must NOT do**: Не скачивать вложения (файлы). Сохранять только текст письма.

  **Agent Profile**: `quick`, Skills: []
  **Parallelization**: Wave 2 (parallel) | Blocks: 12 | Blocked By: 2, 3, 5

  **References**:
  - Bitrix API: crm.activity TYPE_ID=4 (Email), DIRECTION 1=вх 2=исх
  - `scripts/migrate_db_v3.sql` — схема bitrix_emails

  **Acceptance Criteria**:
  - [ ] Метаданные + тело письма в bitrix_emails
  - [ ] subject, email_body, direction, email_date заполнены
  - [ ] Тело HTML сохранено в email_body

  **QA Scenarios:**
  ```
  Scenario: Sync emails
    Tool: Bash (python + psql)
    Steps: sync_emails(); SELECT subject, LEFT(email_body, 100), direction FROM bitrix_emails LIMIT 5
    Expected: subject + email_body (первые 100 символов) + direction заполнены
    Evidence: .sisyphus/evidence/task-7-sync-emails.txt
  ```

  **Commit**: YES (groups with 5, 6, 8)

---

- [ ] 8. Синхронизация комментариев сотрудников

  **What to do**:
  - В `app/tasks/bitrix_sync.py` создать `sync_comments(client, db_conn, bitrix_leads) -> dict`:
    - Для каждого лида: get_timeline_comments(entity_type='lead', entity_id=lead_id)
    - Извлечь: comment (текст), createdBy (author_id), createdTime
    - Резолвить author_id -> author_name через кэш
    - INSERT INTO bitrix_comments ON CONFLICT DO NOTHING

  **Must NOT do**: Не фильтровать — сохранять все текстовые записи.

  **Agent Profile**: `quick`, Skills: []
  **Parallelization**: Wave 2 (parallel) | Blocks: 12 | Blocked By: 2, 3, 5

  **References**:
  - Bitrix API: crm.timeline.comment.list с ENTITY_TYPE='lead', ENTITY_ID=N
  - `scripts/migrate_db_v3.sql` — схема bitrix_comments

  **Acceptance Criteria**:
  - [ ] Комментарии в bitrix_comments
  - [ ] comment_text, author_name, comment_date заполнены

  **QA Scenarios:**
  ```
  Scenario: Sync comments
    Tool: Bash (python + psql)
    Steps: sync_comments(); SELECT author_name, comment_text FROM bitrix_comments LIMIT 5
    Expected: Text comments with author names
    Evidence: .sisyphus/evidence/task-8-sync-comments.txt

  Scenario: Lead without comments
    Tool: Bash (python)
    Steps: sync_comments() for lead with no comments
    Expected: No errors, 0 records
    Evidence: .sisyphus/evidence/task-8-no-comments.txt
  ```

  **Commit**: YES (groups with 5, 6, 7)

---

### Wave 3 — Processing + Integration (After Wave 2)

- [ ] 9. DB-запросы для новых таблиц (db.py)

  **What to do**:
  - Добавить в `app/core/db.py` функции (по паттерну существующих):
    - `save_bitrix_lead(conn, data)` — INSERT/upsert bitrix_leads
    - `save_bitrix_call(conn, data)` — INSERT ON CONFLICT DO NOTHING
    - `save_bitrix_email(conn, data)` — INSERT ON CONFLICT DO NOTHING
    - `save_bitrix_comment(conn, data)` — INSERT ON CONFLICT DO NOTHING
    - `get_bitrix_leads_for_sync(conn) -> list` — SELECT из bitrix_leads
    - `get_unsummarized_calls(conn, lead_id, date) -> list` — звонки без саммари
    - `get_unsummarized_comments(conn, lead_id, date) -> list`
    - `get_unsummarized_emails(conn, lead_id, date) -> list`
    - `get_calls_pending_transcription(conn) -> list` — WHERE transcript_status='pending'
    - `update_call_transcript(conn, call_id, text, status)` — UPDATE transcript
    - `save_bitrix_summary(conn, data)` — INSERT/upsert bitrix_summaries
    - `save_bitrix_sync_log(conn, data)` / `update_bitrix_sync_log(conn, id, ...)`
  - Все: параметризованные SQL, error handling, стиль 1:1 с существующим кодом

  **Must NOT do**: Не менять существующие функции. Не ORM. Raw SQL + psycopg2.

  **Agent Profile**: `unspecified-high`, Skills: []
  **Parallelization**: Wave 3 | Blocks: 10, 12 | Blocked By: Task 2

  **References**:
  - `app/core/db.py` — ВСЕ существующие функции (save_processed_file, get_lead_chat_mapping) — копировать стиль
  - `scripts/migrate_db_v3.sql` (Task 2) — DDL таблиц

  **Acceptance Criteria**:
  - [ ] Все функции импортируются без ошибок
  - [ ] SQL параметризованный (нет f-string SQL)
  - [ ] Стиль = существующий db.py

  **QA Scenarios:**
  ```
  Scenario: Save and read bitrix_lead
    Tool: Bash (python)
    Steps: save_bitrix_lead() with test data, get_bitrix_leads_for_sync()
    Expected: Record saved and readable
    Evidence: .sisyphus/evidence/task-9-db-lead.txt

  Scenario: ON CONFLICT dedup
    Tool: Bash (python)
    Steps: save_bitrix_call() twice with same bitrix_activity_id
    Expected: One record, no error
    Evidence: .sisyphus/evidence/task-9-db-dedup.txt
  ```

  **Commit**: YES — `feat(bitrix): добавить DB-запросы для данных Битрикса`

---

- [ ] 10. Саммари через Claude + push в Dify KB

  **What to do**:
  - Создать `app/tasks/bitrix_summary.py` с `generate_bitrix_summaries(db_conn, llm_client, dify_client)`:
    - Для каждого diffy_lead_id в bitrix_leads (WHERE NOT NULL):
      - Получить несуммаризированные за вчера: звонки (с транскрипцией), комменты, письма (мета)
      - Если нет новых данных — пропустить
      - Сформировать промпт для Claude:
        ```
        Проанализируй коммуникации с лидом {lead_name} за {date}:
        ЗВОНКИ ({N}): дата, направление, длительность, ответственный, [транскрипция]
        ПИСЬМА ({N}): дата, направление, тема, от/кому
        КОММЕНТАРИИ ({N}): автор, дата, текст
        Составь краткую сводку: ключевые темы, договорённости, следующие шаги.
        ```
      - Отправить в Claude -> получить summary_text
      - Сохранить в bitrix_summaries
      - Загрузить в Dify KB лида -> обновить dify_doc_id
  - Добавить промпт-шаблон в таблицу prompts

  **Must NOT do**: Не генерировать если нет новых данных. Не менять существующие промпты.

  **Agent Profile**: `deep`, Skills: []
  **Parallelization**: Wave 3 | Blocks: 12 | Blocked By: 6, 8, 9

  **References**:
  - `app/tasks/individual_summary.py` — ГЛАВНЫЙ паттерн саммари (Claude + Dify push)
  - `app/core/llm.py` — Claude API (generate_summary)
  - `app/core/dify_api.py` — Dify KB push (create_document_by_text)
  - `app/core/db.py` — get_lead_chat_mapping() для dify_dataset_id
  - `scripts/migrate_db_v2.sql` — паттерн INSERT промптов

  **Acceptance Criteria**:
  - [ ] Саммари генерируется для лида с данными
  - [ ] Сохраняется в bitrix_summaries, dify_doc_id обновлён
  - [ ] Лид без данных — пропускается

  **QA Scenarios:**
  ```
  Scenario: Generate summary for lead with data
    Tool: Bash (python)
    Steps: generate_bitrix_summaries() after sync
    Expected: summary_text not empty, dify_doc_id filled
    Evidence: .sisyphus/evidence/task-10-summary-generated.txt

  Scenario: Skip lead without new data
    Tool: Bash (python)
    Steps: Run again for same date
    Expected: Skip without errors
    Evidence: .sisyphus/evidence/task-10-summary-skip.txt
  ```

  **Commit**: YES (groups with Task 11) — `feat(bitrix): саммари через Claude и транскрипция Whisper`

---

- [ ] 11. Транскрипция звонков через Whisper

  **What to do**:
  - Создать `transcribe_pending_calls(db_conn, whisper_url)` (в bitrix_summary.py или отдельно):
    - SELECT звонки WHERE transcript_status='pending' AND record_url IS NOT NULL
    - Для каждого (лимит 20 за запуск):
      1. Скачать аудио с record_url (requests.get)
      2. Отправить в Whisper (POST multipart/form-data)
      3. Сохранить transcript_text, transcript_status='done'
      4. При ошибке: transcript_status='failed', логировать
    - Если record_url недоступен (403/404) -> 'failed', не повторять

  **Must NOT do**: Не менять логику транскрипции Jitsi. Не запускать Whisper параллельно.

  **Agent Profile**: `deep`, Skills: []
  **Parallelization**: Wave 3 | Blocks: 12 | Blocked By: Task 6

  **References**:
  - `app/tasks/scan_recordings.py` — паттерн Whisper (send_to_whisper)
  - `app/config.py` — WHISPER_URL уже есть
  - Whisper API: POST multipart/form-data с аудиофайлом

  **Acceptance Criteria**:
  - [ ] Звонки с record_url транскрибируются
  - [ ] transcript_text заполнен, status='done'
  - [ ] Ошибка -> status='failed'
  - [ ] Лимит 20 за запуск

  **QA Scenarios:**
  ```
  Scenario: Transcribe call with recording
    Tool: Bash (python)
    Steps: transcribe_pending_calls() for call with record_url
    Expected: transcript_text filled, status='done'
    Evidence: .sisyphus/evidence/task-11-transcribe-ok.txt

  Scenario: Unavailable recording
    Tool: Bash (python)
    Steps: transcribe_pending_calls() with invalid record_url
    Expected: status='failed', error logged
    Evidence: .sisyphus/evidence/task-11-transcribe-fail.txt
  ```

  **Commit**: YES (groups with Task 10)

---

### Wave 4 — Orchestration + Wiring (After Wave 3)

- [ ] 12. Главный sync pipeline (оркестрация всех шагов)

  **What to do**:
  - В `app/tasks/bitrix_sync.py` создать `run_bitrix_sync()`:
    - Entry point для scheduled job
    - Последовательность:
      1. bitrix_sync_log запись (status='started')
      2. Init Bitrix24Client из config
      3. sync_leads()
      4. sync_calls()
      5. sync_emails()
      6. sync_comments()
      7. transcribe_pending_calls() (до 20 шт)
      8. generate_bitrix_summaries()
      9. Обновить sync_log (status='completed', counts)
    - Если шаг падает — логировать, продолжить остальные
    - В конце: sync_log с итогами и ошибками
  - Опционально: Telegram-уведомление о результате

  **Must NOT do**: Не падать при ошибке одного шага. Не блокировать event loop.

  **Agent Profile**: `deep`, Skills: []
  **Parallelization**: Wave 4 | Blocks: 13, 14 | Blocked By: 5-11

  **References**:
  - `app/tasks/daily_digest.py` — паттерн orchestration
  - `app/tasks/individual_summary.py` — ещё один pipeline
  - `app/core/telegram_api.py` — уведомления

  **Acceptance Criteria**:
  - [ ] run_bitrix_sync() выполняет все шаги
  - [ ] sync_log со статистикой
  - [ ] Ошибка одного шага не останавливает остальные

  **QA Scenarios:**
  ```
  Scenario: Full sync cycle
    Tool: Bash (python)
    Steps: run_bitrix_sync()
    Expected: sync_log status='completed', counts > 0
    Evidence: .sisyphus/evidence/task-12-full-sync.txt

  Scenario: Partial failure resilience
    Tool: Bash (python)
    Steps: Invalid Whisper URL, run_bitrix_sync()
    Expected: Transcription fails, rest completes. sync_log has error
    Evidence: .sisyphus/evidence/task-12-partial-error.txt
  ```

  **Commit**: YES (groups with Task 13) — `feat(bitrix): pipeline в scheduler и main.py`

---

- [ ] 13. Scheduler jobs + main.py wiring

  **What to do**:
  - `app/scheduler.py`: добавить job с CronTrigger(hour=config.BITRIX_SYNC_HOUR), if BITRIX_SYNC_ENABLED
  - `app/main.py`: инициализировать Bitrix24Client (if enabled), добавить в startup
  - `docker-compose.yml`: добавить env variables если нужно
  - Следовать паттерну WF01-WF06

  **Must NOT do**: Не менять расписание существующих jobs.

  **Agent Profile**: `quick`, Skills: []
  **Parallelization**: Wave 4 | Blocks: 14 | Blocked By: 12

  **References**:
  - `app/scheduler.py` — add_job, CronTrigger, id, name паттерн
  - `app/main.py` — init_db, init_llm, init_dify паттерн
  - `docker-compose.yml` — env variables

  **Acceptance Criteria**:
  - [ ] BITRIX_SYNC_ENABLED=True -> job зарегистрирован
  - [ ] BITRIX_SYNC_ENABLED=False -> job не добавляется
  - [ ] main.py запускается без ошибок

  **QA Scenarios:**
  ```
  Scenario: Scheduler registers Bitrix job
    Tool: Bash (python)
    Steps: Start scheduler, check jobs list
    Expected: "bitrix_sync" job with CronTrigger
    Evidence: .sisyphus/evidence/task-13-scheduler-job.txt

  Scenario: Disabled via config
    Tool: Bash (python)
    Steps: BITRIX_SYNC_ENABLED=False, start scheduler
    Expected: No "bitrix_sync" job
    Evidence: .sisyphus/evidence/task-13-disabled.txt
  ```

  **Commit**: YES (groups with Task 12)

---

- [ ] 14. Тестирование с реальным API Битрикс24

  **What to do**:
  - Запустить полный run_bitrix_sync() с реальным API
  - Проверить каждую таблицу: bitrix_leads, bitrix_calls, bitrix_emails, bitrix_comments, bitrix_summaries, bitrix_sync_log
  - Проверить Dify KB: документы загружены
  - Проверить транскрипцию: хотя бы 1 звонок с transcript_text
  - Создать отчёт о результатах

  **Must NOT do**: Не модифицировать данные в Битриксе.

  **Agent Profile**: `unspecified-high`, Skills: []
  **Parallelization**: Wave 4 (после 13) | Blocks: F1-F4 | Blocked By: 12, 13

  **References**:
  - Все предыдущие Tasks
  - Реальный API: https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/

  **Acceptance Criteria**:
  - [ ] bitrix_leads > 0
  - [ ] bitrix_calls >= 0 (зависит от данных)
  - [ ] bitrix_summaries > 0
  - [ ] Dify KB обновлена
  - [ ] Отчёт создан

  **QA Scenarios:**
  ```
  Scenario: Full end-to-end test
    Tool: Bash (python + psql)
    Steps:
      1. run_bitrix_sync()
      2. SELECT count(*) FROM bitrix_leads/calls/emails/comments/summaries
      3. SELECT * FROM bitrix_sync_log ORDER BY id DESC LIMIT 1
    Expected: All counts reasonable, sync_log status='completed'
    Evidence: .sisyphus/evidence/task-14-e2e-test.txt

  Scenario: Lead mapping verification
    Tool: Bash (psql)
    Steps: SELECT bitrix_lead_id, diffy_lead_id, contract_number FROM bitrix_leads WHERE contract_number IS NOT NULL
    Expected: contract_number has 'FF-', diffy_lead_id matches 'LEAD-{number}'
    Evidence: .sisyphus/evidence/task-14-lead-mapping.txt
  ```

  **Commit**: YES — `test(bitrix): верификация с реальным API`

---

## Final Verification Wave

- [ ] F1. **Plan Compliance Audit** — `oracle`
  Read the plan end-to-end. For each "Must Have": verify implementation exists. For each "Must NOT Have": search codebase for forbidden patterns. Check evidence files exist.
  Output: `Must Have [N/N] | Must NOT Have [N/N] | Tasks [N/N] | VERDICT`

- [ ] F2. **Code Quality Review** — `unspecified-high`
  Run linter + type check. Check for: hardcoded credentials, empty catches, print() in prod, unused imports, AI slop.
  Output: `Build [PASS/FAIL] | Lint [PASS/FAIL] | Files [N clean/N issues] | VERDICT`

- [ ] F3. **Real QA — полный цикл** — `unspecified-high`
  Clean state. Full sync. Verify all tables. Verify Dify KB. Edge cases: empty lead, no calls.
  Output: `Scenarios [N/N pass] | Integration [N/N] | Edge Cases [N] | VERDICT`

- [ ] F4. **Scope Fidelity Check** — `deep`
  Each task: spec vs actual diff. 1:1 match. No scope creep. "Must NOT do" compliance.
  Output: `Tasks [N/N compliant] | Contamination [CLEAN/N] | Unaccounted [CLEAN/N] | VERDICT`

---

## Commit Strategy

| After Task(s) | Commit Message | Files |
|---------------|----------------|-------|
| 1, 2 | `feat(bitrix): добавить конфигурацию и миграцию БД` | config.py, .env.example, migrate_db_v3.sql |
| 3, 4 | `feat(bitrix): создать API клиент Битрикс24` | app/integrations/* |
| 5, 6, 7, 8 | `feat(bitrix): синхронизация лидов, звонков, писем, комментов` | app/tasks/bitrix_sync.py |
| 9 | `feat(bitrix): DB-запросы для данных Битрикса` | app/core/db.py |
| 10, 11 | `feat(bitrix): саммари Claude + транскрипция Whisper` | app/tasks/bitrix_summary.py |
| 12, 13 | `feat(bitrix): pipeline в scheduler и main.py` | scheduler.py, main.py |
| 14 | `test(bitrix): верификация с реальным API` | tests/ |

---

## Success Criteria

### Verification Commands
```bash
# Migration
psql -f scripts/migrate_db_v3.sql  # Expected: CREATE TABLE x6

# Module import
python -c "from app.integrations.bitrix24 import Bitrix24Client; print('OK')"  # OK

# API connection
python -c "
from app.integrations.bitrix24 import Bitrix24Client
c = Bitrix24Client('https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/')
r = c.call('crm.lead.list', {'select': ['ID'], 'start': 0})
print(f'Leads: {r.get(\"total\", 0)}')
"  # Leads: N (N > 0)

# Data after sync
psql -c "SELECT count(*) FROM bitrix_calls"  # > 0
psql -c "SELECT count(*) FROM bitrix_summaries"  # > 0
```

### Final Checklist
- [ ] Все "Must Have" присутствуют
- [ ] Все "Must NOT Have" отсутствуют
- [ ] API клиент работает с реальным Битрикс24
- [ ] Данные синхронизированы в PostgreSQL
- [ ] Саммари сгенерировано через Claude
- [ ] Данные загружены в Dify KB
- [ ] Scheduler запускает job по расписанию
- [ ] Нет хардкодированных credentials
- [ ] Повторный запуск не создаёт дубликатов
