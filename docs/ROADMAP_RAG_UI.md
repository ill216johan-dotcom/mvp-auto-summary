# ROADMAP 3.0: МУЛЬТИАГЕНТНЫЙ RAG И АВТОМАТИЗАЦИЯ БИЗНЕС-ПРОЦЕССОВ

> **Дата:** 2026-02-26  
> **Обновлено:** 2026-03-02  
> **Статус:** E2E тест пройден ✅. Whisper medium STT работает. Dify RAG — частично (embedding не настроен).  
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

## ✅ СДЕЛАНО (1-2 марта — STT + E2E тест)

### 1. ✅ Бесшовная смена STT-провайдеров (2026-03-01)
- `transcribe_server.py` полностью переписан с Strategy Pattern
- 3 адаптера: SpeechKit / Whisper / AssemblyAI
- Переключение через `.env` (`STT_PROVIDER=whisper`)
- Docker Compose: whisper-сервис добавлен (faster-whisper-server, порт 8000)

### 2. ✅ Whisper medium STT работает стабильно (2026-03-01)
- Сервер обновлён: 15GB RAM, 10 CPU cores (Xeon Gold 6240R)
- Whisper medium загружается и работает (ранее OOM на 7.8GB)
- Качество: отличное распознавание русского (2:12 аудио → 1574 символов)
- Не галлюцинирует на тишине (возвращает 0 символов — лучше чем base)
- Скорость: ~5 мин на 2:12 аудио (CPU)

### 3. ✅ User Guide создан (2026-03-01)
- `docs/USER_GUIDE.md` — подробный гайд без «заумностей»

### 4. ✅ Полный E2E тест пройден (2026-03-02)
- Чистый старт: БД, Dify datasets, summary файлы — всё очищено
- Тестовый файл: `4405_тестовый_2026-03-01.webm` (2:12, реальная русская речь)
- **WF01:** Авто-обнаружение файла → Whisper medium → 1574 символов транскрипт → `processed_files` ✅
- **WF03 (симулирован):** Claude (z.ai) → 1521 символов Markdown summary → .md файл → Dify документ загружен ✅
- **WF02 (симулирован):** Claude дайджест → Telegram сообщение (message_id=350) ✅
- ⚠️ **Dify Chatbot:** UI доступен, но RAG не работает (embedding-модель не настроена)

### 5. ✅ Тестовые скрипты созданы (на сервере)
- `scripts/test_wf03.py` — симуляция WF03 с правильным z.ai Anthropic API
- `scripts/test_wf02.py` — симуляция WF02 с Telegram доставкой

---

## ⚠️ ОБНАРУЖЕНО ПРИ E2E ТЕСТЕ

### LLM API — НЕ GLM-4, а Claude через z.ai
- `.env`: `GLM4_BASE_URL=https://api.z.ai/api/anthropic`, `GLM4_MODEL=claude-3-5-haiku-20241022`
- Формат: **Anthropic Messages API** (`/v1/messages`), **НЕ** OpenAI (`/chat/completions`)
- Авторизация: `x-api-key` header + `anthropic-version: 2023-06-01`
- WF03 в n8n имеет хардкод на `https://open.bigmodel.cn/api/paas/v4/chat/completions` (OpenAI формат) — **несоответствие!**

### WHISPER_URL — порт 8000, не 9000
- `faster-whisper-server` слушает порт 8000 внутри контейнера
- Правильно: `WHISPER_URL=http://whisper:8000`
- `docker compose restart` НЕ перезагружает .env — надо `docker compose up -d`

---

## 🔴 СЛЕДУЮЩИЕ ШАГИ (задачи на 2026-03-02)

### 1. 🔴 Dify Embedding Model — настроить в UI
- **Что**: В Dify Admin UI → Settings → Model Provider → добавить OpenAI-compatible embedding
- **Зачем**: Без этого RAG/chatbot не работает (keyword-search недостаточен)
- **Как**: Контейнер `text-embeddings-inference` работает на порту 8081, но Dify не знает о нём
- **Ошибка**: `PluginInvokeError: 'openai_api_key'` при попытке индексации документа
- **Статус**: ❌ Не сделано

