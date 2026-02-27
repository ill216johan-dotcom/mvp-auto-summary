# RAG TROUBLESHOOTING: Полная история проблемы

> **Дата:** 2026-02-27
> **Статус:** RAG не работает. Требуется переиндексация или альтернативное решение.
> **Цель:** Зафиксировать все шаги диагностики для будущего решения.

---

## 1. ЧТО МЫ ХОТЕЛИ

### Бизнес-задача
Куратор заходит в чатбот и задаёт вопросы по истории клиента:
- *"Что обсуждали с ФФ-4405 про переупаковку?"*
- *"Какие были договорённости с LEAD-987?"*
- *"Есть ли открытые вопросы по клиенту 1381?"*

Чатбот отвечает на основе реальных данных из Telegram-переписок и расшифровок звонков.

### Техническая реализация
```
Telegram-чаты → PostgreSQL → Dify Knowledge Base → RAG → Claude ответ
                                      ↓
                               Weaviate (векторы)
```

---

## 2. СИМПТОМ ПРОБЛЕМЫ

### Что наблюдаем
```json
{
    "answer": "В базе знаний нет информации по этому вопросу.",
    "retriever_resources": []  // ← ПУСТО! Поиск ничего не находит
}
```

### Когда проявилось
- Дата: 2026-02-27
- При тестировании чатбота перед демо
- Любой запрос по клиентам возвращает "нет информации"

---

## 3. ДИАГНОСТИКА: ПОШАГОВО

### Шаг 1: Проверка данных в PostgreSQL

**Проверили сегменты (кусочки текста):**
```sql
SELECT d.name, COUNT(ds.id), ds.status 
FROM datasets d 
LEFT JOIN document_segments ds ON d.id = ds.dataset_id 
WHERE d.tenant_id='94b64e4e-13cb-4b7f-accc-99620ebe9c88' 
GROUP BY d.name, ds.status;
```

**Результат:**
```
LEAD-4405 ФФ-4405    | 65 | completed  ✅ Есть данные
LEAD-987 ФФ-987      | 80 | completed  ✅ Есть данные
LEAD-1381 ФФ-1381    | 85 | completed  ✅ Есть данные
LEAD-2048 ФФ-2048    | 2  | completed  ✅ Есть данные
LEAD-4550 ФФ-4550    | 13 | completed  ✅ Есть данные
LEAD-506 ФФ-506      | 6  | completed  ✅ Есть данные
```

**Вывод:** В PostgreSQL всё хорошо — 251 сегмент загружен.

---

### Шаг 2: Проверка Weaviate (векторная БД)

**Команда диагностики:**
```bash
docker exec docker-weaviate-1 wget -qO- \
  --header='Authorization: Bearer WVF5YThaHlkYwhGUSmCRgsX3tD5ngdN8pkih' \
  'http://localhost:8080/v1/schema'
```

**Результат:**
```json
{"classes": []}
```

**Вывод:** Weaviate ПУСТОЙ! Нет ни одного класса (индекса).

---

### Шаг 3: Анализ причины

**Почему Weaviate пустой?**

Dify использует Weaviate для ВСЕХ типов поиска:
- `semantic_search` — векторный поиск (нужны эмбеддинги)
- `keyword_search` — поиск по ключевым словам (ТОЖЕ нужен индекс в Weaviate!)

Даже в режиме `economy` (keyword-only) Dify пишет данные в Weaviate. Но при создании датасетов embedding-провайдер не был настроен → векторы не создались → Weaviate остался пустым.

---

## 4. ПОПЫТКИ РЕШЕНИЯ

### Попытка 1: Удалить default embedding model

```sql
DELETE FROM tenant_default_models 
WHERE tenant_id='...' AND model_type='embeddings';
```

**Результат:** RAG всё равно пытается вызвать embedding API.

---

### Попытка 2: Настроить ZhipuAI embedding

**Проблема:** ZAI coding plan ключи НЕ поддерживают embedding модели:
```bash
curl -X POST 'https://api.z.ai/api/paas/v4/embeddings' \
  -H 'Authorization: Bearer ZAI_KEY' \
  -d '{"model": "embedding-2", "input": "test"}'

# Ответ: {"error":{"code":"1211","message":"Unknown Model"}}
```

