# API Contracts — Внешние сервисы и внутренние методы

> Все API-контракты: внешние сервисы + ключевые внутренние методы Python.
> Обновлено: 2026-03-09 v4.0

---

## 1. LLM — Claude 3.5 Haiku через z.ai

> ⚠️ **КРИТИЧНО**: Несмотря на имена переменных `GLM4_*` в `.env`, фактический API — **Anthropic Messages API**.
> Это **НЕ** OpenAI-compatible. `Authorization: Bearer` не работает.

**Endpoint**: `POST https://api.z.ai/api/anthropic/v1/messages`
**Auth**: `x-api-key: {LLM_API_KEY}` + `anthropic-version: 2023-06-01`

### Запрос

```bash
curl -X POST https://api.z.ai/api/anthropic/v1/messages \
  -H "x-api-key: $LLM_API_KEY" \
  -H "anthropic-version: 2023-06-01" \
  -H "Content-Type: application/json" \
  -d '{
    "model": "claude-3-5-haiku-20241022",
    "max_tokens": 1500,
    "system": "Ты бизнес-аналитик...",
    "messages": [{"role": "user", "content": "Текст транскрипции..."}]
  }'
```

### Ответ

```json
{
  "content": [{"type": "text", "text": "## Резюме\n..."}],
  "usage": {"input_tokens": 1200, "output_tokens": 400}
}
```

### Переменные окружения (`.env` → `config.py` alias)

```env
GLM4_API_KEY=...          → settings.llm_api_key
GLM4_BASE_URL=https://api.z.ai/api/anthropic  → settings.llm_base_url
GLM4_MODEL=claude-3-5-haiku-20241022          → settings.llm_model
```

---

## 2. Dify.ai (RAG + Knowledge Base)

**UI**: `https://dify-ff.duckdns.org`
**API Base**: `http://84.252.100.93/v1` (внутри VPS) или `https://dify-ff.duckdns.org/v1`
**Auth**: `Authorization: Bearer {DIFY_API_KEY}`

> Два типа ключей:
> - `dataset-xxx` — Knowledge Base API (для создания/наполнения блокнотов). Текущий: в `.env`
> - `app-xxx` — App API (для chatbot). Используется в "ФФ Ассистент куратора"

### 2.1 Создать датасет (блокнот)

```bash
POST /v1/datasets
Authorization: Bearer dataset-xxx
Content-Type: application/json

{
  "name": "ФФ-4405",
  "indexing_technique": "high_quality"
}

# Ответ:
{"id": "uuid-...", "name": "ФФ-4405", ...}
```

> **Важно**: Для `high_quality` нужен настроенный Embeddings provider в Dify UI.
> Без него — ошибка 400 `provider_not_initialize`. См. ERRORS.md E060.

### 2.2 Добавить документ в датасет

```bash
POST /v1/datasets/{dataset_id}/document/create-by-text
Authorization: Bearer dataset-xxx
Content-Type: application/json

{
  "name": "[2026-03-08] ФФ-4405 — Битрикс CRM",
  "text": "# Клиент: ФФ-4405\n\n## Резюме (2026-03-08)\n...",
  "indexing_technique": "high_quality",
  "process_rule": {"mode": "automatic"}
}

# Ответ:
{"document": {"id": "doc-uuid", "name": "...", "indexing_status": "waiting"}}
```

### 2.3 Список датасетов

```bash
GET /v1/datasets?limit=100
Authorization: Bearer dataset-xxx
```

### 2.4 Текущие датасеты (зафиксированные вручную)

