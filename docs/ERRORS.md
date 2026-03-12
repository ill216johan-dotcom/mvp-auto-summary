# Known Errors & Troubleshooting

> База знаний ошибок: symptom → root cause → fix
> Обновлено: 2026-03-12 v4.2 — **E069 (критический баг маппинга), E070-E071**

---

## Быстрый поиск

| Код | Тема |
|-----|------|
| E001–E009 | Setup / Docker |
| E010–E019 | Pipeline (Whisper, LLM, Dify) |
| E020–E045 | Deployment / n8n legacy |
| E046–E058 | Recordings / Telegram / Jitsi |
| E059–E060 | Python Orchestrator |
| E061–E065 | Bitrix24 CRM Sync |
| E066–E076 | **Bitrix24 CRM Sync + Dify блокноты** |

**⚠️ КРИТИЧЕСКИЕ:**
- **E069** — Bitrix датасеты в неправильной таблице (ИСПРАВЛЕНО 2026-03-12)

---

## Setup Errors

### E001: n8n не запускается — `N8N_ENCRYPTION_KEY required`
**Fix**: `echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 16)" >> .env && docker compose up -d`

### E002: PostgreSQL connection refused
**Fix**: `docker compose down && docker compose up -d`

---

## Pipeline Errors

### E010: Whisper — `audio_file is required` (422)
**Root Cause**: Файл не передан как binary form-data.
**Fix**: `multipart-form-data`, field name = `audio_file`.

### E011: Whisper OOM
**Fix**: Поменять `WHISPER_MODEL=small`, или увеличить RAM до 8+ GB.

### E012: Whisper timeout
**Fix**: Увеличить timeout (600s+), использовать `small` модель.

### E014: LLM API timeout
**Root Cause**: Транскрипт >50K токенов или временные проблемы z.ai.
**Fix**: Retry с backoff (tenacity уже настроен). При систематическом — разбить на части.

### E015: Telegram — "chat not found"
**Fix**:
```bash
curl "https://api.telegram.org/bot${TOKEN}/getUpdates"
# Найти "chat":{"id":...} — это chat_id
```

### E018: Dify — `Default model not found for text-embedding` (400)
**Root Cause**: В Dify не настроена embedding-модель.
**Fix**: Dify UI → Settings → Model Providers → OpenAI-compatible:
- Base URL: `http://embeddings/v1`
- API Key: `local-embeddings`
- Model: `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`
- Set as **Default** for Text Embedding

### E019: Dify — `provider_not_initialize` при create_dataset
**Одно и то же что E018.** Без embedding-модели `indexing_technique: high_quality` не работает.
**Альтернатива**: использовать `"indexing_technique": "economy"` — без embeddings, но поиск хуже.

---

## Python Orchestrator Errors

### E059: WF03 не запускается (контейнер перезапущен после scheduled time)
**Root Cause**: APScheduler при старте планирует задачи на СЛЕДУЮЩЕЕ время, пропуская прошедшее.
**Fix**: Запустить вручную:
```bash
docker exec mvp-auto-summary-orchestrator-1 python -c "
from app.config import get_settings
from app.tasks.individual_summary import IndividualSummaryTask
# ... запустить task.run()
"
```

### E060: Dify — `provider_not_initialize` (подробно)
**Fix**: См. E018/E019 выше. Embeddings не настроены.

---

## Bitrix24 CRM Sync Errors

### E061: `ModuleNotFoundError: No module named 'app.integrations'`
**Root Cause**: Старый Docker образ без `app/integrations/`.
**Fix**: `docker compose build orchestrator && docker compose up -d orchestrator`

### E062: `AttributeError: Settings object has no attribute 'bitrix_webhook_url'`
**Root Cause**: В контейнере старая версия `app/config.py`.
**Fix**:
```bash
docker compose build orchestrator && docker compose up -d orchestrator
# Или:
docker cp app/config.py mvp-auto-summary-orchestrator-1:/app/app/config.py
```

