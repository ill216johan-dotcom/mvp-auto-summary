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
- Импортировать обновлённый: `n8n-workflows/03-individual-summaries.json`

### 2. ❓ Создать Dify Chatbot (UI)
- DSL-файл готов: `dify-chatbot-app.json` (в корне проекта)
- **Инструкция:** `docs/GUIDE.md` — раздел «🤖 Dify Chatbot»
- После создания: записать URL в `.env` → `DIFY_CHATBOT_URL`

### 3. ❓ Тест WF03 end-to-end
- Инструкция: `docs/GUIDE.md` — раздел «🧪 WF03 End-to-End тест»

### 4. ❓ Загрузить оферту в общий датасет
- Dify → Knowledge → «Общая документация ФФ Платформы» → Add document → PDF/TXT

### 5. ⏸️ STT — восстановить транскрипцию
- Yandex SpeechKit отключён (2026-03-01, оптимизация расходов)
- См. E100 в `docs/ERRORS.md` и раздел 17 в `docs/SPECS.md` — варианты замены
- Рекомендация: Whisper self-hosted (`docs/GUIDE.md` — «🔌 Восстановить STT»)

### 6. ❓ Активировать WF06 (дедлайны)
- После стабилизации основного потока
- Инструкция: `docs/GUIDE.md` — раздел «📦 WF06 Дедлайны»

---

## ИЗВЕСТНЫЕ ОГРАНИЧЕНИЯ

| Проблема | Причина | Статус |
|----------|---------|--------|
| Dify без embedding | Модель векторизации не настроена | Работает на keyword-search |
| WF03 .md файлы | Не было Write File ноды | ✅ ИСПРАВЛЕНО (2026-03-01) |
| WF04 дублировался | Старый импорт не был удалён | Исправляется |
| Yandex SpeechKit | Временно отключён | ⏸️ См. E100 в ERRORS.md |
| Dify Chatbot | Ещё не создан | ❓ См. GUIDE.md |

---

*Обновлено: 2026-03-01 — добавлен WF03 Write .md, DSL чатбота, зафиксировано отключение SpeechKit.*
