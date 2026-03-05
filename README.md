# 🎯 MVP Auto-Summary

**Автоматическая система транскрибации и анализа созвонов с доставкой дайджестов в Telegram**

[![Python 3.11](https://img.shields.io/badge/python-3.11-blue.svg)](https://www.python.org/downloads/)
[![Docker](https://img.shields.io/badge/docker-ready-brightgreen.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

---

## 📖 Описание

MVP Auto-Summary автоматически обрабатывает аудио/видео записи созвонов, транскрибирует их, генерирует умные саммари с помощью AI и отправляет ежедневные дайджесты в Telegram.

### 🎯 Что делает система

1. **WF01** - Каждые 5 минут сканирует папку с записями
2. **WF01** - Автоматически транскрибирует новые файлы через Whisper
3. **WF03** - В 22:00 генерирует индивидуальные саммари по каждому клиенту
4. **WF03** - Загружает саммари в Dify Knowledge Base для RAG-чата
5. **WF02** - В 23:00 отправляет ежедневный дайджест в Telegram
6. **WF06** - Каждые 15 минут извлекает задачи и дедлайны из переписки

---

## ✨ Ключевые возможности

- 🎤 **Транскрибация** - Faster-Whisper с поддержкой русского языка
- 🤖 **AI Summaries** - GLM-4 (ZhipuAI) для генерации умных саммари
- 📚 **RAG Chat** - Интеграция с Dify для поиска по базе знаний
- 📱 **Telegram Bot** - Автоматическая отправка дайджестов
- 🔄 **Scheduler** - APScheduler с automatic retry и healthcheck
- 🐘 **PostgreSQL** - Надежное хранение всех данных
- 🐳 **Docker** - Полностью контейнеризированное решение

---

## 🚀 Быстрый старт

### Предварительные требования

- Docker & Docker Compose
- 4 GB RAM минимум
- API ключи:
  - [GLM-4 (ZhipuAI)](https://open.bigmodel.cn/)
  - [Telegram Bot Token](https://t.me/BotFather)

### Установка за 10 минут

```bash
# 1. Клонировать репозиторий
git clone https://github.com/YOUR_USERNAME/mvp-autosummary.git
cd mvp-autosummary

# 2. Создать .env файл (см. пример в .env.example)
cp .env.example .env
nano .env  # Заполнить API ключи

# 3. Запустить систему
docker compose up -d

# 4. Проверить статус
docker compose ps
docker logs -f mvp-auto-summary-orchestrator-1
```

**Подробное руководство:** [DEPLOYMENT.md](DEPLOYMENT.md)

---

## 📊 Архитектура

```
Recordings (/mnt/recordings)
    ↓
[WF01] Scanner (5 min)
    ↓
Whisper Transcription
    ↓
PostgreSQL Database
    ↓
[WF03] Individual Summary (22:00)
    ├→ Markdown Files
    ├→ Dify Knowledge Base
    └→ Database Records
    ↓
[WF02] Daily Digest (23:00)
    ↓
Telegram Group Chat
```

### Компоненты

| Компонент | Порт | Описание |
|-----------|------|----------|
| orchestrator | - | Python scheduler + tasks |
| postgres | 5432 | База данных |
| whisper | 9000 | STT транскрибация |
| embeddings | 8081 | Text embeddings для Dify |
| dify-api | 5001 | Dify API server |
| dify-web | 3000 | Dify UI |
| nginx | 8181 | Web server для summaries |

---

## 🗂 Структура проекта

```
mvp-autosummary/
├── app/
│   ├── core/
│   │   ├── db.py              # Database client
│   │   ├── dify_api.py        # Dify API client
│   │   ├── llm.py             # GLM-4 LLM client
│   │   ├── telegram_api.py    # Telegram bot
│   │   └── logger.py          # Structured logging
│   ├── tasks/
│   │   ├── scan_recordings.py # WF01: Scanner
│   │   ├── individual_summary.py # WF03: Summaries
│   │   ├── daily_digest.py    # WF02: Digest
│   │   ├── deadline_extractor.py # WF06: Tasks
│   │   └── healthcheck.py     # Auto-recovery
│   ├── config.py              # Settings
│   ├── scheduler.py           # APScheduler config
│   └── main.py                # Entry point
├── tests/                     # Test suite
├── summaries/                 # Generated summaries
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
├── schema.sql                 # Database schema
├── .env.example
├── README.md
└── DEPLOYMENT.md
```

---

## ⚙️ Конфигурация

### Обязательные переменные (.env)

```bash
# GLM-4 API
GLM4_API_KEY=your_key_here
GLM4_BASE_URL=https://api.z.ai/api/anthropic
GLM4_MODEL=claude-3-5-haiku-20241022

# Telegram
TELEGRAM_BOT_TOKEN=1234567890:ABCdef...
TELEGRAM_CHAT_ID=-1001234567890

# Dify
DIFY_API_KEY=dataset-xxx
DIFY_BASE_URL=https://your-dify.com

# Database
POSTGRES_PASSWORD=secure_password
```

### Расписание задач

| Job | Trigger | Описание |
|-----|---------|----------|
| scan_recordings | every 5 min | Сканирование файлов |
| check_pending | every 5 min | Проверка транскрибации |
| individual_summary | 22:00 daily | Генерация саммари |
| deadline_extractor | every 15 min | Извлечение задач |
| daily_digest | 23:00 daily | Отправка в Telegram |
| healthcheck | every 30 min | Recovery пропущенных |

---

## 🧪 Тестирование

### Запуск тестов

```bash
# Все тесты
pytest tests/ -v

# Конкретный тест
pytest tests/test_wf03.py -v

# С покрытием
pytest tests/ --cov=app --cov-report=html
```

### Ручное тестирование

```bash
# 1. Тест транскрибации
docker exec mvp-auto-summary-orchestrator-1 python -m app.tasks.scan_recordings

# 2. Тест саммари (WF03)
docker exec mvp-auto-summary-orchestrator-1 python -c "
import sys; sys.path.insert(0, '/app')
from datetime import date
from app.tasks.individual_summary import IndividualSummaryTask
# ... (см. DEPLOYMENT.md)
"

# 3. Тест дайджеста (WF02)
docker exec mvp-auto-summary-orchestrator-1 python -c "
# ... (см. DEPLOYMENT.md)
"
```

---

## 📱 Использование

### Загрузка записи

```bash
# Скопировать файл в папку с записями
scp meeting_2026-03-05.mp4 root@server:/mnt/recordings/LEAD-ID_$(date +%Y-%m-%d-%H-%M-%S).mp4

# Формат имени файла: LEAD-ID_YYYY-MM-DD-HH-MM-SS.extension
# Пример: 1000139_2026-03-05-14-30-00.mp4
```

### Проверка саммари

```bash
# Web интерфейс
http://YOUR_SERVER_IP:8181/summaries/YYYY-MM-DD/

# Dify RAG чат
https://your-dify.com/chat/CHATBOT_ID
```

### Telegram дайджест

Дайджест приходит автоматически каждый день в 23:00 MSK

---

## 🔧 Troubleshooting

### Проблема: Dify возвращает 500

**Решение:** Настроить embeddings сервер

```bash
# Проверить embeddings
curl http://YOUR_SERVER_IP:8081/info

# Настроить Dify .env
OPENAI_API_BASE=http://YOUR_SERVER_IP:8081/v1
OPENAI_API_KEY=local-embeddings

# Перезапустить
cd /root/dify/docker && docker compose restart api worker
```

### Проблема: Пропущенные задачи

**Решение:** Healthcheck автоматически запустит пропущенные задачи в течение 1 часа

```bash
# Проверить логи
docker logs mvp-auto-summary-orchestrator-1 | grep healthcheck
```

### Проблема: Whisper timeout

**Решение:** Уменьшить модель или увеличить таймауты

```bash
# В .env
WHISPER_MODEL=small  # вместо medium
WHISPER_TIMEOUT_MIN=1200
```

**Больше решений:** [DEPLOYMENT.md - Устранение неполадок](DEPLOYMENT.md#устранение-неполадок)

---

## 📈 Мониторинг

### Логи

```bash
# Orchestrator
docker logs -f mvp-auto-summary-orchestrator-1

# Фильтр по событиям
docker logs mvp-auto-summary-orchestrator-1 | grep "telegram_sent"
docker logs mvp-auto-summary-orchestrator-1 | grep "summary_created"
```

### База данных

```bash
# Подключиться к Postgres
docker exec -it mvp-auto-summary-postgres-1 psql -U n8n -d n8n

# Статистика
SELECT 
  COUNT(*) FILTER (WHERE status = 'completed') as completed,
  COUNT(*) FILTER (WHERE status = 'pending') as pending,
  COUNT(*) FILTER (WHERE status = 'error') as errors
FROM processed_files;
```

---

## 🔄 Backup

```bash
# Backup базы данных
docker exec mvp-auto-summary-postgres-1 pg_dump -U n8n n8n > backup_$(date +%Y%m%d).sql

# Backup саммари
tar -czf summaries_$(date +%Y%m%d).tar.gz summaries/

# Восстановление
docker exec -i mvp-auto-summary-postgres-1 psql -U n8n n8n < backup_20260305.sql
```

---

## 🛣 Roadmap

- [ ] Web UI для мониторинга
- [ ] Slack интеграция
- [ ] Multi-language support
- [ ] Sentiment analysis
- [ ] Calendar integration
- [ ] REST API

---

## 🤝 Contributing

1. Fork репозиторий
2. Создать feature branch (`git checkout -b feature/amazing-feature`)
3. Commit изменения (`git commit -m 'Add amazing feature'`)
4. Push в branch (`git push origin feature/amazing-feature`)
5. Открыть Pull Request

---

## 📄 License

MIT License - см. [LICENSE](LICENSE) файл

---

## 🙏 Acknowledgments

- [Faster-Whisper](https://github.com/guillaumekln/faster-whisper) - быстрая транскрибация
- [Dify](https://dify.ai/) - RAG платформа
- [APScheduler](https://apscheduler.readthedocs.io/) - job scheduling
- [Python Telegram Bot](https://python-telegram-bot.org/) - Telegram API

---

## 📞 Support

- 📧 Email: support@example.com
- 💬 Telegram: @mvp_autosummary_bot
- 📖 Документация: [DEPLOYMENT.md](DEPLOYMENT.md)
- 🐛 Issues: [GitHub Issues](https://github.com/YOUR_USERNAME/mvp-autosummary/issues)

---

**Сделано с ❤️ для автоматизации рутины**