| Название | Dataset ID | Описание |
|----------|-----------|----------|
| База знаний (legacy) | `ba120e09-0119-438f-b6d6-884e73b73334` | Старый общий KB |
| Общая документация ФФ | `727b7015-5c9f-4375-83fd-6b2967ef8637` | Оферта, WMS-инструкция |
| LEAD-4405 ФФ-4405 | `9e65a348-9a04-4ab5-a2ed-4ae766cb11fb` | Клиент 4405 |
| LEAD-987 | `9fec3f54-b7f4-4620-b562-a5266d7206db` | Клиент 987 |
| LEAD-1381 | `54a97db4-3532-41c2-bab0-fd5ac6dc86e8` | Клиент 1381 |
| LEAD-2048 | `205f9a3b-bab3-4967-9887-ed25ea15b506` | Клиент 2048 |
| LEAD-4550 | `be1b0752-4aa5-4a75-a950-993fd4b24353` | Клиент 4550 |
| LEAD-506 | `8b5508b7-5e17-470c-9f33-a6d1443d5ea2` | Клиент 506 |

> Новые датасеты для Bitrix-лидов создаются **автоматически** при первом саммари.

### 2.5 Embeddings (обязательно для high_quality)

- **Container**: `embeddings` (ghcr.io/huggingface/text-embeddings-inference:cpu-latest)
- **Internal URL**: `http://embeddings/v1`
- **Host port**: `8081`
- **Model**: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`

Настройка в Dify UI: Settings → Model Providers → OpenAI-compatible:
- Base URL: `http://embeddings/v1`
- API Key: `local-embeddings` (любая строка)
- Model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Set as Default for **Text Embedding**

### 2.6 Переменные окружения

```env
DIFY_API_KEY=dataset-k7rrBrS6TsEixGGIyAvywfb0
DIFY_BASE_URL=http://84.252.100.93
DIFY_CHATBOT_URL=http://84.252.100.93
```

---

## 3. Bitrix24 CRM REST API

**Webhook URL**: `https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/`
**Auth**: URL содержит токен — бессрочный webhook, не OAuth
**Лимит**: 2 запроса/сек, 50 записей/страницу (пагинация через `next`)
**Объём**: 30 324 лидов + 3 774 контактов (проверено 2026-03-09)

### 3.1 Ключевые методы

| Метод | Описание |
|-------|----------|
| `crm.lead.list` | Все лиды. Параметры: `select`, `filter`, `order`, `start` |
| `crm.contact.list` | Все контакты |
| `crm.activity.list` | Активности: `TYPE_ID=1` (звонки), `TYPE_ID=4` (письма) |
| `crm.timeline.comment.list` | Комментарии по сущности |
| `voximplant.statistic.get` | Статистика звонков + URL записей |
| `user.get` | Имена пользователей по ID |
| `crm.lead.fields` | Список всех полей (включая UF_*) |
| `batch` | До 50 запросов за раз |

### 3.2 Поле договора

```
Field ID:  UF_CRM_1632960743049
Формат:    "ФФ-18", "ФФ-4405", "FF-100"
Regex:     (?:FF|ФФ)-(\d+)   (case-insensitive)
```

Подтверждено через `scripts/bitrix_discover_fields.py`.

### 3.3 Пример вызова (Python)

```python
from app.integrations.bitrix24 import Bitrix24Client

client = Bitrix24Client(settings.bitrix_webhook_url)

# Получить все лиды (автопагинация)
leads = client.call_list('crm.lead.list', {
    'select': ['ID', 'TITLE', 'UF_CRM_1632960743049', 'RESPONSIBLE_ID']
})

# Звонки по лиду
calls = client.call_list('crm.activity.list', {
    'filter': {'OWNER_ID': lead_id, 'OWNER_TYPE_ID': 1, 'TYPE_ID': 1},
    'select': ['ID', 'DESCRIPTION', 'DIRECTION', 'DURATION', 'START_TIME']
})

client.close()
```

### 3.4 ID-архитектура

```
crm.lead.list   → OWNER_TYPE_ID=1 → diffy_lead_id = "BX-LEAD-{ID}"
crm.contact.list → OWNER_TYPE_ID=3:
  есть UF_CRM_1632960743049 = "ФФ-4405" → diffy_lead_id = "LEAD-4405"
  нет поля                              → diffy_lead_id = "BX-CONTACT-{ID}"
```

