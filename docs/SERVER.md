# 🖥️ Подключение к серверу (mvp-auto-summary)

## Краткая справка

| Параметр | Значение |
|----------|----------|
| **IP** | `84.252.100.93` |
| **Пользователь** | `root` |
| **Пароль** | `xe1ZlW0Rpiyk` |
| **SSH порт** | `22` |
| **SSH ключ** | `C:\Users\User\.ssh\mvp_server` |

---

## Подключение через SSH ключ (РЕКОМЕНДУЕТСЯ)

```powershell
# Базовое подключение
ssh -i C:\Users\User\.ssh\mvp_server -o StrictHostKeyChecking=no root@84.252.100.93

# Выполнить команду без интерактивного входа
ssh -i C:\Users\User\.ssh\mvp_server -o StrictHostKeyChecking=no root@84.252.100.93 "команда"

# Примеры:
ssh -i C:\Users\User\.ssh\mvp_server -o StrictHostKeyChecking=no root@84.252.100.93 "docker ps"
ssh -i C:\Users\User\.ssh\mvp_server -o StrictHostKeyChecking=no root@84.252.100.93 "tail -50 /root/bitrix_sync.log"
```

## Подключение через пароль (альтернатива)

```powershell
# Обычный SSH (потребует ввод пароля вручную)
ssh root@84.252.100.93
# Пароль: xe1ZlW0Rpiyk
```

---

## Деплой файлов (ОБЯЗАТЕЛЬНАЯ последовательность)

> ⚠️ **Важно**: `scp` обновляет файлы на хосте, но контейнер использует build-time образ.
> Всегда после `scp` делай `docker cp` в контейнер!

```powershell
# 1. Скопировать файл на хост
scp -i C:\Users\User\.ssh\mvp_server путь\к\файлу root@84.252.100.93:/root/mvp-auto-summary/путь/

# 2. Скопировать в контейнер (ОБЯЗАТЕЛЬНО!)
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 "docker cp /root/mvp-auto-summary/путь/файл mvp-auto-summary-orchestrator-1:/app/путь/файл"

# Деплой папки docs (только scp, без docker cp — документация не нужна в контейнере)
scp -i C:\Users\User\.ssh\mvp_server -r C:\Projects\mvp-auto-summary\docs\ root@84.252.100.93:/root/mvp-auto-summary/
```

### Деплой нескольких файлов сразу

```powershell
# Скопировать все файлы app/ на хост
scp -i C:\Users\User\.ssh\mvp_server -r C:\Projects\mvp-auto-summary\app\ root@84.252.100.93:/root/mvp-auto-summary/

# Скопировать всё в контейнер
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 "docker cp /root/mvp-auto-summary/app/. mvp-auto-summary-orchestrator-1:/app/"
```

---

## Важные пути на сервере

```
/root/
├── mvp-auto-summary/           # Наш проект (auto-summary)
│   ├── docker-compose.yml      # Docker конфигурация
│   ├── .env                    # Переменные окружения
│   ├── requirements.txt        # Python зависимости (requests добавлен!)
│   ├── app/                    # Python orchestrator
│   │   ├── config.py           # Настройки (BITRIX_* поля + llm_api_key alias)
│   │   ├── core/               # db, llm, dify_api, telegram_api
│   │   ├── tasks/              # bitrix_sync, bitrix_summary, WF01-WF06
│   │   ├── integrations/       # bitrix24.py (API клиент)
│   │   ├── scheduler.py        # Bitrix job 06:00 + Jitsi jobs
│   │   └── bot/                # Telegram bot handler
│   ├── services/transcribe/    # STT адаптер
│   ├── scripts/
│   │   ├── run_historical_sync.py  # Скрипт исторической синхронизации
│   │   ├── migrate_db_v3.sql       # Миграция БД (уже применена)
│   │   └── bitrix_e2e_test.py      # E2E тест интеграции
│   └── docs/                   # Документация
│
├── bitrix_sync.log             # Лог исторической синхронизации
├── openclaw/                   # OpenClaw (соседний проект)
│   ├── docker-compose.yml
│   └── .env                    # ZAI_API_KEY
│
└── dify/                       # Dify.ai исходники
    └── docker/                 # Dify docker-compose
```

### Ключевые сервисы проекта

| Сервис | URL | Описание |
|--------|-----|----------|
| **Dify UI** | `https://dify-ff.duckdns.org` | RAG-чат, Knowledge Bases |
| **Summaries** | `http://84.252.100.93:8181/summaries/` | Static .md саммари |
| **Whisper** | `http://localhost:8000` (internal) | STT транскрибация |
| **Embeddings** | `http://84.252.100.93:8081` | Векторизация текста |
| **Telegram Bot** | `@ffp_report_bot` | Дайджест и статус |

