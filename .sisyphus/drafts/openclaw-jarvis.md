# Draft: OpenClaw "Jarvis" — Полноценный AI-ассистент на VPS

## Сервер
- **Тариф**: VPS Professional NVMe unlimited (RU)
- **Дата открытия**: 2026-02-18
- **Домен**: ill216johan.example.com
- **IP**: 84.252.100.93
- **ОС**: Предположительно Linux (уточнить)
- **Root доступ**: Да

## Что такое OpenClaw
- 271k GitHub stars — самый популярный open-source AI ассистент
- Бывшие имена: Clawdbot → Moltbot → OpenClaw
- Поддержка 22+ мессенджеров (Telegram, WhatsApp, Discord, Slack, Signal, и т.д.)
- 8 встроенных инструментов (файловая система, веб-поиск, выполнение кода, память, и т.д.)
- 17 продвинутых инструментов (браузерная автоматизация, cron, скриншоты, и т.д.)
- 5,400+ community skills на ClawHub
- Требования: Node.js ≥22
- Поддержка Docker

## Требования пользователя (подтверждённые)
- [x] Платформа: Telegram (подтверждено)
- [x] Хочет "полноценного Джарвиса" — максимальная функциональность
- [ ] AI-провайдер: НЕ ОПРЕДЕЛЁН
- [ ] Бюджет на API: НЕ ОПРЕДЕЛЁН
- [ ] Конкретные use cases: НЕ ОПРЕДЕЛЕНЫ
- [ ] Дополнительные мессенджеры: НЕ ОПРЕДЕЛЕНЫ
- [ ] Метод установки (Docker vs native): НЕ ОПРЕДЕЛЁН
- [ ] Какие skills/навыки нужны: НЕ ОПРЕДЕЛЕНЫ

## Исследование — Что может "Джарвис" на OpenClaw

### Встроенные инструменты (бесплатно, всегда активны):
1. **File System** — чтение/запись файлов на сервере
2. **Command Execution** — запуск shell-команд
3. **Web Search** — поиск в интернете
4. **Web Browsing** — парсинг веб-страниц
5. **Memory** — постоянная память между сессиями
6. **Message Send** — отправка сообщений
7. **Image Viewing** — анализ изображений
8. **Code Execution** — запуск Python/JS кода

### Продвинутые инструменты (включаются в конфиге):
- Browser Automation (Puppeteer/Chromium)
- Multi-Session (параллельные агенты)
- Screenshots
- Clipboard
- Scheduled Tasks (cron)
- HTTP Requests
- Database Queries
- Audio Transcription, OCR, PDF, SSH, Docker, Webhooks, и т.д.

### Топ community skills для "Джарвиса":
- **Cognitive Memory (FSRS-6)** — спейсд репетишн для долгосрочной памяти
- **Prompt Optimizer** — улучшение промптов автоматически
- **Google Calendar** — управление календарём через Telegram
- **Gmail** — чтение/отправка email
- **GitHub PR** — управление пул-реквестами
- **Code Review** — ревью кода
- **Deploy Monitor** — мониторинг деплоев
- **Log Analysis** — анализ логов
- **Todoist** — управление задачами
- **Notion** — интеграция с Notion
- **Obsidian** — интеграция с Obsidian

### Продвинутые возможности:
- **Self-Building Skills** — OpenClaw может САМА создавать себе новые навыки!
- **Multi-Agent Routing** — разные агенты для разных задач
- **Cron/Webhooks** — автоматические задачи по расписанию
- **Browser Control** — управление браузером (заполнение форм, парсинг)

## Open Questions
- Какой AI провайдер? (Anthropic/OpenAI/OpenRouter)
- Какие конкретные задачи нужны?
- Бюджет на API?
- Нужны ли другие мессенджеры кроме Telegram?
- ОС сервера?
- Есть ли уже Docker?

## Scope Boundaries
- INCLUDE: Полная установка OpenClaw + Telegram + skills + автоматизации
- EXCLUDE: Пока не определено
