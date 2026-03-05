# 🚀 MVP Auto-Summary - Полное руководство развертывания

## 📋 Содержание
- [Требования](#требования)
- [Архитектура](#архитектура)
- [Пошаговое развертывание](#пошаговое-развертывание)
- [Интеграция Dify](#интеграция-dify)
- [Интеграция Telegram](#интеграция-telegram)
- [Проверка работы](#проверка-работы)
- [Устранение неполадок](#устранение-неполадок)

---

## Требования

### Сервер
- Ubuntu 20.04+ / Debian 11+
- Минимум 4 GB RAM
- 20 GB свободного места
- Docker + Docker Compose
- Доступ к портам: 80, 443, 5678, 8081, 8181, 9000

### API Keys
- GLM-4 API (ZhipuAI): https://open.bigmodel.cn/
- Telegram Bot Token: @BotFather
- Dify API Key (создается после установки Dify)

---

## Архитектура

```
┌─────────────────────────────────────────────────────────────┐
│                     MVP Auto-Summary                        │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  Recordings Directory (/mnt/recordings)                    │
│       ↓                                                     │
│  [WF01] Scanner (каждые 5 мин)                             │
│       ↓                                                     │
│  Whisper Transcription                                     │
│       ↓                                                     │
│  PostgreSQL (processed_files)                              │
│       ↓                                                     │
│  [WF03] Individual Summary (22:00)                         │
│       ↓                                                     │
│  ├─→ Markdown Files (/summaries)                           │
│  ├─→ Dify Knowledge Base (high_quality)                    │
│  └─→ PostgreSQL (client_summaries)                         │
│       ↓                                                     │
│  [WF02] Daily Digest (23:00)                               │
│       ↓                                                     │
│  Telegram Bot → Group Chat                                 │
│                                                             │
└─────────────────────────────────────────────────────────────┘

Components:
├─ orchestrator (Python APScheduler)
├─ postgres (PostgreSQL 15)
├─ whisper (Faster-Whisper)
├─ embeddings (Text Embeddings Inference)
├─ dify/* (Dify AI Platform)
└─ n8n (опционально, заменен на orchestrator)
```

---

## Пошаговое развертывание

### Шаг 1: Подготовка сервера

```bash
# Обновить систему
apt update && apt upgrade -y

# Установить Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Установить Docker Compose
curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
chmod +x /usr/local/bin/docker-compose

# Создать рабочую директорию
mkdir -p /root/mvp-auto-summary
cd /root/mvp-auto-summary
```

### Шаг 2: Клонирование проекта

```bash
# Клонировать репозиторий
git clone https://github.com/YOUR_USERNAME/mvp-autosummary.git .

# Создать необходимые директории
mkdir -p /mnt/recordings
mkdir -p /root/mvp-auto-summary/summaries
```

### Шаг 3: Настройка переменных окружения

Создать `.env` файл:

```bash
cat > .env << 'EOF'
# ============================================================
# MVP Auto-Summary — Environment Variables
# ============================================================

# --- General ---
TIMEZONE=Europe/Moscow

# --- n8n (deprecated, kept for compatibility) ---
N8N_PORT=5678
N8N_USER=admin
N8N_PASSWORD=YOUR_PASSWORD_HERE
N8N_ENCRYPTION_KEY=YOUR_32_CHAR_KEY_HERE
N8N_WEBHOOK_URL=http://YOUR_SERVER_IP:5678

# --- PostgreSQL ---
POSTGRES_PORT=5432
POSTGRES_USER=n8n
POSTGRES_PASSWORD=YOUR_PASSWORD_HERE
POSTGRES_DB=n8n

# --- GLM-4 (ZhipuAI) ---
# Get API key from: https://open.bigmodel.cn/
GLM4_API_KEY=YOUR_GLM4_API_KEY_HERE
GLM4_BASE_URL=https://api.z.ai/api/anthropic
GLM4_MODEL=claude-3-5-haiku-20241022

# --- Telegram ---
# Get from @BotFather
TELEGRAM_BOT_TOKEN=YOUR_BOT_TOKEN_HERE
TELEGRAM_CHAT_ID=YOUR_CHAT_ID_HERE
N8N_SECURE_COOKIE=false

# --- Dify ---
# Will be created after Dify installation
DIFY_API_KEY=YOUR_DIFY_API_KEY_HERE
DIFY_BASE_URL=https://dify-ff.duckdns.org
DIFY_CHATBOT_URL=https://dify-ff.duckdns.org/chat/YOUR_CHATBOT_ID

# --- Web Server ---
SUMMARIES_BASE_URL=http://YOUR_SERVER_IP:8181

# --- Whisper (STT) ---
STT_PROVIDER=whisper
WHISPER_URL=http://whisper:8000
WHISPER_PORT=9000
WHISPER_MODEL=medium
TRANSCRIBE_WORKERS=2
TRANSCRIBE_QUEUE_SIZE=100
WHISPER_TIMEOUT_MIN=600
WHISPER_TIMEOUT_MAX=86400
WHISPER_TIMEOUT_MULTIPLIER=4

# --- Fix for APScheduler ---
N8N_RUNNERS_ENABLED=false
EOF
```

### Шаг 4: Запуск базы данных

```bash
# Запустить PostgreSQL
docker compose up -d postgres

# Дождаться запуска (10-15 секунд)
sleep 15

# Применить миграции
docker exec -i mvp-auto-summary-postgres-1 psql -U n8n -d n8n < schema.sql
```

### Шаг 5: Установка Dify

```bash
# Клонировать Dify
cd /root
git clone https://github.com/langgenius/dify.git
cd dify/docker

# Настроить Dify
cp .env.example .env

# ВАЖНО: Настроить embeddings для high_quality режима
# Отредактировать .env:
nano .env

# Изменить следующие строки:
# OPENAI_API_BASE=http://YOUR_SERVER_IP:8081/v1
# OPENAI_API_KEY=local-embeddings

# Запустить Dify
docker compose up -d

# Дождаться запуска (2-3 минуты)
docker compose ps
```

### Шаг 6: Установка Embeddings сервера

```bash
# Вернуться в проект
cd /root/mvp-auto-summary

# Добавить в docker-compose.yml:
cat >> docker-compose.yml << 'EOF'

  embeddings:
    image: ghcr.io/huggingface/text-embeddings-inference:latest
    container_name: embeddings
    ports:
      - "8081:80"
    environment:
      - MODEL_ID=sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
    restart: unless-stopped
    volumes:
      - embeddings_cache:/data
EOF

# Перезапустить с embeddings
docker compose up -d embeddings

# Проверить работу
curl http://localhost:8081/info
```

### Шаг 7: Настройка Nginx для summaries

```bash
# Установить Nginx
apt install nginx -y

# Создать конфиг
cat > /etc/nginx/sites-available/summaries << 'EOF'
server {
    listen 8181;
    server_name _;

    location /summaries/ {
        alias /root/mvp-auto-summary/summaries/;
        autoindex on;
        add_header Cache-Control no-cache;
    }
}
EOF

# Активировать
ln -s /etc/nginx/sites-available/summaries /etc/nginx/sites-enabled/
nginx -t
systemctl restart nginx
```

### Шаг 8: Создание Dify Knowledge Base

```bash
# Получить API ключ Dify
# 1. Зайти в Dify UI: http://YOUR_SERVER_IP
# 2. Settings → API Keys
# 3. Создать Dataset API Key
# 4. Скопировать в .env (DIFY_API_KEY)

# Создать dataset для тестового клиента
curl -X POST "https://dify-ff.duckdns.org/v1/datasets" \
  -H "Authorization: Bearer YOUR_DIFY_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "LEAD-1000139",
    "description": "Тестовый клиент",
    "indexing_technique": "high_quality"
  }'

# Сохранить возвращенный dataset_id
# Обновить .env: DIFY_DATASET_1000139=<dataset_id>
```

### Шаг 9: Запуск Orchestrator

```bash
cd /root/mvp-auto-summary

# Собрать и запустить
docker compose build orchestrator
docker compose up -d orchestrator

# Проверить логи
docker logs -f mvp-auto-summary-orchestrator-1

# Должно быть:
# - scheduler_configured jobs=6
# - scheduler_started jobs=6
# - bot_starting
```

---

## Интеграция Dify

### Проблема: Dify не может создать документ (500 error)

**Причина:** Не настроен embeddings сервер для high_quality режима

**Решение:**

1. Проверить embeddings сервер:
```bash
curl http://YOUR_SERVER_IP:8081/info
# Должен вернуть JSON с моделью
```

2. Настроить Dify .env:
```bash
cd /root/dify/docker
nano .env

# Изменить:
OPENAI_API_BASE=http://YOUR_SERVER_IP:8081/v1
OPENAI_API_KEY=local-embeddings

# Перезапустить Dify
docker compose restart api worker
```

3. Протестировать создание документа:
```bash
curl -X POST "https://dify-ff.duckdns.org/v1/datasets/DATASET_ID/document/create-by-text" \
  -H "Authorization: Bearer YOUR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test",
    "text": "Test content",
    "indexing_technique": "high_quality",
    "process_rule": {"mode": "automatic"}
  }'

# Должен вернуть 200 и document ID
```

### Economy vs High Quality

- **Economy:** Быстрее, но хуже качество RAG
- **High Quality:** Лучшее качество, требует embeddings сервер

**Код (app/core/dify_api.py):**
```python
indexing_technique: str = "high_quality"  # или "economy"
```

---

## Интеграция Telegram

### Создание бота

1. Найти @BotFather в Telegram
2. Отправить `/newbot`
3. Указать имя и username
4. Получить токен вида: `1234567890:ABCdefGHIjklMNOpqrsTUVwxyz`

### Получение Chat ID

```bash
# Добавить бота в группу
# Отправить сообщение в группу
# Перейти по URL:
https://api.telegram.org/botYOUR_BOT_TOKEN/getUpdates

# Найти "chat":{"id":-100XXXXXXXXXX}
# Это и есть TELEGRAM_CHAT_ID
```

### Тест отправки

```bash
curl -X POST "https://api.telegram.org/botYOUR_BOT_TOKEN/sendMessage" \
  -d "chat_id=YOUR_CHAT_ID" \
  -d "text=Test from MVP Auto-Summary!"
```

---

## Проверка работы

### 1. Проверить scheduler

```bash
docker logs mvp-auto-summary-orchestrator-1 | grep "scheduler_configured"
# Должно быть: jobs=6

# Jobs:
# - WF01: Scan (5 min)
# - WF01: Check pending (5 min)
# - WF03: Individual summaries (22:00)
# - WF06: Deadline extractor (15 min)
# - WF02: Daily digest (23:00)
# - Healthcheck (30 min)
```

### 2. Проверить транскрибацию

```bash
# Загрузить тестовый файл
cp test_video.mp4 /mnt/recordings/1000139_$(date +%Y-%m-%d-%H-%M-%S).mp4

# Подождать 5-10 минут
# Проверить логи:
docker logs mvp-auto-summary-orchestrator-1 | grep "transcription"

# Проверить БД:
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c \
  "SELECT id, filename, status FROM processed_files ORDER BY id DESC LIMIT 5;"
```

### 3. Запустить WF03 вручную

```bash
docker exec mvp-auto-summary-orchestrator-1 python -c "
import sys
sys.path.insert(0, '/app')
from datetime import date
from app.tasks.individual_summary import IndividualSummaryTask
from app.core.db import Database
from app.core.llm import LLMClient
from app.core.dify_api import DifyClient
from app.config import get_settings

settings = get_settings()
db = Database(settings.database_dsn)
llm = LLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
dify = DifyClient(settings.dify_api_key, settings.dify_base_url)

task = IndividualSummaryTask(
    db=db, llm=llm, dify=dify,
    summaries_dir=settings.summaries_dir,
    summaries_base_url=settings.summaries_base_url,
)

result = task.run(target_date=date.today())
print(f'Result: {result}')
"
```

### 4. Запустить WF02 вручную (digest в Telegram)

```bash
docker exec mvp-auto-summary-orchestrator-1 python -c "
import sys
sys.path.insert(0, '/app')
from datetime import date
from app.tasks.daily_digest import DailyDigestTask
from app.core.db import Database
from app.core.llm import LLMClient
from app.core.telegram_api import TelegramSender
from app.config import get_settings

settings = get_settings()
db = Database(settings.database_dsn)
llm = LLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
telegram = TelegramSender(settings.telegram_bot_token)

task = DailyDigestTask(
    db=db, llm=llm, telegram=telegram,
    default_chat_id=settings.telegram_chat_id,
    summaries_base_url=settings.summaries_base_url,
)

result = task.run(target_date=date.today())
print(f'Result: {result}')
"

# Проверить Telegram - должно прийти сообщение!
```

### 5. Проверить Dify

```bash
# Проверить документы в Knowledge Base
curl -s "https://dify-ff.duckdns.org/v1/datasets/DATASET_ID/documents?page=1&limit=10" \
  -H "Authorization: Bearer YOUR_API_KEY" | jq '.data[] | {name, indexing_status}'

# Статус должен быть "completed"
```

---

## Устранение неполадок

### Проблема: "Job not found" или missed jobs

**Решение:**
- Healthcheck job автоматически запустит пропущенные задачи
- `misfire_grace_time=3600` - задачи запускаются в течение 1 часа

**Проверить:**
```bash
docker logs mvp-auto-summary-orchestrator-1 | grep -i "healthcheck\|misfire"
```

### Проблема: Dify возвращает 500/400 при создании документа

**Причина:** Не настроен embeddings сервер

**Решение:** См. раздел "Интеграция Dify" выше

### Проблема: Whisper timeout

**Решение:**
- Увеличить таймауты в .env:
  ```
  WHISPER_TIMEOUT_MIN=1200
  WHISPER_TIMEOUT_MAX=172800
  ```
- Использовать меньшую модель: `WHISPER_MODEL=small` или `base`

### Проблема: Telegram не отправляет

**Проверить:**
1. Bot token валидный
2. Chat ID правильный (отрицательный для групп)
3. Бот добавлен в группу
4. Бот имеет права отправлять сообщения

```bash
# Тест отправки
curl -X POST "https://api.telegram.org/botTOKEN/sendMessage" \
  -d "chat_id=CHAT_ID" \
  -d "text=Test"
```

### Проблема: Postgres connection refused

**Проверить:**
```bash
docker compose ps postgres
docker logs mvp-auto-summary-postgres-1

# Перезапустить
docker compose restart postgres
```

### Проблема: Embeddings сервер недоступен

**Проверить:**
```bash
curl http://YOUR_SERVER_IP:8081/info
docker logs embeddings

# Перезапустить
docker compose restart embeddings
```

---

## Логи и мониторинг

### Просмотр логов

```bash
# Orchestrator
docker logs -f mvp-auto-summary-orchestrator-1

# Postgres
docker logs -f mvp-auto-summary-postgres-1

# Whisper
docker logs -f mvp-auto-summary-whisper-1

# Dify API
docker logs -f docker-api-1

# Embeddings
docker logs -f embeddings
```

### Структура логов

Оркестратор использует structlog:
```
2026-03-05 12:00:00 [info     ] scheduler_started              jobs=6
2026-03-05 12:00:05 [debug    ] transcription_queued           file_id=123
2026-03-05 12:00:10 [info     ] transcription_completed        duration=5.2s
2026-03-05 22:00:00 [info     ] summary_created                lead_id=1000139
2026-03-05 23:00:00 [info     ] telegram_sent                  chars=1114
```

---

## Backup и восстановление

### Backup Postgres

```bash
# Создать backup
docker exec mvp-auto-summary-postgres-1 pg_dump -U n8n n8n > backup_$(date +%Y%m%d).sql

# Восстановить
docker exec -i mvp-auto-summary-postgres-1 psql -U n8n n8n < backup_20260305.sql
```

### Backup Summaries

```bash
# Archive summaries
tar -czf summaries_backup_$(date +%Y%m%d).tar.gz /root/mvp-auto-summary/summaries/

# Restore
tar -xzf summaries_backup_20260305.tar.gz -C /
```

---

## Обновление

```bash
cd /root/mvp-auto-summary

# Pull changes
git pull origin feature/python-orchestrator

# Rebuild and restart
docker compose build orchestrator
docker compose restart orchestrator

# Check logs
docker logs -f mvp-auto-summary-orchestrator-1
```

---

## Дополнительные ресурсы

- [Dify Documentation](https://docs.dify.ai/)
- [Faster-Whisper](https://github.com/guillaumekln/faster-whisper)
- [APScheduler](https://apscheduler.readthedocs.io/)
- [Python Telegram Bot](https://docs.python-telegram-bot.org/)

---

**Версия:** 1.0.0  
**Последнее обновление:** 2026-03-05  
**Автор:** MVP Auto-Summary Team