### E063: Bitrix sync job не добавляется в scheduler
**Root Cause**: `BITRIX_SYNC_ENABLED=False` или `BITRIX_WEBHOOK_URL` пустой.
**Fix**: Проверить `.env`:
```bash
grep BITRIX /root/mvp-auto-summary/.env
# Должно быть:
# BITRIX_WEBHOOK_URL=https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/
# BITRIX_SYNC_ENABLED=True
docker compose restart orchestrator
```

### E064: `relation "bitrix_leads" does not exist`
**Root Cause**: Миграция `migrate_db_v3.sql` не применена.
**Fix**:
```bash
docker cp scripts/migrate_db_v3.sql mvp-auto-summary-postgres-1:/tmp/
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -f /tmp/migrate_db_v3.sql
```

### E065: `Bitrix24 rate limit exceeded after 3 retries` (RuntimeError)
**Root Cause**: Bitrix ограничивает 2 запроса/сек. Большой батч → 429.
**Fix**: Одиночные сбои самоустраняются (retry встроен). При систематических — перенести `BITRIX_SYNC_HOUR=3` (3:00 ночи, минимальный трафик).

---

## Bitrix + Dify автосоздание (E066–E072)

### E066: `ModuleNotFoundError: No module named 'requests'` при запуске run_historical_sync.py
**Дата**: 2026-03-09
**Root Cause**: `bitrix_summary.py` использует `requests` для скачивания записей звонков, но в контейнере установлен только `httpx`.
**Fix**:
```bash
docker exec mvp-auto-summary-orchestrator-1 pip install requests -q
```
**Постоянный фикс**: `requests>=2.31.0` добавлен в `requirements.txt` на сервере.

---

### E067: `IndentationError` в `dify_api.py` после редактирования
**Дата**: 2026-03-09
**Root Cause**: При добавлении метода `create_dataset` через Edit tool нарушились отступы — метод `close()` потерял тело.
**Symptom**:
```
IndentationError: expected an indented block after function definition on line 73
```
**Fix**: Полностью перезаписан `dify_api.py` через `mcp_write`. Финальная версия — 106 строк, все методы с правильными отступами.

---

### E068: `AttributeError: Settings object has no attribute 'glm4_api_key'`
**Дата**: 2026-03-09
**Root Cause**: В `run_historical_sync.py` использовались старые имена полей `glm4_api_key`, `glm4_base_url`, `glm4_model`, тогда как в `config.py` они называются `llm_api_key`, `llm_base_url`, `llm_model`.
**Fix**: Исправлено в скрипте:
```python
# БЫЛО:
llm = LLMClient(api_key=s.glm4_api_key, base_url=s.glm4_base_url, model=s.glm4_model)
# СТАЛО:
llm = LLMClient(api_key=s.llm_api_key, base_url=s.llm_base_url, model=s.llm_model)
```

---

### E069: **КРИТИЧЕСКИЙ БАГ** Bitrix датасеты сохраняются в неправильную таблицу
**Дата**: 2026-03-12 (обнаружено и исправлено)
**Severity:** CRITICAL — влияет на все данные клиентов

**Symptoms:**
- Датасеты Bitrix НЕ сохраняются в `bitrix_leads.dify_dataset_id`
- Повторное создание датасетов при каждом запуске (дубликаты в Dify UI)
- Данные из Telegram/Jitsi НЕ попадают в Bitrix датасеты
- В `bitrix_leads` все `dify_dataset_id = NULL`

**Root Cause:**
`app/core/db.py` использовал старые функции `get_dataset_map()` и `save_dataset_mapping()`, которые работали с таблицей `lead_chat_mapping` (предназначенной для Telegram), вместо новой таблицы `bitrix_leads.dify_dataset_id`.

**Неправильный код:**
```python
# bitrix_summary.py:137
dataset_map = db.get_dataset_map()  # ❌ читал из lead_chat_mapping

# bitrix_summary.py:168
db.save_dataset_mapping(diffy_lead_id, dataset_id)  # ❌ писал в lead_chat_mapping
```

**Fix:**
1. Добавлены новые функции в `db.py`:
   - `get_bitrix_dataset_map()` — читает из `bitrix_leads`
   - `save_bitrix_dataset_mapping()` — пишет в `bitrix_leads`

