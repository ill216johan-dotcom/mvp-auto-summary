# API Contracts — External Services

> Все API-контракты используемых внешних сервисов.  
> Обновлено: 2026-02-26 — миграция на Dify.ai, per-client RAG, новые эндпоинты.

---

## 1. Яндекс SpeechKit (STT)

**Docs**: https://yandex.cloud/ru/docs/speechkit/stt/api/transcribation  
**Используется через**: `transcribe` service (port 9001)  
**Режим**: синхронное распознавание по чанкам 25 сек

### Endpoint

```
POST https://stt.api.cloud.yandex.net/speech/v1/stt:recognize
  ?lang=ru-RU&format=oggopus&sampleRateHertz=16000
Authorization: Api-Key {YANDEX_API_KEY}
Content-Type: audio/ogg

<binary audio data>
```

### Поддерживаемые форматы

| Формат | Конвертация |
|--------|-------------|
| WEBM (Jibri) | ffmpeg → OGG/Opus 16kHz mono → чанки по 25 сек |
| MP3 | ffmpeg → OGG/Opus |
| WAV | ffmpeg → OGG/Opus |

### Переменные окружения

```
YANDEX_API_KEY=AQVNxxxxxxxxxxxxxxxx
```

---

## 2. GLM-4 (ZhipuAI)

**Endpoint**: `POST https://open.bigmodel.cn/api/paas/v4/chat/completions`  
**Auth**: `Authorization: Bearer {GLM4_API_KEY}`  
**OpenAI-compatible** API

> ⚠️ **КРИТИЧНО**: `glm-4.7-flash` — thinking-модель. Без `"thinking": {"type": "disabled"}`
> ответ уйдёт в `reasoning_content`, а `content` будет пустым. (см. E043 в ERRORS.md)

### Request

```json
{
  "model": "glm-4-flash",
  "messages": [
    { "role": "system", "content": "Системный промпт..." },
    { "role": "user",   "content": "Транскрипт созвона..." }
  ],
  "temperature": 0.3,
  "max_tokens": 2000,
  "stream": false,
  "thinking": { "type": "disabled" }
}
```

### Response

```json
{
  "choices": [{
    "message": {
      "role": "assistant",
      "content": "## Резюме\n...",
      "reasoning_content": ""
    }
  }],
  "usage": { "prompt_tokens": 1234, "completion_tokens": 567 }
}
```

### Извлечение ответа (защита от пустого content)

```javascript
// В n8n Code node:
const msg = $json.choices?.[0]?.message || {};
const summary = (msg.content || msg.reasoning_content || 'Ошибка генерации').trim();
```

### Модели

| Модель | Контекст | Цена | Статус |
|--------|----------|------|--------|
| `glm-4-flash` | 128K | **Бесплатно** | **Используется в WF03** |
| `glm-4.7-flash` | 200K | **Бесплатно** | Используется в WF02, WF04 |
| `glm-4.7-flashx` | 200K | $0.07/$0.40 | Платная опция |

### Переменные окружения

```
GLM4_API_KEY=xxxxxxxxxxxxxxxx.xxxxxxxxxxxxxxxx
GLM4_BASE_URL=https://open.bigmodel.cn/api/paas/v4
GLM4_MODEL=glm-4.7-flash
```

---

## 3. Dify.ai (RAG + Knowledge Base)

**UI**: `http://84.252.100.93` (порт 80)  
**API Base**: `http://84.252.100.93/v1`  
**Auth**: `Authorization: Bearer {DIFY_API_KEY}`

> ⚠️ Два типа API ключей:
> - `app-xxx` — App API key (для chatbot, из Studio → конкретное приложение)
> - `dataset-xxx` — Dataset API key (для Knowledge Base, из Знания → Сервисный API)
> WF03 использует `dataset-xxx` для создания документов в KB.

### Переменные окружения

```
DIFY_API_KEY=dataset-k7rrBrS6TsEixGGIyAvywfb0
DIFY_BASE_URL=http://84.252.100.93
DIFY_DATASET_ID=ba120e09-0119-438f-b6d6-884e73b73334   # legacy fallback
DIFY_CHATBOT_URL=http://84.252.100.93
```

### Датасеты (Knowledge Base)

| Название | Dataset ID | Описание |
|----------|-----------|----------|
| База знаний (legacy) | `ba120e09-0119-438f-b6d6-884e73b73334` | Старый общий KB |
| Общая документация ФФ | `727b7015-5c9f-4375-83fd-6b2967ef8637` | Оферта, WMS-инструкция |
| LEAD-4405 ФФ-4405 | `9e65a348-9a04-4ab5-a2ed-4ae766cb11fb` | Клиент 4405 |
| LEAD-987 ФФ-987 | `9fec3f54-b7f4-4620-b562-a5266d7206db` | Клиент 987 |
| LEAD-1381 ФФ-1381 | `54a97db4-3532-41c2-bab0-fd5ac6dc86e8` | Клиент 1381 |
| LEAD-2048 ФФ-2048 | `205f9a3b-bab3-4967-9887-ed25ea15b506` | Клиент 2048 |
| LEAD-4550 ФФ-4550 | `be1b0752-4aa5-4a75-a950-993fd4b24353` | Клиент 4550 |
| LEAD-506 ФФ-506 | `8b5508b7-5e17-470c-9f33-a6d1443d5ea2` | Клиент 506 |

