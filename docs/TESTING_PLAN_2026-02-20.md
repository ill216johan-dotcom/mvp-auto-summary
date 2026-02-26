# План тестирования MVP: Реальные данные

> **Дата:** 2026-02-20  
> **Цель:** Протестировать систему на реальных данных (созвоны + чаты)  
> **Время:** ~2-3 часа

---

## 🎯 Конечная цель проекта (context)

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           MVP Auto-Summary v2.0                              │
│                                                                             │
│  ┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐        │
│  │  Созвоны (Jitsi) │    │ Telegram чаты   │    │  Email/Bitrix   │        │
│  │  → Whisper       │    │ → Telethon      │    │  → API          │        │
│  └────────┬────────┘    └────────┬────────┘    └────────┬────────┘        │
│           │                      │                      │                  │
│           └──────────────────────┼──────────────────────┘                  │
│                                  ▼                                         │
│                    ┌─────────────────────────┐                             │
│                    │   PostgreSQL + RAG      │                             │
│                    │   (open-notebook)       │                             │
│                    └────────────┬────────────┘                             │
│                                 │                                          │
│           ┌─────────────────────┼─────────────────────┐                    │
│           ▼                     ▼                     ▼                    │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐          │
│  │  LEAD-101       │   │  LEAD-102       │   │  LEAD-103       │          │
│  │  ┌───────────┐  │   │  ┌───────────┐  │   │  ┌───────────┐  │          │
│  │  │ Созвон 1  │  │   │  │ Созвон 1  │  │   │  │ Чат 1     │  │          │
│  │  │ Созвон 2  │  │   │  │ Чат 1     │  │   │  │ Email 1   │  │          │
│  │  │ Чат 1     │  │   │  │ Email 1   │  │   │  │ ...       │  │          │
│  │  │ Summary   │  │   │  │ Summary   │  │   │  │ Summary   │  │          │
│  │  └───────────┘  │   │  └───────────┘  │   │  └───────────┘  │          │
│  │                 │   │                 │   │                 │          │
│  │  RAG-чат:       │   │  RAG-чат:       │   │  RAG-чат:       │          │
│  │  "О чем говорили│   │  "Какой бюджет?"│   │  "Когда дедлайн"│          │
│  └─────────────────┘   └─────────────────┘   └─────────────────┘          │
│                                                                             │
│                    ┌─────────────────────────┐                             │
│                    │   Telegram Bot Alerts   │                             │
│                    │   - Срочные вопросы     │                             │
│                    │   - Дедлайны            │                             │
│                    │   - Риски               │                             │
│                    └─────────────────────────┘                             │
│                                                                             │
│                    ┌─────────────────────────┐                             │
│                    │   Daily Digest (23:00)  │                             │
│                    │   - Кратко по всем      │                             │
│                    │   - Action items        │                             │
│                    └─────────────────────────┘                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

**Ключевые фичи:**
1. **Индивидуальная комната на клиента** (notebook в open-notebook)
2. **RAG-система** — можно задать вопрос по истории общения
3. **Алерты в Telegram** — срочные вопросы, дедлайны, риски
4. **Daily digest** — краткое саммари по всем клиентам за день

---

## 📋 План на завтра (2026-02-20)

### Часть 1: Подготовка реальных созвонов (30-45 мин)

#### 1.1. Где взять реальные аудиозаписи?

**Варианты:**
1. **Telegram** — если созвоны записывались через Telegram
2. **Google Meet / Zoom** — если записи сохранялись
3. **Мобильный диктофон** — если записывали вручную

**Форматы:** Whisper поддерживает WebM, MP3, WAV, OGG, M4A, FLAC — конвертация НЕ нужна!

#### 1.2. Как загрузить файлы на сервер

**Способ 1: Через WinSCP (рекомендуется для Windows)**

1. Скачай WinSCP: https://winscp.net/eng/download.php
2. Подключись к серверу:
   - Host: `84.252.100.93`
   - Username: `root`
   - Password: `xe1ZlW0Rpiyk`