---

## Полезные команды

### Управление mvp-auto-summary

```bash
# Статус контейнеров
docker compose -f /root/mvp-auto-summary/docker-compose.yml ps

# Логи orchestrator (последние 100 строк)
docker compose -f /root/mvp-auto-summary/docker-compose.yml logs --tail=100 -f orchestrator

# Перезапуск
cd /root/mvp-auto-summary && docker compose restart

# Полный перезапуск
cd /root/mvp-auto-summary && docker compose down && docker compose up -d
```

### База данных (PostgreSQL)

```bash
# Подключиться к БД
docker exec -it mvp-auto-summary-postgres-1 psql -U n8n -d n8n

# Список блокнотов Dify (лиды и контакты)
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  'SELECT lead_id, lead_name, dify_dataset_id FROM lead_chat_mapping ORDER BY lead_id;'

# Статус обработанных файлов (Jitsi)
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "SELECT status, COUNT(*) FROM processed_files GROUP BY status;"

# Количество загруженных лидов/контактов из Битрикса
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "SELECT entity_type, COUNT(*) FROM bitrix_leads GROUP BY entity_type;"

# Количество активностей (звонки, письма, комменты)
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "SELECT activity_type, COUNT(*) FROM bitrix_activities GROUP BY activity_type;"

# Статус синхронизации активностей
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "SELECT entity_type, activities_synced, last_activity_date, updated_at FROM bitrix_sync_state LIMIT 20;"
```

### Bitrix24 синхронизация

```bash
# Статус исторической синхронизации (лог)
tail -100 /root/bitrix_sync.log

# Проверить — жив ли процесс исторической синхронизации
ps aux | grep run_historical | grep -v grep

# Запустить историческую синхронизацию заново (если упала)
docker exec -d mvp-auto-summary-orchestrator-1 \
  python /app/scripts/run_historical_sync.py >> /root/bitrix_sync.log 2>&1 &

# Запустить Bitrix синхронизацию вручную (только Step 1 — загрузка лидов)
docker exec mvp-auto-summary-orchestrator-1 python -c "
import asyncio
from app.tasks.bitrix_sync import run_bitrix_sync
asyncio.run(run_bitrix_sync())
"

# Запустить Bitrix саммари вручную (Step 2 — генерация саммари в Dify)
docker exec mvp-auto-summary-orchestrator-1 python -c "
import asyncio
from app.tasks.bitrix_summary import run_bitrix_summary
asyncio.run(run_bitrix_summary())
"
```

### Проверить переменные окружения Bitrix в контейнере

```bash
docker exec mvp-auto-summary-orchestrator-1 env | grep BITRIX
# Должно показать:
# BITRIX_WEBHOOK_URL=https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/
# BITRIX_CONTRACT_FIELD=UF_CRM_1632960743049
# BITRIX_SYNC_HOUR=6
```

### Dify API

```bash
# Список датасетов (блокнотов)
curl -s 'https://dify-ff.duckdns.org/v1/datasets?page=1&limit=100' \
  -H 'Authorization: Bearer dataset-zyLYATai9CmALb3SzNYkRkjk' | python3 -m json.tool | grep name

# Добавить документ в датасет
curl -X POST 'https://dify-ff.duckdns.org/v1/datasets/{dataset_id}/document/create-by-text' \
  -H 'Authorization: Bearer dataset-zyLYATai9CmALb3SzNYkRkjk' \
  -H 'Content-Type: application/json' \
  -d '{"name": "doc_name", "text": "content", "indexing_technique": "economy"}'
```

### Управление OpenClaw (соседний проект)

```bash
# Статус контейнеров
docker compose -f /root/openclaw/docker-compose.yml ps

# Логи
docker compose -f /root/openclaw/docker-compose.yml logs --tail=100 -f openclaw-gateway

# Перезапуск
cd /root/openclaw && docker compose restart
```

---

## Диагностика проблем

### Статус исторической синхронизации

```bash
# Показать последние строки лога + статус процесса
tail -80 /root/bitrix_sync.log && echo "---" && ps aux | grep run_historical | grep -v grep

# Если процесс завершился — проверить итоги в БД
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "
SELECT
  (SELECT COUNT(*) FROM bitrix_leads WHERE entity_type='lead') AS leads,
  (SELECT COUNT(*) FROM bitrix_leads WHERE entity_type='contact') AS contacts,
  (SELECT COUNT(*) FROM bitrix_activities) AS activities,
  (SELECT COUNT(*) FROM bitrix_summaries) AS summaries;
"
```