2. Обновлён `bitrix_summary.py`:
   ```python
   dataset_map = db.get_bitrix_dataset_map()  # ✅ из bitrix_leads
   db.save_bitrix_dataset_mapping(diffy_lead_id, dataset_id)  # ✅ в bitrix_leads
   ```

3. SQL миграция (`scripts/migrate_fix_bitrix_mapping.sql`):
   - Перенесено 4,154 датасета из `lead_chat_mapping` в `bitrix_leads`
   - Удалено 3,366 неправильных записей Bitrix из `lead_chat_mapping`
   - Сохранено 2 Telegram маппинга (правильно)

**Результат миграции:**
| До миграции | После миграции |
|-------------|----------------|
| `bitrix_leads`: 0 с dataset | `bitrix_leads`: 4,154 с dataset ✅ |
| `lead_chat_mapping`: 3,366 Bitrix ❌ | `lead_chat_mapping`: 0 Bitrix ✅ |
| `lead_chat_mapping`: 2 Telegram ✅ | `lead_chat_mapping`: 2 Telegram ✅ |

**Verification:**
```bash
# Проверить что датасеты есть в bitrix_leads
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "SELECT bitrix_entity_type, COUNT(dify_dataset_id) FROM bitrix_leads \
   GROUP BY bitrix_entity_type;"

# Проверить что в lead_chat_mapping нет Bitrix
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "SELECT COUNT(*) FROM lead_chat_mapping \
   WHERE lead_id LIKE 'ФФ-%' OR lead_id LIKE 'BX-%';"
```

**Файлы:**
- `app/core/db.py` — новые функции (+62 строки)
- `app/tasks/bitrix_summary.py` — обновлён (2 строки)
- `scripts/migrate_fix_bitrix_mapping.sql` — миграция (+103 строки)
- `PHASE1_COMPLETION_REPORT.md` — полный отчёт

**Связанные ошибки:**
- E069 — проблема с обновлением файлов в контейнере
- E072 — возможны дубликаты датасетов в Dify UI после этого бага

---

### E070: Дубликаты датасетов в Dify UI после исправления E069
**Дата:** 2026-03-12
**Symptoms:** В Dify UI видно несколько датасетов с одним названием (например, "ФФ-4405", "BX-LEAD-12345")
**Root Cause:** Из-за бага E069 каждый запуск создавал новый датасет (старый не находился в неправильной таблице)
**Fix:**
1. Опционально удалить дубликаты вручную через Dify UI
2. Или оставить (не критично) — система будет использовать правильный датасет из `bitrix_leads.dify_dataset_id`
**Prevention:** После исправления E069 новые дубликаты не создаются

---

### E071: `AttributeError: Database object has no attribute 'get_bitrix_leads_for_sync'` (в контейнере)
**Дата**: 2026-03-09
**Root Cause**: `scp` обновил файлы на хосте (`/root/mvp-auto-summary/`), но контейнер использует файлы из образа (build-time). Новые методы не были доступны.
**Fix**: Копировать файлы **напрямую в контейнер**:
```bash
docker cp /root/mvp-auto-summary/app/core/db.py mvp-auto-summary-orchestrator-1:/app/app/core/db.py
docker cp /root/mvp-auto-summary/app/core/dify_api.py mvp-auto-summary-orchestrator-1:/app/app/core/dify_api.py
docker cp /root/mvp-auto-summary/app/tasks/bitrix_summary.py mvp-auto-summary-orchestrator-1:/app/app/tasks/bitrix_summary.py
```
**Проверка**:
```bash
docker exec mvp-auto-summary-orchestrator-1 python -c \
  "from app.core.db import Database; print(hasattr(Database, 'get_bitrix_leads_for_sync'))"
# True
```

---

### E070: `docker exec ... python /scripts/run_historical_sync.py` — No such file
**Дата**: 2026-03-09
**Root Cause**: `/scripts/` — путь на хосте (`/root/mvp-auto-summary/scripts/`), а не внутри контейнера.
**Fix**: Скопировать скрипт в контейнер:
```bash
docker cp /root/mvp-auto-summary/scripts/run_historical_sync.py \
  mvp-auto-summary-orchestrator-1:/app/run_historical_sync.py
docker exec ... python /app/run_historical_sync.py
```