3. Перейди в папку `/mnt/recordings/2026/02/20/` (создай если нет)
4. Перетащи файлы из Windows

**Способ 2: Через PuTTY (scp команда)**

В Windows PowerShell:
```powershell
scp -o StrictHostKeyChecking=no "C:\path\to\call1.wav" root@84.252.100.93:/mnt/recordings/2026/02/20/
```

**Способ 3: Через curl с сервера (если файлы в облаке)**

В PuTTY:
```bash
cd /mnt/recordings/2026/02/20/
curl -L -o "call1.mp3" "https://ссылка-на-файл.mp3"
```

#### 1.3. Требования к именам файлов

**Формат:** `{LEAD_ID}_{дата}_{время}.{расширение}`

Примеры:
```
101_2026-02-20_10-30.mp3      ← созвон с клиентом LEAD-101
102_2026-02-20_14-00.wav      ← созвон с клиентом LEAD-102
103_2026-02-20_16-30.webm     ← созвон с клиентом LEAD-103
```

**Важно:**
- LEAD_ID — это ID клиента в вашей CRM/системе (цифры)
- Дата в формате YYYY-MM-DD
- Время в формате HH-MM (24 часа)

#### 1.4. Создать папку на сервере

В PuTTY:
```bash
mkdir -p /mnt/recordings/2026/02/20/
chmod 777 /mnt/recordings/2026/02/20/
ls -la /mnt/recordings/2026/02/20/
```

---

### Часть 2: Выгрузка истории Telegram-чатов (45-60 мин)

#### 2.1. Почему это сложно?

**Telegram Bot API НЕ позволяет читать историю сообщений!** Бот видит только:
- Сообщения, отправленные ПОСЛЕ добавления бота в чат
- Через webhook (реальное время)

**Решение:** Использовать **Telethon** (Python-библиотека для личного аккаунта)

#### 2.2. Получение API credentials

1. Зайди на https://my.telegram.org/apps
2. Войди своим номером телефона (тот, что в Telegram)
3. Создай новое приложение:
   - App title: `MVP Auto-Summary`
   - Short name: `mvp-summary`
   - Platform: `Desktop`
4. Скопируй:
   - **api_id**: цифры (например, `12345678`)
   - **api_hash**: строка 32 символа (например, `a1b2c3d4e5f6...`)

**⚠️ ВАЖНО:** Эти данные = доступ к твоему Telegram. Не передавай никому!

#### 2.3. Подготовка скрипта на сервере

Я напишу скрипт `export_telegram_chat.py`, который:
1. Подключится к твоему Telegram
2. Выгрузит историю указанного чата
3. Сохранит в JSON и TXT форматы

**Скрипт будет готов завтра утром.**

#### 2.4. Процесс выгрузки (завтра)

```bash
# На сервере:
cd /root/mvp-auto-summary/scripts/

# Запуск скрипта (интерактивный - попросит код из Telegram)
python3 export_telegram_chat.py --chat "Имя клиента или чата" --output ../exports/LEAD-101_chat.json

# Результат:
# ../exports/LEAD-101_chat.json  ← полная история в JSON
# ../exports/LEAD-101_chat.txt   ← текст для суммаризации
```

#### 2.5. Альтернатива: ручная выгрузка

Если не хочешь давать доступ к Telegram через API:

1. Открой чат в Telegram Desktop
2. Выдели все сообщения (Ctrl+A — может не работать для длинных чатов)
3. Скопируй в текстовый файл
4. Сохрани как `LEAD-101_chat.txt`
5. Загрузи на сервер через WinSCP

**Формат файла:**
```
[10.02.2026 14:30] Алексей: Добрый день, интересует ваш продукт
[10.02.2026 14:31] Клиент: Да, хотел узнать про условия доставки
[10.02.2026 14:35] Алексей: Доставка 2-3 дня, бесплатно от 5000р
...
```

