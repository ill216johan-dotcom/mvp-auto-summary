# ROADMAP 3.0: МУЛЬТИАГЕНТНЫЙ RAG И АВТОМАТИЗАЦИЯ БИЗНЕС-ПРОЦЕССОВ

> **Дата:** 2026-02-26  
> **Обновлено:** 2026-03-01  
> **Статус:** MVP v2 задеплоен. Telegram-бот работает. STT временно отключён.  
> **Цель:** Per-client RAG (Dify.ai) по звонкам + Telegram-бот + nginx саммари.

---

## СДЕЛАНО (25-26 февраля)

1. **Смена RAG:** open-notebook → Dify.ai (порт 80, контейнер `docker-nginx-1`)
2. **Инфраструктура:** Portainer (9443), summaries-nginx (8181), PostgreSQL v2 миграция
3. **Per-client датасеты в Dify:** 7 KB созданы (1 общий + 6 LEAD-*)
   - Ключевое: датасеты создаются БЕЗ `indexing_technique` (embedding-модель не настроена)
4. **WF03 Individual Summaries:** GLM-4 → per-client Dify KB (по lead_id из БД)
5. **WF02 Daily Digest:** ссылки на .md файлы + Dify чат в Telegram
6. **WF04 Telegram Bot:** /report /status /rag /help — импортирован, активен (id: `iRF8ZueNMO2HaWV1`)
7. **Исправлен баг boolean:equal** в WF01 и WF04 (n8n 2.8.3 не поддерживает `type:boolean`)

---

## ✅ TELEGRAM BOT — ПОЛНОСТЬЮ РАБОТАЕТ (26.02.2026 18:34)

- `/report` — отчёт по созвонам ✅
- `/status` — статус системы + список клиентов ✅
- `/rag` — ссылка на Dify + примеры вопросов ✅
- `/help` — справка по командам ✅

---

## СЛЕДУЮЩИЕ ШАГИ (актуально на 2026-03-01)

### 1. ✅ WF03 Write .md (СДЕЛАНО 2026-03-01)
- Добавлены ноды `Prep Call/Chat MD Write` + `Write Call/Chat MD File` (Execute Command)
- n8n теперь записывает .md файлы в `/summaries/YYYY-MM-DD/LEAD-XXXX_*.md`
- Файл WF03 обновлён, задеплоен, активен (29 нод)

### 2. ✅ WF06 активирован (СДЕЛАНО 2026-03-01)
- Дедлайны + задачи из звонков → PostgreSQL `extracted_tasks` → Telegram алерты (22:30)

### 3. ✅ Тестовые данные очищены (СДЕЛАНО 2026-03-01)
- Удалены тестовые записи: `processed_files`, `chat_messages` (TEST_4405)
- Удалён тестовый .md файл из summaries volume

### 4. ✅ Дубликаты WF04 удалены (СДЕЛАНО 2026-03-01)
- Было 6 копий неактивного WF04 — все удалены
- Осталось: 1 активный WF04 (id: `39wv0ASq5MXGnAEn`)

### 5. ❓ Создать Dify Chatbot (UI)
- DSL-файл готов: `dify-chatbot-app.json` (в корне проекта)
- Chatbot URL уже есть в .env: `DIFY_CHATBOT_URL=http://84.252.100.93/chat/71pymtobibxuwqbc`
- Проверить что все 7 KB подключены к chatbot в Dify Studio
- **Инструкция:** `docs/GUIDE.md` — раздел «🤖 Dify Chatbot»

### 6. ❓ Загрузить оферту в общий датасет
- Dify → Knowledge → «Общая документация ФФ Платформы» → Add document → PDF/TXT
- Датасет сейчас пустой (docs=0)

### 7. ⏸️ STT — восстановить транскрипцию
- Yandex SpeechKit отключён (2026-03-01, оптимизация расходов)
- WF01 активен, но transcribe-контейнер не обрабатывает файлы
- См. E100 в `docs/ERRORS.md` и раздел 17 в `docs/SPECS.md` — варианты замены
- Рекомендация: Whisper self-hosted (`docs/GUIDE.md` — «🔌 Восстановить STT»)

---

## АКТИВНЫЕ WORKFLOW (на 2026-03-01)

| ID | Название | Расписание | Статус |
|----|----------|------------|--------|
| `mEgnRihTrXgdS6mG` | 00 — Error Alerts | on error | ✅ |
| `EFQwS2Iy76c9J8Dq` | 01 — New Recording → SpeechKit | on file | ✅ (STT off) |
| `cBfns8usSm2DYxQg` | 02 — Daily Digest → Telegram | 21:00 | ✅ |
| `FGMFUfL3lGI8B2Yt` | 03 — Individual Summaries → Dify | 22:00 | ✅ |
| `39wv0ASq5MXGnAEn` | 04 — Telegram Bot Commands | webhook | ✅ |
| `nmuKqgUDP6FP0h1s` | 06 — Deadline Extractor | 22:30 | ✅ |

---

## ИЗВЕСТНЫЕ ОГРАНИЧЕНИЯ

| Проблема | Причина | Статус |
|----------|---------|--------|
| Dify без embedding | Модель векторизации не настроена | Работает на keyword-search |
| Yandex SpeechKit | Временно отключён | ⏸️ См. E100 в ERRORS.md |
| Dify Chatbot KB | Не проверено подключение всех 7 KB | ❓ |
| «Общая документация» | Датасет пустой (docs=0) | ❓ Загрузить оферту |

---

*Обновлено: 2026-03-01 — WF03+WF06 активны, дубли WF04 удалены, тестовые данные очищены.*