### Список датасетов

```bash
GET /v1/datasets?limit=100
Authorization: Bearer dataset-xxx

# Пример:
curl http://84.252.100.93/v1/datasets?limit=100 \
  -H "Authorization: Bearer dataset-k7rrBrS6TsEixGGIyAvywfb0"
```

### Создать датасет

```bash
POST /v1/datasets
Content-Type: application/json

{
  "name": "LEAD-9999 ФФ-9999",
  "description": "Созвоны, чаты, саммари клиента ФФ-9999.",
  "permission": "all_team_members"
}
# НЕ передавать indexing_technique — без embedding модели даёт ошибку 400
```

### Добавить документ в датасет

```bash
POST /v1/datasets/{dataset_id}/document/create-by-text
Authorization: Bearer dataset-xxx
Content-Type: application/json

{
  "name": "[2026-02-26] LEAD-4405 — Созвоны (2 звонка)",
  "text": "## Резюме\n...\n## Action Items\n...",
  "indexing_technique": "high_quality",
  "process_rule": { "mode": "automatic" }
}
```

Response:
```json
{ "document": { "id": "doc-uuid", "name": "...", "indexing_status": "waiting" } }
```

> Если нет embedding-модели → ошибка `Default model not found for text-embedding`.
> В таком случае создавать датасеты без `indexing_technique`.

### Проверить доступность API

```bash
curl -s http://localhost/v1/datasets?limit=1 \
  -H "Authorization: Bearer dataset-k7rrBrS6TsEixGGIyAvywfb0" | python3 -m json.tool
# 200 → OK, 401 → неверный ключ
```

---

## 4. Telegram Bot API

**Bot**: `@ffp_report_bot`  
**Token**: `${TELEGRAM_BOT_TOKEN}`  
**Chat**: `${TELEGRAM_CHAT_ID}` = `-1003872092456` (группа "Отчёты ФФ Платформы")

### Команды бота (WF04)

| Команда | Действие |
|---------|----------|
| `/report` | Промежуточный отчёт по необработанным созвонам |
| `/status` | Статус системы + список клиентов + ссылки |
| `/rag` | Ссылка на Dify RAG-ассистент |
| `/help` | Справка по командам |

### Отправить сообщение

```bash
POST https://api.telegram.org/bot{TOKEN}/sendMessage

{
  "chat_id": -1003872092456,
  "text": "<b>Заголовок</b>\nТекст",
  "parse_mode": "HTML",
  "disable_web_page_preview": false
}
```

> Используем **HTML**, не Markdown — стабильнее в n8n.

### Получить обновления (polling)

```
GET https://api.telegram.org/bot{TOKEN}/getUpdates
  ?limit=20&timeout=0&offset={last_update_id+1}
```

WF04 вызывает каждые 30 секунд, хранит `lastUpdateId` в `staticData`.

### Отправить тестовое сообщение вручную

```bash
curl -X POST "https://api.telegram.org/bot8527521201:AAHpyrPn4cig-zq0Xymt7lZ94qBIEXnYAeQ/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{"chat_id": -1003872092456, "text": "/status"}'
```

---

## 5. transcribe service (internal)

**URL (docker network)**: `http://transcribe:9001`  
**URL (host)**: `http://localhost:9001`

### Start transcription

```
POST http://transcribe:9001/
{ "filepath": "/recordings/4405_2026-02-26_10-30.webm" }

→ { "status": "processing", "filename": "4405_2026-02-26_10-30.webm" }
```

### Check transcription status

```
POST http://transcribe:9001/check
{ "filename": "4405_2026-02-26_10-30.webm" }

→ { "transcript": "Текст транскрипта...", "status": "completed" }
→ { "transcript": null, "status": "processing" }   # ещё не готово
→ { "transcript": null, "status": "error" }         # ошибка
```

### Health check

```
GET http://transcribe:9001/health
→ { "status": "ok" }
```

---

## 6. PostgreSQL (внутренний)

**Connection (внутри Docker)**: `postgresql://n8n:PASSWORD@postgres:5432/n8n`  
**Connection (с хоста)**: `postgresql://n8n:PASSWORD@localhost:5432/n8n`

### Ключевые таблицы

| Таблица | Назначение |
|---------|-----------|
| `processed_files` | Все аудиозаписи, статус обработки, транскрипт, саммари |
| `chat_messages` | История Telegram-переписки по клиентам |
| `client_summaries` | Ежедневные саммари (звонки + чаты) |
| `lead_chat_mapping` | Маппинг lead_id → Telegram chat + dify_dataset_id |
| `prompts` | Промпты с версионированием |
| `extracted_tasks` | Задачи и дедлайны из транскриптов (WF06) |
| `system_settings` | Глобальные настройки (ID общего датасета Dify и т.д.) |