---

### Часть 3: Обновлённая архитектура Workflow 02 (60-90 мин)

#### 3.1. Текущий workflow (только созвоны)

```
[Schedule 23:00]
    → Load Today's Transcripts (только из processed_files)
    → Aggregate
    → GLM-4 Summarize
    → Send Telegram (один общий дайджест)
```

#### 3.2. Новый workflow (созвоны + чаты + индивидуальные summaries)

```
[Schedule 23:00]
    │
    ├──→ Load Today's Calls (processed_files)
    │         → For each call:
    │              → GLM-4 Summarize (сохранить в separate file)
    │              → Save to notebook LEAD-{id}
    │
    ├──→ Load Today's Chats (новая таблица: chat_messages)
    │         → For each chat:
    │              → GLM-4 Summarize (сохранить в separate file)
    │              → Save to notebook LEAD-{id}
    │
    └──→ Aggregate all summaries
              → GLM-4 Super-Brief (2-3 предложения на клиента)
              → Send Telegram (super-short digest)
```

#### 3.3. Новые таблицы в PostgreSQL

```sql
-- Таблица для чатов
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
    source_type VARCHAR(20), -- 'call' или 'chat'
    source_id INTEGER,       -- ID из processed_files или chat_messages
    summary_text TEXT,
    summary_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- View для получения всех данных по клиенту
CREATE VIEW v_client_activity AS
SELECT 
    lead_id,
    'call' as source_type,
    id as source_id,
    transcript_text as content,
    created_at
FROM processed_files
WHERE status = 'completed'
UNION ALL
SELECT 
    lead_id,
    'chat' as source_type,
    id as source_id,
    message_text as content,
    message_date as created_at
FROM chat_messages;
```

#### 3.4. Структура файлов summaries

```
/exports/summaries/2026-02-20/
├── LEAD-101_call_2026-02-20_10-30.md    ← саммари созвона
├── LEAD-101_chat_2026-02-20.md          ← саммари чата
├── LEAD-101_combined_2026-02-20.md      ← объединённое саммари
├── LEAD-102_call_2026-02-20_14-00.md
├── LEAD-102_chat_2026-02-20.md
├── LEAD-102_combined_2026-02-20.md
└── daily_digest_2026-02-20.md           ← супер-краткий дайджест для бота
```

---

### Часть 4: Подготовка open-notebook для RAG (30 мин)

#### 4.1. Текущее состояние

- open-notebook уже работает на :8888
- SurrealDB хранит данные
- Есть API для создания notebooks и sources

#### 4.2. Структура notebooks

```
Notebook "LEAD-101" (клиент ООО "Ромашка")
├── Source: Созвон 20.02.2026 10:30
│     └── Content: [транскрипт]
│     └── Summary: [GLM-4 summary]
│
├── Source: Чат 20.02.2026
│     └── Content: [история чата]
│     └── Summary: [GLM-4 summary]
│
└── Source: Предыдущие созвоны...
```

#### 4.3. RAG-чат по клиенту

**API endpoint:** `POST http://open-notebook:8888/chat/execute`

**Пример запроса:**
```json
{
  "session_id": "chat_session:LEAD-101",
  "message": "О чем говорили на последнем созвоне? Были ли договорённости по доставке?",
  "context": {
    "notebook_id": "notebook:LEAD-101"
  }
}
```

**Ответ:** RAG найдёт релевантные фрагменты и ответит на основе реальных данных.

---

### Часть 5: Изменения в промптах GLM-4

#### 5.1. Текущий промпт (для daily digest)

```
Ты бизнес-аналитик. Сформируй ежедневный дайджест по стенограммам встреч.
Формат:
1) Краткое резюме дня (3-5 предложений).
2) Ключевые договоренности (буллеты).
3) Action items (буллеты с ответственным).
4) Риски/блокеры.
5) Клиенты/LEAD: перечисли LEAD-ID, по каждому 1-2 ключевых пункта.
```

