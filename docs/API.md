# API Contracts — External Services

> Все API-контракты используемых внешних сервисов для справки при настройке n8n workflows.

---

## 1. Яндекс SpeechKit (STT)

> Основной движок транскрипции. Асинхронный режим — отправил задание, подождал, забрал результат.

**Документация**: https://yandex.cloud/ru/docs/speechkit/stt/api/transcribation

### Шаг 1: Загрузить аудио в Яндекс Object Storage

Аудио нужно загрузить в S3-совместимое хранилище Яндекса перед отправкой в SpeechKit.

```bash
# Через aws cli (совместим с Яндекс S3)
aws s3 cp meeting.webm s3://ВАШ_БАКЕТ/audio/meeting.webm \
  --endpoint-url https://storage.yandexcloud.net
```

### Шаг 2: Запустить асинхронную транскрипцию

**Endpoint**: `POST https://transcribe.api.cloud.yandex.net/speech/stt/v3/recognizeFileAsync`

**Auth**: `Authorization: Api-Key {YANDEX_API_KEY}`

**Request**:
```json
{
  "uri": "https://storage.yandexcloud.net/ВАШ_БАКЕТ/audio/meeting.webm",
  "recognitionModel": {
    "model": "general",
    "audioFormat": {
      "containerAudio": {
        "containerAudioType": "WEBM_OPUS"
      }
    },
    "languageRestriction": {
      "restrictionType": "WHITELIST",
      "languageCode": ["ru-RU"]
    }
  }
}
```

**Response**:
```json
{
  "id": "e03sup6d5h7rq574ht8g",
  "done": false
}
```
→ Сохранить `id` (operationId) для polling.

### Шаг 3: Polling статуса операции

**Endpoint**: `GET https://operation.api.cloud.yandex.net/operations/{operationId}`

**Auth**: `Authorization: Api-Key {YANDEX_API_KEY}`

**Response когда готово** (`done: true`):
```json
{
  "id": "e03sup6d5h7rq574ht8g",
  "done": true,
  "response": {
    "chunks": [
      {
        "alternatives": [
          {
            "text": "Распознанный текст фразы...",
            "confidence": 0
          }
        ],
        "channelTag": "0"
      }
    ]
  }
}
```

**Извлечение текста из chunks** (n8n Code node):
```javascript
const chunks = $json.response.chunks || [];
const text = chunks
  .map(c => c.alternatives?.[0]?.text || '')
  .filter(t => t.trim())
  .join(' ');
return [{ json: { transcript: text } }];
```

### Поддерживаемые форматы

| Формат | containerAudioType |
|--------|--------------------|
| WEBM (Opus) | `WEBM_OPUS` |
| MP3 | `MP3` |
| OGG (Opus) | `OGG_OPUS` |
| WAV | `LINEAR16_PCM` |

> Jibri записывает в WebM/Opus — конвертация **НЕ нужна**.

### Переменные окружения

```
YANDEX_API_KEY=AQVNxxxxxxxxxxxxxxxx   # IAM-токен или API-ключ
YANDEX_FOLDER_ID=b1gxxxxxxxxxxxxxxxx  # ID папки в Яндекс Облаке
YANDEX_BUCKET=ffp-recordings          # Имя S3-бакета
```

---

## 2. GLM-4 (ZhipuAI)

**Endpoint**: `POST https://open.bigmodel.cn/api/paas/v4/chat/completions`

**Auth**: `Authorization: Bearer {GLM4_API_KEY}`

**OpenAI-compatible** — можно использовать n8n OpenAI node с кастомным base URL.

> ⚠️ **ВАЖНО**: Модель `glm-4.7-flash` — thinking-модель. Нужно явно отключать thinking mode!  
> Иначе `content` будет пустым, а ответ уйдёт в `reasoning_content`. (см. E043 в ERRORS.md)

**Request**:
```json
{
  "model": "glm-4.7-flash",
  "messages": [
    {
      "role": "system",
      "content": "Ты бизнес-аналитик. Сделай краткое саммари созвона (3-5 предложений). Выдели ключевые договорённости и action items."
    },
    {
      "role": "user",
      "content": "{transcript_text}"
    }
  ],
  "temperature": 0.2,
  "max_tokens": 1400,
  "stream": false,
  "thinking": { "type": "disabled" }
}
```

**Response**:
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Summary text...",
        "reasoning_content": ""
      }
    }
  ],
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 567
  }
}
```

### Модели

| Модель | Контекст | Цена (1M токенов) | Рекомендация |
|--------|----------|-------------------|--------------|
| glm-4.7-flash | 200K | **Бесплатно** | **MVP (текущая)** |
| glm-4.7-flashx | 200K | $0.07 / $0.40 | Платная опция |
| glm-4.7 | 200K | $0.60 / $2.20 | Максимальное качество |

### Рабочий ключ

```
fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6
```

---

## 3. Telegram Bot API

**Bot**: `@ffp_report_bot`  
**Token**: `8527521201:AAHpyrPn4cig-zq0Xymt7lZ94qBIEXnYAeQ`  
**Chat ID**: `-1003872092456`

### Отправить сообщение

**Endpoint**: `POST https://api.telegram.org/bot{TOKEN}/sendMessage`