### Полезные запросы

```bash
PG="docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n"

# Статус обработки файлов
$PG -c "SELECT id, filename, status, summary_sent FROM processed_files ORDER BY id DESC LIMIT 10;"

# Клиенты и их Dify dataset IDs
$PG -c "SELECT lead_id, lead_name, curators, dify_dataset_id FROM lead_chat_mapping;"

# Саммари за сегодня
$PG -c "SELECT lead_id, source_type, LEFT(summary_text,100) FROM client_summaries WHERE summary_date=CURRENT_DATE;"

# Промпты
$PG -c "SELECT name, is_active, version FROM prompts ORDER BY name;"

# Задачи из транскриптов
$PG -c "SELECT lead_id, task_desc, assignee, deadline FROM extracted_tasks ORDER BY created_at DESC LIMIT 10;"

# Сбросить summary_sent для повторного дайджеста
$PG -c "UPDATE processed_files SET summary_sent=false WHERE id IN (1,2,3);"

# Сбросить зависшие файлы
$PG -c "DELETE FROM processed_files WHERE status='transcribing' AND created_at < NOW()-INTERVAL '30 minutes';"
```

---

## 7. n8n Public API

**Base URL**: `http://localhost:5678/api/v1`  
**Auth**: `X-N8N-API-KEY: {token}` (JWT из таблицы `user_api_keys`)

### Получить список воркфлоу

```bash
curl http://localhost:5678/api/v1/workflows \
  -H "X-N8N-API-KEY: TOKEN"
```

### Импортировать воркфлоу

```bash
# Обязательно очистить JSON — только name/nodes/connections/settings
python3 -c "
import json
d = json.load(open('workflow.json'))
payload = {k: d[k] for k in ['name','nodes','connections','settings'] if k in d}
print(json.dumps(payload))
" | curl -X POST http://localhost:5678/api/v1/workflows \
  -H "X-N8N-API-KEY: TOKEN" \
  -H "Content-Type: application/json" -d @-
```

### Активировать воркфлоу

```bash
curl -X POST "http://localhost:5678/api/v1/workflows/{id}/activate" \
  -H "X-N8N-API-KEY: TOKEN"
```

### Получить API key из БД

```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT label, LEFT(\"apiKey\",40) FROM public.user_api_keys ORDER BY \"createdAt\" DESC LIMIT 5;"
```

---

## 8. summaries-nginx (статические файлы)

**URL**: `http://84.252.100.93:8181`  
**Путь к файлам**: `/summaries/YYYY-MM-DD/LEAD-XXXX_type_YYYY-MM-DD.md`

### Структура URL

```
http://84.252.100.93:8181/summaries/           ← index (autoindex)
http://84.252.100.93:8181/summaries/2026-02-26/  ← файлы за дату
http://84.252.100.93:8181/summaries/2026-02-26/LEAD-4405_call_2026-02-26.md
http://84.252.100.93:8181/summaries/2026-02-26/LEAD-4405_chat_2026-02-26.md
```

### Health check

```bash
curl http://localhost:8181/health
# → ok
```

### Записать .md файл (из n8n Code node)

WF03 должен записывать файлы в volume `summaries_data`:
```javascript
// В n8n нет прямого доступа к файловой системе — используй Write Binary File node
// Путь внутри контейнера: /summaries/YYYY-MM-DD/LEAD-XXX_call_YYYY-MM-DD.md
```

---

## 9. Healthchecks (smoke tests)

```bash
# n8n
curl -sf http://localhost:5678/healthz && echo "n8n OK"

# PostgreSQL
docker exec mvp-auto-summary-postgres-1 pg_isready -U n8n && echo "PG OK"

# transcribe
curl -sf http://localhost:9001/health && echo "transcribe OK"

# Dify
curl -sf http://localhost/v1/datasets?limit=1 \
  -H "Authorization: Bearer dataset-k7rrBrS6TsEixGGIyAvywfb0" | grep -q '"data"' && echo "Dify OK"

# summaries nginx
curl -sf http://localhost:8181/health && echo "nginx OK"

# Telegram Bot
curl -sf "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/getMe" | python3 -c "
import sys,json; d=json.load(sys.stdin)
print('Telegram OK:', d['result']['username'])"

# GLM-4
curl -sf -X POST https://open.bigmodel.cn/api/paas/v4/chat/completions \
  -H "Authorization: Bearer ${GLM4_API_KEY}" \
  -H "Content-Type: application/json" \
  -d '{"model":"glm-4.7-flash","messages":[{"role":"user","content":"1+1=?"}],"max_tokens":5,"thinking":{"type":"disabled"}}' \
  | python3 -c "import sys,json; print('GLM4 OK:', json.load(sys.stdin)['choices'][0]['message']['content'])"
```

---

*Обновлено: 2026-02-26 — Dify per-client KB, n8n API, summaries-nginx, актуальные dataset IDs*