**Вывод:** ZAI coding plan = только чат (claude-3-5-haiku), БЕЗ embedding.

---

### Попытка 3: Поднять локальный embedding-сервер

**Что сделали:**
```bash
# Запустили HuggingFace TEI (Text Embeddings Inference)
docker run -d --name embeddings -p 8081:80 \
  ghcr.io/huggingface/text-embeddings-inference:cpu-latest \
  --model-id sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2

# Подключили к сети Dify
docker network connect docker_default embeddings

# Проверили что работает
curl -X POST 'http://localhost:8081/embed' \
  -H 'Content-Type: application/json' \
  -d '{"inputs": "тест"}'
# Ответ: 384-мерный вектор ✅
```

**Настроили в Dify:**
```sql
INSERT INTO provider_credentials (tenant_id, provider_name, encrypted_config)
VALUES ('...', 'langgenius/openai/openai', 
        '{"openai_api_key":"dummy", "base_url":"http://embeddings:80/v1"}');

UPDATE tenant_default_models 
SET provider_name='langgenius/openai/openai', model_name='text-embedding-3-small'
WHERE model_type='embeddings';

UPDATE datasets SET indexing_technique='high_quality', 
       embedding_model='text-embedding-3-small',
       embedding_model_provider='langgenius/openai/openai'
WHERE id='9e65a348-...';
```

**Результат:** Конфигурация обновилась, но переиндексация не запускается автоматически.

---

### Попытка 4: Принудительный запуск переиндексации

**Пробовали:**
```bash
# Обновить статус документа для повторной индексации
UPDATE documents SET indexing_status='parsing', error=NULL;

# API endpoint для переиндексации — НЕТ (404)
POST /v1/datasets/{id}/reindex
POST /v1/datasets/{id}/documents/{doc_id}/index
```

**Результат:** Dify не предоставляет API для принудительной переиндексации. Нужен UI или внутренний celery task.

---

## 5. ТЕКУЩЕЕ СОСТОЯНИЕ

### Что работает ✅
| Компонент | Статус |
|-----------|--------|
| Dify chatbot | ✅ Отвечает (LLM работает) |
| Claude через ZAI | ✅ claude-3-5-haiku работает |
| PostgreSQL segments | ✅ 251 сегмент загружен |
| Embeddings server | ✅ Работает на порту 8081 |
| HTML-дашборд | ✅ 6 карточек клиентов |
| Telegram-бот | ✅ /status, /report, /help |

### Что НЕ работает ❌
| Компонент | Статус | Причина |
|-----------|--------|---------|
| RAG retrieval | ❌ Пусто | Weaviate не содержит векторов |
| Document re-index | ❌ Не запускается | Нет API, нужен UI |

---

## 6. КОРНЕВАЯ ПРИЧИНА

```
Документы загружены через API
         ↓
Сегменты созданы в PostgreSQL (status=completed)
         ↓
НО: embedding-провайдер не был настроен
         ↓
Векторы НЕ созданы в Weaviate
         ↓
RAG поиск возвращает пусто (нечего искать)
```

**Важно:** Dify не умеет "на лету" переиндексировать документы при смене embedding-провайдера. Требуется ручное действие через UI или пересоздание документов.

---

## 7. ВОЗМОЖНЫЕ РЕШЕНИЯ

### Вариант A: Переиндексация через Dify UI

