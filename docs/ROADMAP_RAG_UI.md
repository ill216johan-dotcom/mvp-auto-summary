# ROADMAP 3.0: МУЛЬТИАГЕНТНЫЙ RAG И АВТОМАТИЗАЦИЯ БИЗНЕС-ПРОЦЕССОВ

> **Дата:** 2026-02-26  
> **Статус:** MVP v2 задеплоен. Telegram-бот в процессе отладки.  
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

## СЛЕДУЮЩИЕ ШАГИ

### 1. Создать Dify Chatbot (UI)
- Studio → New App → Chatbot
- Название: «ФФ Ассистент Куратора»
- Подключить ВСЕ 7 KB (общий + все LEAD-*)
- Системный промпт из `scripts/setup_dify_chatbot.py`
- Publish → скопировать URL в `.env` → `DIFY_CHATBOT_URL`

### 2. Тест WF03 end-to-end
- Прогнать тестовый файл через WF01
- Убедиться что саммари появляется в per-client KB в Dify
- Задать вопрос в Chatbot — проверить RAG-ответ

### 3. Загрузить оферту в общий датасет
- Dify → Knowledge → «Общая документация ФФ Платформы»
- Добавить PDF/TXT: оферта, WMS-инструкция

### 4. Активировать WF06 (дедлайны)
- После стабилизации основного потока
- GLM-4 извлекает задачи → PostgreSQL `extracted_tasks` → Telegram алерты

---

## ИЗВЕСТНЫЕ ОГРАНИЧЕНИЯ

| Проблема | Причина | Статус |
|----------|---------|--------|
| Dify без embedding | Модель векторизации не настроена | Работает на keyword-search |
| WF03 не пишет .md файлы | Нет Write Binary File ноды | TODO |
| WF04 дублировался | Старый импорт не был удалён | Исправляется |

---

*Обновлено: 26.02.2026*