---

### E071: tmux отсутствует на сервере
**Дата**: 2026-03-09
**Root Cause**: `tmux` не установлен на VPS.
**Symptom**: `bash: line 1: tmux: command not found`
**Workaround**: Использовать `nohup ... &` с перенаправлением в лог:
```bash
nohup docker exec mvp-auto-summary-orchestrator-1 python /app/run_historical_sync.py \
  > /root/bitrix_sync.log 2>&1 &
echo PID:$!

# Следить за прогрессом:
tail -f /root/bitrix_sync.log
```

---

### E072: `ff_number` не определён при `dataset_id` уже есть в `dataset_map`
**Дата**: 2026-03-09
**Root Cause**: Переменная `ff_number` вычислялась только внутри `if not dataset_id:`, но использовалась в цикле по датам (`client_label = ff_number if ff_number else ...`).
**Symptom**: `NameError: name 'ff_number' is not defined`
**Fix**: Вынести вычисление `ff_number` **до** блока `if not dataset_id:`:
```python
# ПРАВИЛЬНО — всегда вычисляется:
ff_number = _extract_ff_number(lead.get("title", "") or lead.get("name", ""))

dataset_id = dataset_map.get(diffy_lead_id, "")
if not dataset_id:
    dataset_name = ff_number if ff_number and not diffy_lead_id.startswith("BX-LEAD-") else diffy_lead_id
    dataset_id = dify.create_dataset(dataset_name)
    ...
```

---

## Jitsi / Recordings Errors

### E016: NFS mount dropped
```bash
mountpoint /mnt/recordings
mount -a
```

### E057: transcribe — очередь переполнена
**Fix**: Увеличить `TRANSCRIBE_QUEUE_SIZE` и/или `TRANSCRIBE_WORKERS`.

### E058: Jibri BUSY — параллельный созвон не записывается
**Fix**:
```bash
cd /opt/jitsi-meet
docker compose -f docker-compose.yml -f jibri.yml up -d --scale jibri=2
```

---

## Telegram (авторизация/выгрузка)

### E047: SMS-код не приходит при авторизации Telethon
**Fix**: Использовать QR-вход: Telegram → Настройки → Устройства → Подключить устройство.

### E048: QR отсканирован, но скрипт не реагирует
**Root Cause**: Старая версия скрипта без `await qr_login.wait(timeout=120)`.
**Fix**: Использовать актуальный `list_telegram_chats.py`.

### E049: Скрипт запрашивает пароль после QR
**Root Cause**: На аккаунте включена двухэтапная проверка. Это нормально.
**Fix**: Ввести облачный пароль. Настройки → Конфиденциальность → Двухэтапная проверка.

### E050: Нужно ли 5 приложений для 5 менеджеров?
**Нет.** Один общий Telegram-аккаунт, добавленный во все чаты. Одно приложение на my.telegram.org.

### E051: Как получить api_id и api_hash
1. Открыть https://my.telegram.org/apps
2. Войти через номер телефона
3. Создать приложение: Platform = Desktop
4. Скопировать **App api_id** и **App api_hash**

### E053: Как заполнить lead_chat_mapping
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "
INSERT INTO lead_chat_mapping (lead_id, lead_name, chat_id, chat_title, chat_type)
VALUES ('101', 'ООО Ромашка', -1009876543210, 'ООО Ромашка', 'supergroup');
"
```

---

## Bitrix24 + Dify автосоздание блокнотов (E073-E076)

### E073: Dify датасеты не создаются — 400 Bad Request
**Symptom**: В логах `bitrix_dataset_create_failed` с ошибкой `HTTP 400`.

**Root Cause**: Код отправлял параметр `indexing_technique` при создании датасета, но Dify API его не принимает (только при создании документа).

**Fix** (применён 2026-03-10):
```python
# В app/core/dify_api.py строка 89:
# ДО:
payload = {"name": name, "indexing_technique": indexing_technique}