#### 5.2. Новый промпт для индивидуального summary (созвон)

```
Ты бизнес-аналитик. Проанализируй транскрипцию созвона с клиентом.

ВЫХОДНОЙ ФОРМАТ (строго):

## Краткое резюме
[2-3 предложения о главном]

## Участники
- Менеджер: [имя]
- Клиент: [компания/имя]

## Ключевые договорённости
- [пункт 1]
- [пункт 2]

## Action Items
- [ ] [задача] — [ответственный] — [дедлайн]
- [ ] [задача] — [ответственный] — [дедлайн]

## Риски и блокеры
- [риск 1 или "Нет"]

## Следующие шаги
- [что делать дальше]

## Важные цитаты клиента
> "[цитата 1]"
> "[цитата 2]"
```

#### 5.3. Новый промпт для индивидуального summary (чат)

```
Ты бизнес-аналитик. Проанализируй историю переписки с клиентом в Telegram.

ВЫХОДНОЙ ФОРМАТ (строго):

## Период общения
[даты первой и последней переписки]

## Основные темы
- [тема 1]
- [тема 2]

## Ключевые договорённости
- [пункт 1]
- [пункт 2]

## Open questions (вопросы без ответа)
- [вопрос 1 или "Нет"]

## Тон клиента
[позитивный/нейтральный/негативный + причины]

## Следующие шаги
- [что нужно сделать]
```

#### 5.4. Промпт для супер-краткого daily digest

```
Ты бизнес-аналитик. Создай СВЕРХКРАТКИЙ ежедневный дайджест.

ПРАВИЛА:
- Максимум 500 символов
- Только самое важное
- Формат: по одному предложению на клиента

ФОРМАТ:
📅 Дайджест за {дата}

👥 Клиенты: LEAD-101, LEAD-102, LEAD-103

📝 По каждому:
• LEAD-101: [1 предложение о главном]
• LEAD-102: [1 предложение о главном]
• LEAD-103: [1 предложение о главном]

⚠️ Срочное:
• [если есть срочное, иначе "Нет"]
```

---

### Часть 6: Скрипты для подготовки (создаю завтра утром)

#### 6.1. export_telegram_chat.py

Выгрузка истории чата через Telethon.

#### 6.2. import_chat_to_db.py

Импорт выгруженного чата в PostgreSQL.

#### 6.3. generate_individual_summary.py

Генерация индивидуального summary по клиенту.

#### 6.4. combine_client_data.py

Объединение всех данных по клиенту в один файл.

---

## 📋 Чек-лист на завтра

### Утром (подготовка):

- [ ] Создать папку на сервере: `/mnt/recordings/2026/02/20/`
- [ ] Создать папку: `/root/mvp-auto-summary/exports/summaries/2026-02-20/`
- [ ] Создать таблицы в PostgreSQL (chat_messages, client_summaries)
- [ ] Загрузить скрипты на сервер

### Днём (загрузка данных):

- [ ] Загрузить 2-3 реальных созвона через WinSCP
- [ ] Получить Telegram API credentials (api_id, api_hash)
- [ ] Выгрузить 2-3 реальных чата
- [ ] Импортировать чаты в PostgreSQL

### Вечером (тестирование):

- [ ] Запустить Workflow 01 (транскрипция созвонов)
- [ ] Проверить транскрипты в open-notebook
- [ ] Запустить новый Workflow 02 (индивидуальные summaries)
- [ ] Проверить файлы summaries в `/exports/summaries/`
- [ ] Проверить daily digest в Telegram
- [ ] Протестировать RAG-чат по клиенту

---

## 🔧 Команды для PuTTY (завтра)

### Создание структуры папок:

```bash
mkdir -p /mnt/recordings/2026/02/20/
mkdir -p /root/mvp-auto-summary/exports/summaries/2026/02/20/
chmod 777 /mnt/recordings/2026/02/20/
chmod 777 /root/mvp-auto-summary/exports/summaries/2026/02/20/
```

