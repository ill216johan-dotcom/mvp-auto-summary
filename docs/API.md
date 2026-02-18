# API Contracts — External Services

> Все API-контракты используемых внешних сервисов для справки при настройке n8n workflows.

---

## 1. Whisper (Self-hosted STT)

> Заменяет Yandex SpeechKit. Работает локально, бесплатно, поддерживает WebM.

**Docker image**: `onerahmet/openai-whisper-asr-webservice:latest-cpu`  
**Internal URL**: `http://whisper:9000`  
**Swagger docs**: `http://VPS_IP:9000/docs`

### Transcribe Audio

**Endpoint**: `POST http://whisper:9000/asr`

**Query Parameters**:
| Param | Value | Description |
|-------|-------|-------------|
| `task` | `transcribe` | Транскрипция (не перевод) |
| `language` | `ru` | Русский язык |
| `output` | `json` | Формат ответа |
| `word_timestamps` | `false` | Таймстампы слов (опционально) |

**Request** (multipart/form-data):
```bash
curl -X POST "http://whisper:9000/asr?task=transcribe&language=ru&output=json" \
  -F "audio_file=@meeting.webm"
```

**Response**:
```json
{
  "text": "Полный распознанный текст встречи..."
}
```

### Supported Formats

| Format | Support |
|--------|---------|
| WebM | ✅ Нативно |
| MP3 | ✅ |
| WAV | ✅ |
| OGG | ✅ |
| FLAC | ✅ |
| M4A | ✅ |

> Whisper принимает **любой формат** — конвертация не нужна!

---

## 3. GLM-4 (ZhipuAI)

**Endpoint**: `POST https://api.z.ai/api/paas/v4/chat/completions`

**Auth**: `Authorization: Bearer {GLM4_API_KEY}`

**OpenAI-compatible** — can use n8n OpenAI node with custom base URL.

**Request**:
```json
{
  "model": "glm-4.7-flashx",
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
  "temperature": 0.3,
  "max_tokens": 4000,
  "stream": false
}
```

**Response**:
```json
{
  "choices": [
    {
      "message": {
        "role": "assistant",
        "content": "Summary text..."
      }
    }
  ],
  "usage": {
    "prompt_tokens": 1234,
    "completion_tokens": 567
  }
}
```

### Models

| Model | Context | Price (in/out per 1M tok) |
|-------|---------|---------------------------|
| glm-4.7-flashx | 200K | $0.07 / $0.40 |
| glm-4.7-flash | 200K | FREE |
| glm-4.7 | 200K | $0.60 / $2.20 |

---

## 4. Telegram Bot API

**Endpoint**: `POST https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage`

**Request**:
```json
{
  "chat_id": "{TELEGRAM_CHAT_ID}",
  "text": "Markdown formatted text",
  "parse_mode": "Markdown"
}
```

---

## 5. open-notebook API

**Base URL**: `http://open-notebook:8888` (internal Docker network)

**Auth**: `Authorization: Bearer {OPEN_NOTEBOOK_TOKEN}` (по умолчанию `password`)

### Create Notebook (per client)
```
POST /notebooks
{ "name": "LEAD-12345", "description": "Client meetings" }
→ { "id": "notebook:xxx", "name": "LEAD-12345" }
```

### Add Source (transcript)
```
POST /sources
{
  "type": "text",
  "text": "Transcript content...",
  "notebook_ids": ["notebook:xxx"],
  "title": "Meeting 2026-02-18 14:30"
}
→ { "id": "source:yyy", "command_id": "command:zzz" }
```

### List Notebooks
```
GET /notebooks?archived=false&order_by=updated%20desc
→ { "items": [ { "id": "notebook:xxx", "name": "LEAD-12345" } ] }
```

### RAG Chat
```
POST /chat/execute
{
  "session_id": "chat_session:xxx",
  "message": "Что обсуждалось на последнем митинге?",
  "context": { "sources": { "source:yyy": "full content" } }
}
```

### Vector Search
```
POST /search
{
  "type": "vector",
  "query": "client budget concerns",
  "search_sources": true,
  "limit": 10
}
```

---

*Document created: 2026-02-18 | Auto-updated by Living Documentation Protocol*