### 3.5 Переменные окружения

```env
BITRIX_WEBHOOK_URL=https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/
BITRIX_CONTRACT_FIELD=UF_CRM_1632960743049
BITRIX_SYNC_HOUR=6
BITRIX_SYNC_ENABLED=True
```

---

## 4. Whisper API (self-hosted)

**URL**: `http://whisper:8000` (внутри docker) / `http://localhost:8000` (с хоста)
**Container**: `fedirz/faster-whisper-server:latest-cpu`

### 4.1 Транскрипция

```bash
curl -X POST http://localhost:8000/v1/audio/transcriptions \
  -F "file=@audio.webm" \
  -F "model=medium" \
  -F "language=ru"

# Ответ:
{"text": "Здравствуйте, мы хотели обсудить..."}
```

### 4.2 Для записей Bitrix (через requests)

```python
# В bitrix_summary.py — transcribe_pending_calls()
asr_url = transcribe_url.rstrip("/") + "/asr"
response = requests.post(asr_url, files={"audio_file": ("audio.mp3", file, "audio/mp3")})
text = response.json().get("text", "")
```

### 4.3 Производительность (CPU, 10 core Xeon)

| Аудио | Модель | Время |
|-------|--------|-------|
| 2:12 русский | medium | ~5 мин |
| Тишина | medium | <1 мин |

### 4.4 Переменные окружения

```env
STT_PROVIDER=whisper
WHISPER_URL=http://whisper:8000
WHISPER_MODEL=medium
TRANSCRIBE_URL=http://transcribe:9001   # для bitrix_summary
```

---

## 5. transcribe сервис (внутренний, :9001)

Адаптер для Jitsi-записей (STT Strategy Pattern). Для Bitrix-записей `bitrix_summary.py` обращается к Whisper напрямую.

```
POST http://transcribe:9001/
{ "filepath": "/recordings/4405_2026-02-26_10-30.webm" }
→ { "status": "queued", "filename": "4405_2026-02-26_10-30.webm" }

POST http://transcribe:9001/check
{ "filename": "4405_2026-02-26_10-30.webm" }
→ { "transcript": "Текст...", "status": "completed" }
→ { "transcript": null, "status": "queued" }

GET http://transcribe:9001/health
→ { "status": "ok", "provider": "whisper" }
```

---

## 6. Telegram Bot API

**Bot**: `@ffp_report_bot`
**Token**: `${TELEGRAM_BOT_TOKEN}`
**Chat ID**: `-1003872092456` ("Отчёты ФФ Платформы")

### Команды

| Команда | Действие |
|---------|----------|
| `/report` | Отчёт по необработанным звонкам |
| `/status` | Статус системы + очереди |
| `/rag` | Ссылка на Dify RAG |
| `/help` | Справка |

### Отправить сообщение (curl)

```bash
curl -X POST "https://api.telegram.org/bot${TELEGRAM_BOT_TOKEN}/sendMessage" \
  -H "Content-Type: application/json" \
  -d '{"chat_id": -1003872092456, "text": "Тест", "parse_mode": "HTML"}'
```

---

## 7. PostgreSQL (внутренний)

```
docker network: postgresql://n8n:ill216johan511lol2@postgres:5432/n8n
host:           postgresql://n8n:ill216johan511lol2@localhost:5432/n8n
```

### Быстрые запросы