**Шаги:**
1. Зайти в Dify UI: `http://84.252.100.93`
2. Knowledge Base → Выбрать датасет LEAD-4405
3. Settings → Retrieval Settings
4. Убедиться что embedding provider настроен (OpenAI → http://embeddings:80/v1)
5. Нажать "Re-index" или пересоздать документы

**Риски:**
- Может не быть кнопки "Re-index" в UI
- Может потребовать валидный OpenAI API key (даже если base_url кастомный)

---

### Вариант B: Пересоздать документы через API

**Шаги:**
1. Удалить старые документы: `DELETE /v1/datasets/{id}/documents/{doc_id}`
2. Загрузить заново с новым embedding provider
3. Дождаться индексации (автоматически создаст векторы)

**Скрипт:** Написать Python-скрипт для пересоздания всех 12 документов.

---

### Вариант C: Прямая запись в Weaviate

**Идея:** Написать скрипт который:
1. Читает сегменты из PostgreSQL
2. Генерирует векторы через локальный embeddings сервер
3. Пишет напрямую в Weaviate

**Риски:**
- Сложно, нужно знать схему Dify в Weaviate
- Может сломать целостность данных

---

### Вариант D: Альтернативный RAG (PostgreSQL full-text search)

**Идея:** Обойти Dify RAG, сделать поиск напрямую по PostgreSQL:

```sql
-- Полнотекстовый поиск по сегментам
SELECT content, ts_rank(to_tsvector('russian', content), query) as rank
FROM document_segments, 
     to_tsquery('russian', 'переупаковка') query
WHERE to_tsvector('russian', content) @@ query
ORDER BY rank DESC
LIMIT 5;
```

**Реализация:** n8n workflow:
1. Telegram бот получает вопрос
2. Code нода делает SQL поиск
3. Результаты отправляются в Claude для суммаризации
4. Ответ возвращается в Telegram

**Плюсы:** Быстро, не зависит от Dify/Weaviate
**Минусы:** Менее точный поиск (без семантики)

---

### Вариант E: Отложить RAG на после демо

**Для демо показать:**
1. HTML-дашборд с саммари клиентов (работает)
2. Telegram-бот с командами /status, /report (работает)
3. Dify chatbot — демо-режим с заглушкой "RAG в разработке"

**Объяснение для руководства:**
> "Сейчас система показывает саммари по клиентам. Интерактивный RAG-чатбот находится в разработке — требуется донастройка поискового движка. Следующий этап развития."

---

## 8. РЕКОМЕНДАЦИЯ

**Для демо (27-28.02.2026):** Вариант E — отложить RAG.

**После демо:** Вариант B — пересоздать документы с правильным embedding provider.

**Причина:** Переиндексация через UI ненадёжна, а прямой поиск по PostgreSQL — временное решение. Правильный путь — пересоздать документы.

---

## 9. ТЕХНИЧЕСКИЕ ДЕТАЛИ

### Конфигурация Dify (текущая)

```sql
-- Default embedding model
SELECT * FROM tenant_default_models WHERE model_type='embeddings';
-- provider_name: langgenius/openai/openai
-- model_name: text-embedding-3-small

-- Provider credentials
SELECT provider_name, encrypted_config FROM provider_credentials 
WHERE tenant_id='94b64e4e-13cb-4b7f-accc-99620ebe9c88';
-- langgenius/openai/openai: {"openai_api_key":"dummy", "base_url":"http://embeddings:80/v1"}
-- langgenius/anthropic/anthropic: {"anthropic_api_key":"...", "anthropic_api_url":"https://api.z.ai/api/anthropic"}

-- Dataset config
SELECT name, indexing_technique, embedding_model FROM datasets 
WHERE tenant_id='94b64e4e-13cb-4b7f-accc-99620ebe9c88';
-- LEAD-* datasets: high_quality, text-embedding-3-small
```

### Embeddings сервер

```bash
# Контейнер
docker ps | grep embeddings
# embeddings: ghcr.io/huggingface/text-embeddings-inference:cpu-latest

# Endpoint
curl http://embeddings:80/info
# model_id: sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2
# max_input_length: 128
# dimension: 384

# Тест
curl -X POST 'http://embeddings:80/v1/embeddings' \
  -H 'Content-Type: application/json' \
  -d '{"input": "тест", "model": "dummy"}'
# Возвращает 384-мерный вектор ✅
```

### Weaviate (пустой)

```bash
curl http://localhost:8080/v1/schema
# {"classes": []}  ← НЕТ ИНДЕКСОВ
```

---

## 10. ССЫЛКИ

- Dify документация: https://docs.dify.ai/
- Weaviate схема: `docker-weaviate-1:/weaviate.conf`
- Embeddings server: `http://84.252.100.93:8081`
- Dify UI: `http://84.252.100.93` (rod@zevich.ru / Admin123456)

---

*Документ создан: 2026-02-27*
*Автор: Sonnet (Claude) в рамках сессии с Claude Code*
