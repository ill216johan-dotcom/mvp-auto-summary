# API Contracts — External Services

> Все API-контракты используемых внешних сервисов.  
> Обновлено: 2026-03-02 — LLM = Claude через z.ai (Anthropic API), STT = Whisper self-hosted, Dify per-client RAG.

---

## 1. Whisper (STT) — Активный провайдер

> ⚠️ **SpeechKit и AssemblyAI отключены**. Используем self-hosted faster-whisper.

**Endpoint:** `POST {WHISPER_URL}/v1/audio/transcriptions`  
Где `WHISPER_URL` по умолчанию `http://whisper:8000` (внутри docker сети).

### Request
Мы используем прямой вызов Whisper API, минуя старый адаптер `transcribe:9001` (т.к. он не поддерживал multipart/form-data загрузку).

```bash
curl -X POST http://whisper:8000/v1/audio/transcriptions \
  -H "Content-Type: multipart/form-data" \
  -F "file=@audio.mp3" \
  -F "language=ru"
```

### Response
```json
{
  "text": "Транскрибированный текст разговора..."
}
```

**Особенности:**
- Работает на CPU. Транскрибация занимает ~1.3x от реальной длительности аудио.
- Таймаут в Python-клиенте увеличен до 900 секунд (15 минут), чтобы не прерывать длинные звонки.

---

## 2. LLM — Claude 3.5 Haiku через z.ai (Anthropic API)

> ⚠️ **КРИТИЧНО**: Несмотря на имя переменных `GLM4_*` в `.env`, фактический API — это **Anthropic Messages API**.
> Это **НЕ** OpenAI-compatible. Формат запросов/ответов отличается.

**Endpoint**: `POST https://api.z.ai/api/anthropic/v1/messages`  
**Auth**: `x-api-key: {GLM4_API_KEY}` + `anthropic-version: 2023-06-01`  
**НЕ** `Authorization: Bearer`!

### Request

```bash
curl -X POST https://api.z.ai/api/anthropic/v1/messages \
  -H "x-api-key: 99918695e8de4146a3303043154f4c51.Op8sSKnavRz8PrIQ" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-haiku-20241022",
    "max_tokens": 2000,
    "messages": [
      { "role": "user", "content": "Привет" }
    ]
  }'
```

### Response

```json
{
  "id": "msg_xxx",
  "type": "message",
  "role": "assistant",
  "content": [
    { "type": "text", "text": "Привет! Чем могу помочь?" }
  ],
  "model": "claude-3-5-haiku-20241022",
  "usage": { "input_tokens": 10, "output_tokens": 20 }
}
```

### Извлечение ответа

```python
# Python:
text = response['content'][0]['text']

# JavaScript (n8n Code node):
const text = $json.content?.[0]?.text || 'Ошибка генерации';
```

### Переменные окружения

```
GLM4_API_KEY=99918695e8de4146a3303043154f4c51.Op8sSKnavRz8PrIQ
GLM4_BASE_URL=https://api.z.ai/api/anthropic
GLM4_MODEL=claude-3-5-haiku-20241022
```

### Сравнение OpenAI vs Anthropic форматов

| | OpenAI (старый хардкод WF03) | Anthropic (фактический) |
|--|--------------------------------|---------------------------|
| Endpoint | `/v4/chat/completions` | `/v1/messages` |
| Auth header | `Authorization: Bearer xxx` | `x-api-key: xxx` |
| Extra header | — | `anthropic-version: 2023-06-01` |
| Response | `choices[0].message.content` | `content[0].text` |

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

## 5. transcribe service (internal, Strategy Pattern)

**URL (docker network)**: `http://transcribe:9001`  
**URL (host)**: `http://localhost:9001`  
**STT Provider**: задаётся через `STT_PROVIDER` в `.env`

### Поддерживаемые провайдеры

| Provider | .env | Стоимость | Примечание |
|----------|------|-----------|------------|
| Whisper | `STT_PROVIDER=whisper` | Бесплатно | Текущий, WHISPER_URL=http://whisper:8000 |
| SpeechKit | `STT_PROVIDER=speechkit` | ~25K руб/мес | Отключён |
| AssemblyAI | `STT_PROVIDER=assemblyai` | ~$0.006/мин | Не тестирован |

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
→ { "status": "ok", "provider": "whisper" }
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

## 10. Whisper API (self-hosted, faster-whisper-server)

**URL (docker network)**: `http://whisper:8000`  
**ВАЖНО**: Порт **8000**, не 9000!

### Transcribe

```bash
curl -X POST http://whisper:8000/v1/audio/transcriptions \
  -F "file=@audio.webm" \
  -F "model=medium" \
  -F "language=ru"
```

### Response

```json
{
  "text": "Транскрибированный текст..."
}
```

### Переменные окружения

```
STT_PROVIDER=whisper
WHISPER_URL=http://whisper:8000
WHISPER_MODEL=medium
```

### Производительность (CPU, 10 cores Xeon Gold 6240R)

| Аудио | Модель | Время | Результат |
|-------|--------|-------|-----------|
| 2:12 (русский) | medium | ~5 мин | 1574 символов |
| тишина | medium | <1 мин | 0 символов (нет галлюцинаций) |

---

*Обновлено: 2026-03-02 — LLM = Claude/z.ai (Anthropic API), STT = Whisper medium self-hosted, transcribe с Strategy Pattern*

---

## 11. Bitrix24 Webhook Server (Входящий)

**Endpoint:** `POST http://84.252.100.93:8009/`  
**Назначение:** Приём событий от Bitrix24 о завершении звонков (событие `OnVoximplantCallEnd`).

### Request от Bitrix24 (application/x-www-form-urlencoded)
```
event=ONVOXIMPLANTCALLEND
&data[CALL_ID]=externalCall.xxx
&data[CALL_DURATION]=120
&data[PHONE_NUMBER]=+79991234567
&data[RECORD_FILE_ID]=341880
```

### Логика обработки
1. Сервер находит звонок в `bitrix_calls` (по `CALL_ID` или `CRM_ACTIVITY_ID`).
2. Обогащает запись `record_file_id`.
3. Сразу запускает скачивание (через `disk.file.get`) и транскрибацию (в Whisper).
4. **Важно:** Поскольку `event.bind` требует OAuth-авторизации, а у нас только webhook-токен, на данный момент сервер просто запущен, но событие в Битриксе не зарегистрировано. Вместо этого используется polling каждые 30 минут (`poll_new_recordings`).