### Сервер недоступен

```powershell
# Проверка пинга
ping 84.252.100.93

# Проверка SSH порта
powershell -Command "Test-NetConnection -ComputerName 84.252.100.93 -Port 22"
```

### Orchestrator не стартует

```bash
# Проверить логи
docker compose -f /root/mvp-auto-summary/docker-compose.yml logs --tail=50 orchestrator

# Проверить .env
cat /root/mvp-auto-summary/.env | grep -v PASSWORD | grep -v KEY

# Пересоздать контейнеры
cd /root/mvp-auto-summary && docker compose down && docker compose up -d
```

### Whisper не транскрибирует

```bash
# Проверить очередь
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "SELECT status, COUNT(*) FROM processed_files GROUP BY status;"

# Логи transcribe сервиса
docker compose -f /root/mvp-auto-summary/docker-compose.yml logs --tail=50 transcribe

# Проверить Whisper напрямую
curl http://localhost:8000/health
```

### Dify не принимает документы (Error 400)

```bash
# Проверить embeddings
curl http://84.252.100.93:8081/v1/embeddings \
  -H 'Content-Type: application/json' \
  -d '{"input":"test","model":"sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"}'

# Если embeddings отвечают — настроить в Dify UI:
# Settings → Model Providers → OpenAI-compatible
# Base URL: http://embeddings/v1
# Set as Default for Text Embedding
```

---

## Решение частых проблем

### 1. SSH ключ не работает (Permission denied)

```powershell
# Проверить права на ключ (Windows)
icacls C:\Users\User\.ssh\mvp_server
# Должно показать только текущего пользователя

# Если права неверные — сбросить
icacls C:\Users\User\.ssh\mvp_server /inheritance:r /grant:r "%USERNAME%:R"
```

### 2. Переменные окружения не применяются

**Проблема:** Изменили `.env`, но изменения не работают.

**Решение:** Нужно перезапустить контейнеры:
```bash
cd /root/mvp-auto-summary && docker compose down && docker compose up -d
```

### 3. Bitrix синхронизация — `requests` не найден

**Проблема:** `ModuleNotFoundError: No module named 'requests'`

**Решение:** Добавить в requirements.txt и пересобрать:
```bash
# На сервере
echo "requests>=2.31.0" >> /root/mvp-auto-summary/requirements.txt
docker compose -f /root/mvp-auto-summary/docker-compose.yml build orchestrator
docker compose -f /root/mvp-auto-summary/docker-compose.yml up -d orchestrator
```

### 4. Файлы зависли в статусе `queued`/`transcribing`

**Проблема:** Файлы не двигаются по pipeline.

**Решение:**
```bash
# Сбросить зависшие файлы
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "UPDATE processed_files SET status='pending' WHERE status IN ('queued','transcribing') AND updated_at < NOW() - INTERVAL '1 hour';"
```

### 5. Промпты для LLM

Промпты хранятся в БД (таблица `prompts`). Редактировать через psql:
```bash
docker exec -it mvp-auto-summary-postgres-1 psql -U n8n -d n8n
-- Обновить промпт
UPDATE prompts SET prompt_text='новый текст' WHERE name='call_summary_prompt';
```

### 6. Блокнот ФФ не создаётся в Dify

**Проблема:** Лид имеет ФФ-номер в `TITLE`, но блокнот называется `BX-LEAD-*`

**Решение:** Проверить, что функция `_extract_ff_number` правильно парсит название:
```bash
docker exec mvp-auto-summary-orchestrator-1 python -c "
from app.tasks.bitrix_summary import _extract_ff_number
print(_extract_ff_number('Иван Петров, ФФ-4405'))  # должно вернуть 'ФФ-4405'
print(_extract_ff_number('Договор ФФ-18'))           # должно вернуть 'ФФ-18'
print(_extract_ff_number('Без договора'))             # должно вернуть None
"
```

---

## Архитектура блокнотов Dify

| Тип клиента | Источник ФФ-номера | Название блокнота |
|---|---|---|
| Контакт с договором (поле `UF_CRM_1632960743049`) | Поле договора | `ФФ-4405` |
| Лид с ФФ в TITLE | Regex из `TITLE` | `ФФ-4405` |
| Лид без ФФ-номера | — | `BX-LEAD-{id}` |
| Контакт без договора | — | `BX-CONTACT-{id}` |

RAG-чат "ФФ Ассистент куратора" понимает запросы вида **"как там ФФ-4405?"** — ищет по блокноту с таким именем.

---

*Обновлено: 2026-03-09 — добавлена Bitrix24 интеграция, SSH ключ, команды синхронизации*