### Создание таблиц:

```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR(50),
    chat_title VARCHAR(255),
    sender VARCHAR(100),
    message_text TEXT,
    message_date TIMESTAMP,
    imported_at TIMESTAMP DEFAULT NOW(),
    summary_sent BOOLEAN DEFAULT FALSE
);

CREATE TABLE IF NOT EXISTS client_summaries (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR(50),
    source_type VARCHAR(20),
    source_id INTEGER,
    summary_text TEXT,
    summary_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);
"
```

### Проверка загруженных файлов:

```bash
ls -la /mnt/recordings/2026/02/20/
```

### Ручной запуск транскрипции:

```bash
# Через n8n UI: http://84.252.100.93:5678
# Workflow 01 → Execute workflow
```

### Проверка транскриптов:

```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "
SELECT id, filename, lead_id, 
       LENGTH(transcript_text) as text_len, 
       status 
FROM processed_files 
WHERE filename LIKE '%2026-02-20%' 
ORDER BY id DESC;
"
```

---

## 📁 Файловая структура (итоговая)

```
/root/mvp-auto-summary/
├── exports/
│   ├── chats/
│   │   ├── LEAD-101_chat.json       ← выгруженный чат
│   │   ├── LEAD-101_chat.txt
│   │   ├── LEAD-102_chat.json
│   │   └── LEAD-102_chat.txt
│   │
│   └── summaries/
│       └── 2026-02-20/
│           ├── LEAD-101_call_10-30.md
│           ├── LEAD-101_chat.md
│           ├── LEAD-101_combined.md
│           ├── LEAD-102_call_14-00.md
│           ├── LEAD-102_chat.md
│           ├── LEAD-102_combined.md
│           └── daily_digest.md
│
├── scripts/
│   ├── export_telegram_chat.py
│   ├── import_chat_to_db.py
│   ├── generate_individual_summary.py
│   └── combine_client_data.py
│
└── n8n-workflows/
    ├── 01-new-recording.json
    ├── 02-daily-digest.json          ← текущий
    └── 03-individual-summary.json     ← новый (завтра)
```

---

## ⚠️ Риски и ограничения

### 1. Telegram API
- **Риск:** Telegram может временно заблокировать при агрессивном использовании
- **Митигация:** Паузы между запросами, выгрузка не более 5 чатов за раз

### 2. Качество транскрипции
- **Риск:** Плохое качество аудио → низкое качество транскрипта
- **Митигация:** Проверить качество аудио перед загрузкой

### 3. GLM-4 thinking mode
- **Риск:** Может вернуться (если API обновится)
- **Митигация:** Fallback на reasoning_content уже есть

### 4. Время обработки
- **Риск:** Длинные созвоны (60+ мин) обрабатываются долго
- **Митигация:** Увеличить timeout в n8n до 10 минут

---

## 📞 Контакты и доступы

| Сервис | Данные |
|--------|--------|
| Сервер | `root@84.252.100.93` / `xe1ZlW0Rpiyk` |
| n8n UI | `http://84.252.100.93:5678` / `rod@zevich.ru` / `Ill216johan511lol2` |
| open-notebook | `http://84.252.100.93:8888` |
| Telegram Bot | `@ffp_report_bot` |
| GLM-4 API Key | `fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6` |

---

## 🎯 Критерии успеха на завтра

1. ✅ Загружено 2+ реальных созвона
2. ✅ Выгружено 2+ реальных чата
3. ✅ Созвоны транскрибированы Whisper
4. ✅ Сгенерированы индивидуальные summaries по каждому клиенту
5. ✅ Данные сохранены в open-notebook (notebook на клиента)
6. ✅ Daily digest отправлен в Telegram
7. ✅ RAG-чат отвечает на вопросы по клиенту

---

*Документ создан: 2026-02-19 | Автор: OpenCode Agent*