```bash
PG="docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n"

# Статус Bitrix синхронизации
$PG -c "SELECT sync_type, status, leads_synced, calls_synced, emails_synced, started_at FROM bitrix_sync_log ORDER BY id DESC LIMIT 5;"

# Количество данных в Bitrix-таблицах
$PG -c "SELECT 'leads' as t, COUNT(*) FROM bitrix_leads UNION ALL SELECT 'calls', COUNT(*) FROM bitrix_calls UNION ALL SELECT 'emails', COUNT(*) FROM bitrix_emails UNION ALL SELECT 'comments', COUNT(*) FROM bitrix_comments UNION ALL SELECT 'summaries', COUNT(*) FROM bitrix_summaries;"

# Найти клиента по ФФ-номеру
$PG -c "SELECT diffy_lead_id, contract_number, title FROM bitrix_leads WHERE title ILIKE '%ФФ-4405%' OR contract_number = '4405';"

# Блокноты Dify (маппинг)
$PG -c "SELECT lead_id, dify_dataset_id FROM lead_chat_mapping WHERE dify_dataset_id IS NOT NULL ORDER BY lead_id LIMIT 20;"

# Саммари за сегодня
$PG -c "SELECT diffy_lead_id, summary_date, calls_count, emails_count, LEFT(summary_text,100) FROM bitrix_summaries WHERE summary_date >= CURRENT_DATE - 1 ORDER BY summary_date DESC LIMIT 10;"

# Jitsi: статус обработки файлов
$PG -c "SELECT status, COUNT(*) FROM processed_files GROUP BY status;"

# Jitsi: клиенты и Dify dataset
$PG -c "SELECT lead_id, lead_name, dify_dataset_id FROM lead_chat_mapping;"
```

---

## 8. DifyClient (Python, `app/core/dify_api.py`)

```python
class DifyClient:
    def create_document_by_text(
        self,
        dataset_id: str,
        name: str,
        text: str,
        indexing_technique: str = "high_quality"
    ) -> str:
        """Создаёт документ в датасете. Возвращает doc_id."""

    def create_dataset(
        self,
        name: str,
        indexing_technique: str = "high_quality"
    ) -> str:
        """Создаёт новый датасет. Возвращает dataset UUID."""

    def close(self) -> None:
        """Закрывает HTTP-соединение."""
```

---

## 9. Database методы Bitrix (`app/core/db.py`)

```python
# Запись
db.save_bitrix_lead(data: dict) -> None
db.save_bitrix_call(data: dict) -> bool          # True = новая запись
db.save_bitrix_email(data: dict) -> bool
db.save_bitrix_comment(data: dict) -> bool
db.save_bitrix_summary(data: dict) -> None       # upsert по (lead_id, date)
db.save_dataset_mapping(lead_id, dataset_id) -> None  # upsert lead_chat_mapping

# Чтение
db.get_bitrix_leads_for_sync() -> list[dict]
db.get_calls_pending_transcription() -> list[dict]    # LIMIT 20, status='pending'
db.get_bitrix_data_for_summary(lead_id, date) -> dict # {calls, emails, comments}
db.get_bitrix_activity_dates(lead_id) -> list[date]   # уникальные даты активности
db.get_dataset_map() -> dict[str, str]            # {lead_id: dify_dataset_id}

# Обновление
db.update_call_transcript(call_id, text, status) -> None

# Логирование синхронизации
db.start_bitrix_sync_log(sync_type) -> int        # возвращает log_id
db.finish_bitrix_sync_log(log_id, status, ...) -> None
```

---

## 10. summaries-nginx (статика)

**URL**: `http://84.252.100.93:8181`

```
http://84.252.100.93:8181/summaries/               ← index
http://84.252.100.93:8181/summaries/2026-03-09/    ← файлы за дату
http://84.252.100.93:8181/summaries/2026-03-09/LEAD-4405_call_2026-03-09.md
```

---

## 11. Яндекс SpeechKit — ❗ ОТКЛЮЧЁН

> SpeechKit отключён с 2026-03-01. Причина: ~25K руб/мес vs 0 руб Whisper.
> Код-адаптер сохранён в `services/transcribe/` на случай возврата.

---

*Создано: 2026-03-02 | Обновлено: 2026-03-09 v4.0 — Bitrix API, DifyClient.create_dataset, db методы*
