-- ============================================================
-- MVP Auto-Summary: Database Migration v2
-- Дата: 2026-02-26
-- Применить: docker exec mvp-autosummary-postgres-1 psql -U n8n -d n8n -f /scripts/migrate_db_v2.sql
-- ============================================================

-- 1. Добавляем колонку tasks_extracted для WF06 (deadline extractor)
ALTER TABLE processed_files ADD COLUMN IF NOT EXISTS tasks_extracted BOOLEAN DEFAULT FALSE;

-- Индекс для WF06 (только неза処理のfiles)
CREATE INDEX IF NOT EXISTS idx_processed_files_tasks_extracted 
    ON processed_files(tasks_extracted) 
    WHERE tasks_extracted = false;

-- 2. Добавляем dify_dataset_id в lead_chat_mapping для per-client RAG
ALTER TABLE lead_chat_mapping ADD COLUMN IF NOT EXISTS dify_dataset_id VARCHAR(200);

-- 3. system_settings — хранение глобальных настроек (ID общего датасета и т.д.)
CREATE TABLE IF NOT EXISTS system_settings (
    key        VARCHAR(100) PRIMARY KEY,
    value      TEXT NOT NULL,
    updated_at TIMESTAMP DEFAULT NOW()
);

-- 4. extracted_tasks — задачи и дедлайны из транскриптов (для WF06)
CREATE TABLE IF NOT EXISTS extracted_tasks (
    id          SERIAL PRIMARY KEY,
    lead_id     VARCHAR(50),
    source_file VARCHAR(255),
    task_desc   TEXT,
    assignee    VARCHAR(100),
    deadline    VARCHAR(100),
    context     TEXT,
    created_at  TIMESTAMP DEFAULT NOW(),
    status      VARCHAR(20) DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS idx_extracted_tasks_lead_id ON extracted_tasks(lead_id);
CREATE INDEX IF NOT EXISTS idx_extracted_tasks_status  ON extracted_tasks(status);

-- 5. client_summaries: добавляем file_path для .md файлов
ALTER TABLE client_summaries ADD COLUMN IF NOT EXISTS file_path VARCHAR(500);

-- 6. Обновляем curators для 6 клиентов (LEAD 4405, 987, 1381 — Евгений, остальные — уточнить)
UPDATE lead_chat_mapping SET curators = 'Евгений' WHERE lead_id IN ('4405', '987', '506') AND (curators IS NULL OR curators = '');
UPDATE lead_chat_mapping SET curators = 'Евгений, Кристина' WHERE lead_id IN ('1381') AND (curators IS NULL OR curators = '');
UPDATE lead_chat_mapping SET curators = 'Кристина' WHERE lead_id IN ('2048', '4550') AND (curators IS NULL OR curators = '');

-- 7. Промпты — убеждаемся что все 4 базовых промпта существуют
INSERT INTO prompts (name, prompt_text, is_active, created_by) VALUES
(
    'call_summary_prompt',
    'Ты бизнес-аналитик. Проанализируй транскрипцию(и) созвона с клиентом.

Выдай в формате Markdown:
## Резюме (2-3 предложения)

## Участники

## Ключевые договорённости
- Пункт 1
- Пункт 2

## Action Items
| Задача | Ответственный | Срок |
|--------|--------------|------|

## Риски и проблемы

## Тон клиента
(позитивный / нейтральный / негативный)

Не более 1500 слов. Только факты из текста.',
    true,
    'system'
)
ON CONFLICT (name) DO NOTHING;

INSERT INTO prompts (name, prompt_text, is_active, created_by) VALUES
(
    'chat_summary_prompt',
    'Ты куратор клиентского отдела фулфилмент-компании. Проанализируй переписку с клиентом в Telegram.

Выдай в формате Markdown:
## Резюме дня (2-3 предложения)

## Вопросы клиента
### Решённые ✅
- 

### Нерешённые ❓
- 

## Action Items для команды

## Тон клиента
(позитивный / нейтральный / негативный / требует внимания)',
    true,
    'system'
)
ON CONFLICT (name) DO NOTHING;

INSERT INTO prompts (name, prompt_text, is_active, created_by) VALUES
(
    'digest_prompt',
    'Ты бизнес-аналитик. Сформируй ежедневный дайджест по стенограммам встреч.

ФОРМАТ (строго HTML — используй <b>, <i>, не Markdown):

<b>Резюме дня</b> (3-5 предложений)

<b>Ключевые договорённости</b>
• Пункт

<b>Action Items</b>
• Задача — Кто — Срок

<b>Риски/блокеры</b>
• Пункт (или: Нет)

<b>По клиентам:</b>
• LEAD-XXXX: 1-2 ключевых пункта

Максимум 3000 символов.',
    true,
    'system'
)
ON CONFLICT (name) DO NOTHING;

INSERT INTO prompts (name, prompt_text, is_active, created_by) VALUES
(
    'report_prompt',
    'Ты аналитик отдела кураторов фулфилмент-компании. Тебе дают транскрипты созвонов.

КУРАТОРЫ: Евгений, Кристина, Анна (основные), Галина, Дарья (консультанты), Станислав, Андрей (руководители).

ФОРМАТ ОТЧЁТА (HTML):

<b>📊 Отчёт за [ДАТА]</b>

<b>👤 [КУРАТОР]:</b>
  • Созвонов: N (LEAD-XXXX)
  • Решённых вопросов: N — кратко
  • Открытых вопросов: N — кратко

Максимум 3500 символов.',
    true,
    'system'
)
ON CONFLICT (name) DO NOTHING;

-- Показываем результат
SELECT 'Migration v2 completed' AS result;
SELECT name, is_active, updated_at FROM prompts ORDER BY name;
