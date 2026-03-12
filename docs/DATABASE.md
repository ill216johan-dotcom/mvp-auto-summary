# 🗄️ База данных mvp-auto-summary — Полное руководство для новичка

> **Для кого эта документация**: Для тех, кто начинает изучать SQL и хочет практиковаться на реальном проекте.
> 
> **Что внутри**: Понятное объяснение каждой таблицы, примеры SQL-запросов, частые задачи.

---

## 📚 Оглавление

1. [Что такое база данных (БД)?](#что-такое-база-данных)
2. [Наша БД: PostgreSQL](#наша-бд-postgresql)
3. [Где находится БД](#где-находится-бд)
4. [Как подключиться к БД](#как-подключиться-к-бд)
5. [Структура БД: какие есть таблицы](#структура-бд)
6. [Таблицы проекта (mvp-auto-summary)](#таблицы-проекта)
7. [Таблицы n8n (устаревшие, но остались)](#таблицы-n8n)
8. [Примеры SQL-запросов для новичков](#примеры-sql-запросов)
9. [Частые задачи](#частые-задачи)
10. [Шпаргалка по командам](#шпаргалка)

---

## Что такое база данных?

**База данных (БД)** — это программа для хранения и поиска информации.

Представь Excel-таблицу:
- **Строки** — это записи (например, один клиент)
- **Столбцы** — это поля (имя, телефон, email)

БД работает так же, но:
- Умеет хранить **миллионы строк** без тормозов
- Позволяет делать **сложные поиски** (например, "все клиенты, купившие товар X в 2024 году")
- **Защищает данные** от потери (если программа упала — данные остались)

---

## Наша БД: PostgreSQL

**Тип БД**: PostgreSQL (сокращённо Postgres)  
**Версия**: 15

**Почему PostgreSQL?**
- Бесплатная (open-source)
- Надёжная (используется в крупных компаниях)
- Удобная для новичков (понятные сообщения об ошибках)

**Альтернативы** (для общей эрудиции):
- **MySQL** — тоже популярная, немного проще
- **SQLite** — супер-лёгкая, для маленьких проектов
- **MongoDB** — не табличная (хранит JSON), для других задач

---

## Где находится БД

### На сервере (production)

```
Сервер: 84.252.100.93
Контейнер Docker: mvp-auto-summary-postgres-1
Порт: 5432 (стандартный порт PostgreSQL)
База данных: n8n
Пользователь: n8n
Пароль: ill216johan511lol2
```

**Важно**: БД работает внутри Docker-контейнера. Это значит, что:
- Файлы БД изолированы от основной системы
- Легко делать бэкапы и переносить на другой сервер
- Если контейнер упадёт — достаточно перезапустить, данные сохранятся

### Локально (у тебя на компьютере)

Если захочешь развернуть локально для практики:
```bash
docker compose up -d postgres
```

---

## Как подключиться к БД

### Способ 1: Через SSH + psql (РЕКОМЕНДУЕТСЯ для новичков)

```bash
# Подключиться к серверу
ssh -i C:\Users\User\.ssh\mvp_server -o StrictHostKeyChecking=no root@84.252.100.93

# Войти в БД
docker exec -it mvp-auto-summary-postgres-1 psql -U n8n -d n8n
```

Теперь ты в **интерактивной консоли PostgreSQL** (psql). Можешь писать SQL-запросы.

**Выйти из psql**: `\q` + Enter

### Способ 2: Через DBeaver (графический интерфейс)

[DBeaver](https://dbeaver.io/) — бесплатная программа с красивым интерфейсом.

**Настройки подключения**:
- **Тип**: PostgreSQL
- **Хост**: `84.252.100.93`
- **Порт**: `5432`
- **База данных**: `n8n`
- **Пользователь**: `n8n`
- **Пароль**: `ill216johan511lol2`

**Плюсы DBeaver**:
- Видишь таблицы в дереве слева
- Можно редактировать данные как в Excel
- Подсветка синтаксиса SQL
- Автодополнение

### Способ 3: Из кода (Python)

```python
import psycopg2

conn = psycopg2.connect(
    host="84.252.100.93",
    port=5432,
    database="n8n",
    user="n8n",
    password="ill216johan511lol2"
)
cursor = conn.cursor()
cursor.execute("SELECT COUNT(*) FROM bitrix_leads")
print(cursor.fetchone())
```

---

## Структура БД

**Всего таблиц**: 74

**Категории**:
1. **Наш проект (mvp-auto-summary)** — 12 таблиц
2. **n8n (legacy)** — 62 таблицы (остались после миграции, но не используются)

---

## Таблицы проекта (mvp-auto-summary)

### 1. `bitrix_leads` — Лиды и контакты из Битрикс24

**Что хранит**: Информацию о клиентах из CRM (Битрикс24).

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | Уникальный номер записи (автоинкремент) |
| `bitrix_lead_id` | integer | ID в Битриксе (уникальный) |
| `bitrix_entity_type` | varchar(20) | Тип: `'lead'` (потенциальный клиент) или `'contact'` (клиент с договором) |
| `diffy_lead_id` | varchar(50) | ID для Dify блокнота (например, `ФФ-4405`, `BX-LEAD-12345`) |
| `title` | varchar(500) | Название лида (часто содержит ФФ-номер) |
| `name` | varchar(200) | Имя контакта |
| `phone` | varchar(100) | Телефон |
| `email` | varchar(200) | Email |
| `contract_number` | varchar(100) | Номер договора (например, `ФФ-4405`) |
| `created_at` | timestamp | Когда запись создана в нашей БД |
| `last_synced_at` | timestamp | Когда последний раз синхронизировались с Битриксом |

**Пример данных**:
```
id | bitrix_lead_id | bitrix_entity_type | diffy_lead_id | title                | contract_number
---+----------------+--------------------+---------------+----------------------+----------------
1  | 12345          | lead               | BX-LEAD-12345 | Иван Петров, ФФ-4405 | NULL
2  | 789            | contact            | ФФ-4405       | Иван Петров          | ФФ-4405
```

**SQL для начинающих**:
```sql
-- Посчитать сколько всего лидов
SELECT COUNT(*) FROM bitrix_leads;

-- Показать первых 10 лидов с номерами договоров
SELECT id, title, contract_number 
FROM bitrix_leads 
WHERE contract_number IS NOT NULL 
LIMIT 10;

-- Сколько лидов vs контактов
SELECT bitrix_entity_type, COUNT(*) 
FROM bitrix_leads 
GROUP BY bitrix_entity_type;
```

---

### 2. `bitrix_emails` — Письма из Битрикса

**Что хранит**: Переписку с клиентами по email.

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | ID записи |
| `bitrix_activity_id` | integer | ID активности в Битриксе |
| `bitrix_lead_id` | integer | К какому лиду/контакту относится |
| `direction` | integer | `1` = входящее, `2` = исходящее |
| `subject` | varchar(500) | Тема письма |
| `description` | text | Полный текст письма (HTML очищен) |
| `responsible_name` | varchar(200) | Кто ответственный (сотрудник) |
| `date` | timestamp | Дата отправки/получения |

**SQL примеры**:
```sql
-- Сколько писем всего
SELECT COUNT(*) FROM bitrix_emails;

-- Показать последние 5 входящих писем
SELECT subject, description, date 
FROM bitrix_emails 
WHERE direction = 1 
ORDER BY date DESC 
LIMIT 5;

-- Сколько писем по каждому лиду
SELECT bitrix_lead_id, COUNT(*) as emails_count
FROM bitrix_emails
GROUP BY bitrix_lead_id
ORDER BY emails_count DESC
LIMIT 10;
```

---

### 3. `bitrix_calls` — Звонки из Битрикса

**Что хранит**: История звонков клиентам.

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | ID записи |
| `bitrix_activity_id` | integer | ID в Битриксе |
| `bitrix_lead_id` | integer | К какому клиенту относится |
| `direction` | integer | `1` = входящий, `2` = исходящий |
| `duration` | integer | Длительность в секундах |
| `date` | timestamp | Когда был звонок |
| `recording_url` | varchar(1000) | Ссылка на запись звонка (если есть) |

**SQL примеры**:
```sql
-- Общее количество звонков
SELECT COUNT(*) FROM bitrix_calls;

-- Средняя длительность звонка
SELECT AVG(duration) as avg_seconds FROM bitrix_calls;

-- Самые долгие звонки
SELECT bitrix_lead_id, duration, date 
FROM bitrix_calls 
ORDER BY duration DESC 
LIMIT 5;
```

---

### 4. `bitrix_comments` — Комментарии сотрудников

**Что хранит**: Заметки менеджеров о клиентах.

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | ID записи |
| `bitrix_activity_id` | integer | ID в Битриксе |
| `bitrix_lead_id` | integer | К какому клиенту |
| `description` | text | Текст комментария |
| `responsible_name` | varchar(200) | Кто написал |
| `date` | timestamp | Когда написан |

**SQL примеры**:
```sql
-- Количество комментариев
SELECT COUNT(*) FROM bitrix_comments;

-- Кто больше всех пишет комментарии
SELECT responsible_name, COUNT(*) as comments_count
FROM bitrix_comments
GROUP BY responsible_name
ORDER BY comments_count DESC;
```

---

### 5. `bitrix_summaries` — Саммари по клиентам

**Что хранит**: Ежедневные сводки по клиентам, сгенерированные Claude AI.

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | ID записи |
| `bitrix_lead_id` | integer | Для какого клиента |
| `diffy_lead_id` | varchar(50) | ID блокнота Dify |
| `summary_date` | date | За какую дату саммари |
| `summary_text` | text | Текст саммари (Markdown) |
| `calls_count` | integer | Сколько звонков было в этот день |
| `emails_count` | integer | Сколько писем |
| `comments_count` | integer | Сколько комментариев |
| `dify_doc_id` | varchar(255) | ID документа в Dify (если загружено) |
| `created_at` | timestamp | Когда создано |

**SQL примеры**:
```sql
-- Количество саммари
SELECT COUNT(*) FROM bitrix_summaries;

-- Саммари за сегодня
SELECT * FROM bitrix_summaries 
WHERE summary_date = CURRENT_DATE;

-- Сколько саммари на каждого клиента
SELECT diffy_lead_id, COUNT(*) as summaries_count
FROM bitrix_summaries
GROUP BY diffy_lead_id
ORDER BY summaries_count DESC
LIMIT 10;
```

---

### 6. `bitrix_sync_log` — Лог синхронизации

**Что хранит**: Историю запусков синхронизации из Битрикса.

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | ID записи |
| `sync_type` | varchar(50) | Тип синхронизации (`leads`, `emails`, `calls`) |
| `status` | varchar(20) | Статус (`success`, `error`) |
| `items_synced` | integer | Сколько записей синхронизировано |
| `error_message` | text | Текст ошибки (если была) |
| `started_at` | timestamp | Когда начали |
| `completed_at` | timestamp | Когда закончили |

**SQL примеры**:
```sql
-- Последние 10 синхронизаций
SELECT * FROM bitrix_sync_log 
ORDER BY started_at DESC 
LIMIT 10;

-- Сколько синхронизаций было успешных vs ошибок
SELECT status, COUNT(*) 
FROM bitrix_sync_log 
GROUP BY status;
```

---

### 7. `processed_files` — Файлы Jitsi-записей

**Что хранит**: Записи созвонов из Jitsi (аудио/видео файлы).

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | ID записи |
| `filename` | varchar(500) | Имя файла (уникальное) |
| `filepath` | varchar(1000) | Полный путь на сервере |
| `lead_id` | varchar(100) | ID клиента (извлекается из названия файла) |
| `file_date` | date | Дата созвона |
| `status` | varchar(50) | Статус обработки (`new`, `queued`, `transcribing`, `completed`, `error`) |
| `transcript_text` | text | Транскрипция (текст из аудио) |
| `summary_text` | text | Саммари разговора |
| `dify_doc_id` | varchar(255) | ID документа в Dify |
| `created_at` | timestamp | Когда файл обнаружен |
| `updated_at` | timestamp | Последнее обновление |

**SQL примеры**:
```sql
-- Количество файлов по статусам
SELECT status, COUNT(*) 
FROM processed_files 
GROUP BY status;

-- Файлы сегодняшние
SELECT filename, status, created_at 
FROM processed_files 
WHERE file_date = CURRENT_DATE;

-- Файлы с ошибками
SELECT filename, error_message 
FROM processed_files 
WHERE status = 'error';
```

---

### 8. `lead_chat_mapping` — Соответствие лид ↔ Dify блокнот

**Что хранит**: Связь между клиентами и их блокнотами в Dify.

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | ID записи |
| `lead_id` | varchar(100) | ID клиента (уникальный) |
| `lead_name` | varchar(300) | Имя клиента |
| `dify_dataset_id` | varchar(255) | UUID блокнота в Dify |
| `created_at` | timestamp | Когда создан |
| `updated_at` | timestamp | Последнее обновление |

**SQL примеры**:
```sql
-- Сколько блокнотов создано
SELECT COUNT(*) FROM lead_chat_mapping;

-- Найти блокнот клиента ФФ-4405
SELECT * FROM lead_chat_mapping 
WHERE lead_id = 'ФФ-4405';
```

---

### 9. `prompts` — Промпты для LLM

**Что хранит**: Шаблоны промптов для Claude AI.

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | ID записи |
| `name` | varchar(100) | Название промпта (уникальное) |
| `prompt_text` | text | Текст промпта |
| `version` | integer | Версия |
| `is_active` | boolean | Активен ли промпт |
| `created_at` | timestamp | Когда создан |

**SQL примеры**:
```sql
-- Список всех промптов
SELECT name, version, is_active FROM prompts;

-- Посмотреть текст промпта для саммари
SELECT prompt_text FROM prompts 
WHERE name = 'call_summary_prompt' AND is_active = true;
```

---

### 10. `chat_messages` — Сообщения из Telegram-чатов

**Что хранит**: Переписку кураторов с клиентами в Telegram.

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | ID записи |
| `lead_id` | varchar(100) | ID клиента |
| `telegram_message_id` | bigint | ID сообщения в Telegram |
| `sender_name` | varchar(200) | Кто отправил |
| `message_text` | text | Текст сообщения |
| `message_date` | timestamp | Когда отправлено |
| `message_type` | varchar(50) | Тип (`text`, `photo`, `file`) |

**SQL примеры**:
```sql
-- Сколько сообщений в чате с ФФ-4405
SELECT COUNT(*) FROM chat_messages 
WHERE lead_id = 'ФФ-4405';

-- Последние 20 сообщений
SELECT sender_name, message_text, message_date 
FROM chat_messages 
ORDER BY message_date DESC 
LIMIT 20;
```

---

### 11. `client_summaries` — Сводки по клиентам (из Jitsi)

**Что хранит**: Ежедневные саммари из Jitsi-созвонов.

**Структура**: Похожа на `bitrix_summaries`, но для Jitsi-записей.

**SQL примеры**:
```sql
-- Количество саммари
SELECT COUNT(*) FROM client_summaries;

-- Саммари за последнюю неделю
SELECT * FROM client_summaries 
WHERE summary_date >= CURRENT_DATE - INTERVAL '7 days';
```

---

### 12. `extracted_tasks` — Извлечённые задачи

**Что хранит**: Задачи, извлечённые AI из транскрипций.

**Структура**:
| Столбец | Тип | Описание |
|---|---|---|
| `id` | integer | ID записи |
| `file_id` | integer | Ссылка на `processed_files.id` |
| `lead_id` | varchar(100) | ID клиента |
| `task_text` | text | Текст задачи |
| `priority` | varchar(20) | Приоритет (`high`, `medium`, `low`) |
| `deadline` | date | Дедлайн (если упомянут) |
| `extracted_at` | timestamp | Когда извлечено |

**SQL примеры**:
```sql
-- Все задачи с высоким приоритетом
SELECT * FROM extracted_tasks 
WHERE priority = 'high';

-- Задачи по клиенту
SELECT task_text, priority, deadline 
FROM extracted_tasks 
WHERE lead_id = 'ФФ-4405';
```

---

## Таблицы n8n (legacy, не используются)

После миграции с n8n на Python orchestrator осталось 62 таблицы n8n. Они НЕ используются в текущей работе, но **не удалены** (на всякий случай).

**Основные таблицы n8n** (для общего понимания):
- `workflow_entity` — сохранённые workflows (автоматизации)
- `execution_entity` — история запусков workflows
- `credentials_entity` — сохранённые API-ключи
- `user` — пользователи n8n

**Можно ли удалить?** Да, но осторожно — сначала убедись, что ничего не сломается.

---

## Примеры SQL-запросов для новичков

### Базовые команды

```sql
-- 1. ПОКАЗАТЬ ВСЁ из таблицы (первые 10 строк)
SELECT * FROM bitrix_leads LIMIT 10;

-- 2. ПОСЧИТАТЬ количество строк
SELECT COUNT(*) FROM bitrix_emails;

-- 3. НАЙТИ конкретную запись
SELECT * FROM bitrix_leads WHERE bitrix_lead_id = 12345;

-- 4. ОТФИЛЬТРОВАТЬ по условию
SELECT * FROM processed_files WHERE status = 'completed';

-- 5. ОТСОРТИРОВАТЬ (сначала новые)
SELECT * FROM bitrix_summaries ORDER BY created_at DESC LIMIT 5;
```

### Продвинутые запросы

```sql
-- 6. ОБЪЕДИНИТЬ таблицы (JOIN)
-- Показать саммари с именами клиентов
SELECT 
    bs.summary_date,
    bs.diffy_lead_id,
    bl.name,
    bs.summary_text
FROM bitrix_summaries bs
JOIN bitrix_leads bl ON bs.bitrix_lead_id = bl.bitrix_lead_id
LIMIT 10;

-- 7. ГРУППОВАЯ СТАТИСТИКА
-- Сколько писем на каждого менеджера
SELECT 
    responsible_name,
    COUNT(*) as emails_count
FROM bitrix_emails
GROUP BY responsible_name
ORDER BY emails_count DESC;

-- 8. ПОИСК ПО ТЕКСТУ
-- Найти письма с упоминанием "доставка"
SELECT * FROM bitrix_emails 
WHERE description LIKE '%доставка%';

-- 9. ДАТЫ
-- Активности за последние 7 дней
SELECT * FROM bitrix_emails 
WHERE date >= NOW() - INTERVAL '7 days';

-- 10. УСЛОВИЯ С AND/OR
SELECT * FROM bitrix_leads 
WHERE (contract_number IS NOT NULL) 
  AND (created_at >= '2024-01-01');
```

---

## Частые задачи

### Задача 1: Найти все коммуникации с клиентом ФФ-4405

```sql
-- Шаг 1: Найти bitrix_lead_id
SELECT bitrix_lead_id FROM bitrix_leads 
WHERE diffy_lead_id = 'ФФ-4405';

-- Предположим, нашли bitrix_lead_id = 789

-- Шаг 2: Найти все письма
SELECT * FROM bitrix_emails WHERE bitrix_lead_id = 789;

-- Шаг 3: Найти все звонки
SELECT * FROM bitrix_calls WHERE bitrix_lead_id = 789;

-- Шаг 4: Найти все комментарии
SELECT * FROM bitrix_comments WHERE bitrix_lead_id = 789;
```

### Задача 2: Посмотреть саммари за конкретную дату

```sql
SELECT 
    diffy_lead_id,
    summary_text,
    calls_count,
    emails_count
FROM bitrix_summaries
WHERE summary_date = '2026-03-09'
ORDER BY diffy_lead_id;
```

### Задача 3: Найти зависшие файлы (не обработались)

```sql
SELECT * FROM processed_files
WHERE status IN ('queued', 'transcribing')
  AND updated_at < NOW() - INTERVAL '1 hour';
```

### Задача 4: Топ-10 клиентов по количеству активностей

```sql
SELECT 
    bl.diffy_lead_id,
    bl.name,
    COUNT(DISTINCT be.id) as emails,
    COUNT(DISTINCT bc.id) as calls
FROM bitrix_leads bl
LEFT JOIN bitrix_emails be ON bl.bitrix_lead_id = be.bitrix_lead_id
LEFT JOIN bitrix_calls bc ON bl.bitrix_lead_id = bc.bitrix_lead_id
GROUP BY bl.diffy_lead_id, bl.name
ORDER BY (COUNT(DISTINCT be.id) + COUNT(DISTINCT bc.id)) DESC
LIMIT 10;
```

---

## Шпаргалка по командам

### Команды psql (интерактивная консоль)

```
\dt              — Показать все таблицы
\d table_name    — Структура таблицы (столбцы, типы)
\d+ table_name   — Подробная структура (+ индексы, триггеры)
\l               — Список всех баз данных
\du              — Список пользователей
\q               — Выйти из psql
```

### Команды SQL (работают везде)

```sql
SELECT     — Выбрать данные
INSERT     — Добавить новую запись
UPDATE     — Изменить существующую запись
DELETE     — Удалить запись
WHERE      — Фильтр
ORDER BY   — Сортировка
GROUP BY   — Группировка
LIMIT      — Ограничить количество строк
JOIN       — Объединить таблицы
```

### Бэкап и восстановление (через командную строку)

```bash
# Создать дамп БД
docker exec mvp-auto-summary-postgres-1 pg_dump -U n8n n8n > backup.sql

# Восстановить из дампа
docker exec -i mvp-auto-summary-postgres-1 psql -U n8n -d n8n < backup.sql
```

---

## Безопасность (важно!)

### ❌ НЕ ДЕЛАЙ:

```sql
-- НЕ удаляй все данные без WHERE
DELETE FROM bitrix_leads;  -- ❌ Удалит ВСЁ!

-- НЕ меняй структуру таблиц без понимания
ALTER TABLE bitrix_leads DROP COLUMN name;  -- ❌ Сломает код!

-- НЕ раскрывай пароль БД публично
-- (этот документ для внутреннего использования)
```

### ✅ БЕЗОПАСНО:

```sql
-- Всегда используй LIMIT при тестировании
SELECT * FROM bitrix_leads LIMIT 10;

-- Сначала проверяй, что изменишь (с WHERE)
SELECT * FROM bitrix_leads WHERE bitrix_lead_id = 12345;
-- Если всё ок, тогда UPDATE:
UPDATE bitrix_leads SET name = 'Новое имя' WHERE bitrix_lead_id = 12345;

-- Делай бэкапы перед любыми изменениями
```

---

## Полезные ссылки для изучения SQL

1. **[SQL Tutorial by W3Schools](https://www.w3schools.com/sql/)** — интерактивные уроки
2. **[PostgreSQL Documentation](https://www.postgresql.org/docs/)** — официальная документация
3. **[SQLBolt](https://sqlbolt.com/)** — упражнения для практики
4. **[PostgreSQL Exercises](https://pgexercises.com/)** — задачки на реальных примерах

---

## Итоги

Теперь ты знаешь:
- ✅ Что такое БД и почему PostgreSQL
- ✅ Как подключиться к нашей БД
- ✅ Какие таблицы есть и что они хранят
- ✅ Как писать базовые SQL-запросы
- ✅ Как решать частые задачи

**Следующий шаг**: Открой DBeaver, подключись к БД и попробуй выполнить примеры из этого документа. Экспериментируй, смотри результаты — так учится быстрее всего!

---

*Обновлено: 2026-03-10 — добавлены Bitrix-таблицы, примеры для новичков*