### 2. 🔴 WF03 — выровнять API формат с z.ai
- **Что**: В n8n UI обновить HTTP Request ноду в WF03
- **Сейчас**: Хардкод `https://open.bigmodel.cn/api/paas/v4/chat/completions` (OpenAI формат)
- **Нужно**: `https://api.z.ai/api/anthropic/v1/messages` (Anthropic формат)
- **Авторизация**: `x-api-key` вместо `Authorization: Bearer`
- **Статус**: ❌ Не сделано

### 3. 🟡 WF01 — исправить race condition со статусом
- **Что**: Транскрипт записывается в БД, но WF01 помечает файл как `error` (retry timeout)
- **Причина**: 10 попыток × 60 сек — недостаточно для Whisper medium на CPU
- **Fix**: Увеличить количество попыток или timeout
- **Статус**: ❓ Требует анализа

### 4. 🟡 Обработка больших файлов (>30 мин аудио)
- **Что**: Файл `1000023` (30 мин) упал по таймауту при транскрипции
- **Fix**: Увеличить timeout или реализовать chunking
- **Статус**: ❓ Требует решения

### 5. 🟢 Заполнить `curators` в lead_chat_mapping
- Поле пустое, нужно спросить у руководителя
- Влияет на дайджесты по кураторам

---

## АКТИВНЫЕ WORKFLOW (на 2026-03-02)

| ID | Название | Расписание | Статус |
|----|----------|------------|--------|
| `mEgnRihTrXgdS6mG` | 00 — Error Alerts | on error | ✅ |
| `EFQwS2Iy76c9J8Dq` | 01 — New Recording → Whisper | on file | ✅ (Whisper medium) |
| `cBfns8usSm2DYxQg` | 02 — Daily Digest → Telegram | 21:00 | ✅ |
| `FGMFUfL3lGI8B2Yt` | 03 — Individual Summaries → Dify | 22:00 | ⚠️ (API формат не совпадает) |
| `39wv0ASq5MXGnAEn` | 04 — Telegram Bot Commands | webhook | ✅ |
| `nmuKqgUDP6FP0h1s` | 06 — Deadline Extractor | 22:30 | ✅ |

---

## ТЕКУЩЕЕ СОСТОЯНИЕ СИСТЕМЫ (2026-03-02)

### Сервер
- **IP**: 84.252.100.93
- **RAM**: 15 GB (обновлено с 7.8 GB)
- **CPU**: 10 cores (Xeon Gold 6240R)
- **OS**: Ubuntu

### STT
- **Провайдер**: Whisper self-hosted (medium)
- **URL**: `http://whisper:8000`
- **Статус**: ✅ Работает стабильно

### LLM
- **Провайдер**: Claude 3.5 Haiku через z.ai
- **URL**: `https://api.z.ai/api/anthropic/v1/messages`
- **Формат**: Anthropic Messages API
- **Статус**: ✅ Работает (проверено в E2E тесте)

### RAG (Dify)
- **UI**: `http://84.252.100.93` (порт 80)
- **Chatbot**: `http://84.252.100.93/chat/71pymtobibxuwqbc`
- **Статус**: ⚠️ Документы загружаются, но индексация не работает (embedding не настроен)

---

## ИЗВЕСТНЫЕ ОГРАНИЧЕНИЯ

| Проблема | Причина | Статус |
|----------|---------|--------|
| Dify RAG не работает | Embedding-модель не настроена в Dify Settings | 🔴 Критично |
| WF03 API формат | Хардкод OpenAI формат, а LLM = Anthropic (z.ai) | 🔴 Критично |
| WF01 race condition | Retry timeout < время транскрипции Whisper medium | 🟡 Средне |
| Большие файлы >30 мин | Timeout при транскрипции на CPU | 🟡 Средне |
| Кураторы не заполнены | Поле `curators` в lead_chat_mapping пустое | 🟢 Низкий |

---

## РЕЗУЛЬТАТЫ E2E ТЕСТА (2026-03-02)

```
WF01: 4405_тестовый_2026-03-01.webm → Whisper medium → 1574 chars → status=completed ✅
WF03: transcript → Claude (z.ai) → 1521 char summary → .md file + Dify doc ✅
WF02: Claude digest → Telegram message_id=350 ✅
Dify RAG: ⚠️ indexing error (embedding model not configured)
```

---

*Обновлено: 2026-03-02 — E2E тест пройден, сервер обновлён (15GB/10CPU), Whisper medium работает, z.ai/Claude как LLM.*