**Request**:
```json
{
  "chat_id": -1003872092456,
  "text": "Markdown formatted text",
  "parse_mode": "Markdown"
}
```

### Получить обновления (polling)

**Endpoint**: `GET https://api.telegram.org/bot{TOKEN}/getUpdates?offset={offset}`

Workflow 04 вызывает getUpdates каждые 30 секунд, отслеживает offset чтобы не обрабатывать одно сообщение дважды.

### Команды бота

| Команда | Действие |
|---------|----------|
| `/report` | Немедленный отчёт по всем `summary_sent=false` записям |

---

## 4. open-notebook API

> ⚠️ **ВАЖНО**: Два разных порта!
> - `:8888` → Web UI (браузер, для людей)
> - `:5055` → REST API (для n8n внутри Docker)

**Internal API URL (для n8n)**: `http://open-notebook:5055`  
**External UI URL (для браузера)**: `http://84.252.100.93:8888`

**Auth**: `Authorization: Bearer {OPEN_NOTEBOOK_TOKEN}`

### Список ноутбуков

```
GET http://open-notebook:5055/api/notebooks

Response (массив напрямую, не обёртка):
[
  { "id": "notebook:xyz123", "title": "LEAD-1000023", ... },
  { "id": "notebook:abc456", "title": "LEAD-1000097", ... }
]
```

### Создать ноутбук

```
POST http://open-notebook:5055/api/notebooks
Content-Type: application/json

{ "title": "LEAD-12345" }

Response:
{ "id": "notebook:xyz123", "title": "LEAD-12345", ... }
```

### Добавить источник (транскрипт или саммари)

```
POST http://open-notebook:5055/api/sources/json
Content-Type: application/json

{
  "notebooks": ["notebook:xyz123"],
  "type": "text",
  "content": "Текст транскрипта...",
  "title": "Созвон 2026-02-22 14:30 — LEAD-1000023",
  "embed": true,
  "async_processing": false
}

Response:
{ "id": "source:abc789", "title": "...", ... }
```

> `embed: true` — включить в векторный индекс для RAG-поиска  
> `async_processing: false` — ждать завершения (синхронно)

### n8n jsonBody (обязательно Expression mode)

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

### Проверить что API работает

```bash
# Изнутри Docker:
docker exec mvp-auto-summary-open-notebook-1 \
  wget -qO- http://localhost:5055/api/notebooks

# Снаружи (с хоста сервера):
curl http://84.252.100.93:5055/api/notebooks
```

### RAG Chat

```
POST http://open-notebook:5055/chat/execute
{
  "session_id": "chat_session:xxx",
  "message": "Что обсуждалось на последнем митинге?"
}
```

### Vector Search

```
POST http://open-notebook:5055/search
{
  "type": "vector",
  "query": "бюджет клиента",
  "search_sources": true,
  "limit": 10
}
```

---

## 5. PostgreSQL (внутренний)

**Connection** (внутри Docker): `postgresql://n8n:n8n@postgres:5432/n8n`

### Таблица processed_files

```sql
CREATE TABLE processed_files (
  id            SERIAL PRIMARY KEY,
  filename      TEXT NOT NULL,
  filepath      TEXT NOT NULL,          -- обязательное поле!
  lead_id       TEXT,
  status        TEXT DEFAULT 'pending', -- pending/transcribing/completed/error
  transcript_text TEXT,
  summary_sent  BOOLEAN DEFAULT false,
  created_at    TIMESTAMP DEFAULT NOW()
);
```

### View v_today_completed

```sql
-- Записи за сегодня, не отправленные в дайджест
SELECT * FROM v_today_completed;
-- WHERE status='completed' AND summary_sent=false AND DATE(created_at)=CURRENT_DATE
```

### Полезные запросы

```bash
# Статус обработки файлов
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT id, filename, status, summary_sent, created_at FROM processed_files ORDER BY id DESC LIMIT 10;"

# Сбросить summary_sent для повторного дайджеста
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "UPDATE processed_files SET summary_sent = false WHERE status='completed';"

# Очистить всё для чистого теста
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "TRUNCATE TABLE processed_files RESTART IDENTITY;"

# Сбросить зависшие файлы (transcribing > 30 мин)
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "DELETE FROM processed_files WHERE status='transcribing' AND created_at < NOW() - INTERVAL '30 minutes';"
```

---

*Document created: 2026-02-18 | Updated: 2026-02-22 — заменён Whisper на SpeechKit, исправлены порты open-notebook (5055), добавлены секции PostgreSQL и Telegram polling*