# ПОСЛЕ:
payload = {"name": name}
```

**Верификация**:
```bash
grep -c 'bitrix_dataset_create_failed' /root/bitrix_sync.log
# Должно быть 0
```

---

### E074: Блокноты Dify называются BX-LEAD-* вместо ФФ-номеров
**Symptom**: В Dify создаются блокноты `BX-LEAD-1035`, хотя в Битриксе есть ФФ-номер в названии.

**Root Cause**: Логика извлечения ФФ-номера была только в `bitrix_summary.py` (Step 2), но `diffy_lead_id` присваивается в `bitrix_sync.py` (Step 1).

**Fix** (применён 2026-03-10):
```python
# В app/tasks/bitrix_sync.py строка 175:
# ДО:
diffy_lead_id = f"BX-LEAD-{lead_id}"

# ПОСЛЕ:
ff_number = _extract_contract_number(lead.get("TITLE", ""))
diffy_lead_id = ff_number if ff_number else f"BX-LEAD-{lead_id}"
```

**Верификация** (после пересинхронизации):
```bash
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 \
  "docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  'SELECT COUNT(*) FROM bitrix_leads WHERE diffy_lead_id LIKE \'ФФ%\';'"
# Должно показать ~2000+ лидов с ФФ-номерами
```

---

### E075: Поле contract_number (UF_CRM_1632960743049) пустое у всех клиентов
**Symptom**: В БД `bitrix_leads.contract_number` у всех записей `NULL`.

**Root Cause**: В Битриксе поле `UF_CRM_1632960743049` не заполнено ни у одного контакта.

**Решение**: Извлекать ФФ-номер из поля `TITLE` через regex:
```python
# Паттерн: 'Сергей, ФФ-34' → извлекает 'ФФ-34'
m = re.search(r'(?:FF|ФФ|фф)-?(\d+)', title, re.IGNORECASE)
if m:
    return f'ФФ-{m.group(1)}'
```

**Статистика**:
- Всего лидов: 31,005
- С ФФ в title: ~2,044 (~6.6%)
- С заполненным UF_CRM_*: 0

---

### E076: Контакты с договором называются LEAD-4405 вместо ФФ-4405
**Symptom**: Контакты с договором в Dify называются `LEAD-4405`, хотя должно быть `ФФ-4405`.

**Root Cause**: Функция `_extract_contract_number` возвращала только цифры (`return m.group(1)`), а не полный номер.

**Fix** (применён 2026-03-10):
```python
# В app/tasks/bitrix_sync.py строка 58:
# ДО:
return m.group(1)  # Возвращало '4405'

# ПОСЛЕ:
return f'ФФ-{m.group(1)}'  # Возвращает 'ФФ-4405'
```

**Верификация**:
```bash
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 \
  "docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  'SELECT diffy_lead_id, contract_number FROM bitrix_leads WHERE contract_number IS NOT NULL LIMIT 10;'"
# Оба столбца должны быть в формате 'ФФ-XXXX'
```

---

## Частые операции диагностики

### Проверить статус исторической синхронизации
```bash
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 "tail -50 /root/bitrix_sync.log"
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 "ps aux | grep run_historical"
```

### Проверить что данные попали в БД
```bash
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 \
  "docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  'SELECT COUNT(*) FROM bitrix_leads; SELECT COUNT(*) FROM bitrix_calls; SELECT COUNT(*) FROM bitrix_emails;'"
```

### Проверить orchestrator работает (jobs=6)
```bash
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 \
  "docker logs --tail 20 mvp-auto-summary-orchestrator-1"
# Ожидается: scheduler_started jobs=6
```

### Перезапустить историческую синхронизацию (если упала)
```bash
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 "
docker cp /root/mvp-auto-summary/scripts/run_historical_sync.py \
  mvp-auto-summary-orchestrator-1:/app/run_historical_sync.py
nohup docker exec mvp-auto-summary-orchestrator-1 python /app/run_historical_sync.py \
  > /root/bitrix_sync.log 2>&1 &
echo PID:\$!
"
```

---

*Создано: 2026-02-18 | Обновлено: 2026-03-12 v4.2 — E069-E071 (критический баг маппинга ИСПРАВЛЕН)*
