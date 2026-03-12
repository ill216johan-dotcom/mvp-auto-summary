# 📚 План реализации Базы Знаний и улучшения качества саммари

> **Статус:** ПЛАН (не реализовано)  
> **Дата:** 2026-03-07  
> **Приоритет:** HIGH

---

## 1. Постановка задачи

### Проблема
Текущие саммари генерируются LLM без контекста о бизнесе:
- ЛЛМ не знает, что такое фулфилмент, какие процессы есть, какая терминология
- Не знает нашу оферту — упоминает "лишнее" и не замечает нюансов
- Не знает специфику конкретного клиента — нет истории отношений

### Решение
**База Знаний "0"** — фундаментальный контекст, который подмешивается ко всем запросам на саммари и RAG-чат.

---

## 2. Архитектура (концепция "0 + N")

```
Dify Knowledge Bases:
┌─────────────────────────────────┐
│  KB-0: "База знаний компании"   │  ← ГЛОБАЛЬНАЯ (для всех)
│  - Оферта                       │
│  - Услуги и тарифы (прайс-лист) │
│  - Терминология фулфилмента     │
│  - Бизнес-процессы              │
│  - FAQ                          │
└─────────────────────────────────┘
           ↓ всегда в контексте
┌──────────────┐  ┌──────────────┐  ┌──────────────┐
│  KB-506      │  │  KB-987      │  │  KB-1000139  │  ← ПЕР-КЛИЕНТ
│  Саммари     │  │  Саммари     │  │  Саммари     │
│  звонков     │  │  звонков     │  │  звонков     │
│  и чатов     │  │  и чатов     │  │  и чатов     │
└──────────────┘  └──────────────┘  └──────────────┘
```

**При запросе в RAG для клиента 506:**
1. Ищем в KB-506 (релевантные саммари клиента)
2. Добавляем контекст из KB-0 (фундаментальные знания)
3. Объединяем → передаём в LLM

**При генерации саммари:**
1. Получаем транскрипт звонка
2. Запрашиваем из KB-0 релевантные фрагменты (прайс, оферта)
3. Добавляем в system prompt как "контекст о компании"
4. LLM генерирует осведомлённое саммари

---

## 3. Анализ реализуемости

### 3.1. Dify: мультидатасет поиск — ✅ ПОДДЕРЖИВАЕТСЯ

Dify API `/v1/datasets/{id}/retrieve` работает на **один датасет за запрос**.

**Решение:** делать два параллельных запроса и объединять результаты в коде:

```python
# Псевдокод
results_client = dify.retrieve(query, dataset_id=client_dataset_id, top_k=5)
results_global = dify.retrieve(query, dataset_id=KB0_DATASET_ID, top_k=3)
context = merge_results(results_global, results_client)
```

Это работает через существующий `DifyClient.retrieve()` без изменения API.

### 3.2. Саммари с контекстом KB-0 — ✅ РЕАЛИЗУЕМО

При генерации саммари (WF03) добавляем шаг:

```python
# Перед вызовом LLM
kb0_context = dify.retrieve(
    query=transcript[:500],  # первые 500 символов для поиска
    dataset_id=KB0_DATASET_ID,
    top_k=3
)
enriched_prompt = f"{base_prompt}\n\n=== КОНТЕКСТ О КОМПАНИИ ===\n{format_kb0(kb0_context)}"
summary = llm.generate(enriched_prompt, transcript)
```

### 3.3. Отключение источников для конкретных клиентов — ✅ РЕАЛИЗУЕМО

Добавляем в `lead_chat_mapping` конфигурацию источников KB-0:

```sql
ALTER TABLE lead_chat_mapping ADD COLUMN kb0_sources TEXT[] DEFAULT ARRAY['all'];
-- Варианты: 'all', 'offer', 'pricelist', 'processes', 'faq', 'none'
```

Либо **проще**: используем **Dify tags** для фильтрации по типу документа:
- Документы в KB-0 тегируются: `type:offer`, `type:pricelist`, `type:processes`
- При запросе фильтруем по тегам в зависимости от настроек клиента

**Проверка Dify API для тегов:**
```bash
# При создании документа в KB-0:
POST /v1/datasets/{kb0_id}/document/create-by-text
{ "name": "Оферта", "text": "...", "metadata": [{"key": "type", "value": "offer"}] }

# Retrieve с фильтром (нужно проверить поддержку)
# Если Dify не поддерживает фильтр по metadata — используем отдельные датасеты
```

**Альтернативный подход (надёжнее):** KB-0 разбить на несколько датасетов:
- `KB-0-offer` — оферта
- `KB-0-pricelist` — прайс-лист  
- `KB-0-processes` — бизнес-процессы
- `KB-0-general` — общее (всегда подключено)

Тогда для каждого клиента в `lead_chat_mapping` хранится список dataset_id, которые нужно включить.

---

## 4. Пошаговый план реализации

### Этап 1: Создание KB-0 в Dify (1-2 часа)

**1.1. Создать датасет "База знаний компании" в Dify**
```bash
curl -X POST 'https://dify-ff.duckdns.org/v1/datasets' \
  -H 'Authorization: Bearer dataset-zyLYATai9CmALb3SzNYkRkjk' \
  -H 'Content-Type: application/json' \
  -d '{
    "name": "KB-0: База знаний компании",
    "description": "Фундаментальный контекст: оферта, прайс, процессы. Используется для всех клиентов.",
    "indexing_technique": "high_quality"
  }'
```

**1.2. Загрузить документы в KB-0** (вручную через Dify UI или API)

Документы для первичного наполнения:
- [ ] Оферта (договор-оферта на услуги фулфилмента)
- [ ] Прайс-лист на услуги
- [ ] Описание бизнес-процессов (приёмка, хранение, сборка, отправка)
- [ ] Часто задаваемые вопросы клиентов (FAQ)
- [ ] Глоссарий терминов фулфилмента
- [ ] Контакты и регламенты

**1.3. Прописать dataset_id в .env**
```bash
# В /root/mvp-auto-summary/.env добавить:
KB0_DATASET_ID=<uuid-полученный-при-создании>
# Или разбивка по типам:
KB0_OFFER_DATASET_ID=<uuid>
KB0_PRICELIST_DATASET_ID=<uuid>
KB0_PROCESSES_DATASET_ID=<uuid>
```

---

### Этап 2: Схема БД для управления источниками (30 мин)

**2.1. Миграция БД**
```sql
-- Добавляем KB-0 источники для каждого клиента
-- Список dataset_id из KB-0, которые подключены для этого клиента
ALTER TABLE lead_chat_mapping 
  ADD COLUMN kb0_dataset_ids TEXT[] DEFAULT NULL;
  -- NULL = использовать все KB-0 датасеты (default)
  -- ARRAY[] = отключить KB-0 полностью
  -- ARRAY['uuid1','uuid2'] = подключить конкретные
  
-- Пример настройки:
UPDATE lead_chat_mapping SET kb0_dataset_ids = ARRAY[
  'uuid-kb0-offer',
  'uuid-kb0-processes'
] WHERE lead_id = '987';  -- для клиента 987 прайс не нужен
```

**2.2. Обновить `get_dataset_map()` в `app/core/db.py`**
```python
def get_dataset_config(self, lead_id: str) -> dict:
    """Get dataset config for a lead including KB-0 sources."""
    with self.cursor() as cur:
        cur.execute("""
            SELECT dify_dataset_id, kb0_dataset_ids
            FROM lead_chat_mapping
            WHERE lead_id = %s AND active = true
        """, (lead_id,))
        row = cur.fetchone()
        if not row:
            return {}
        return {
            "client_dataset_id": row["dify_dataset_id"],
            "kb0_dataset_ids": row["kb0_dataset_ids"],  # None = all KB-0
        }
```

---

### Этап 3: Обогащение генерации саммари (2-3 часа)

**3.1. Добавить KB-0 контекст в WF03 (`app/tasks/individual_summary.py`)**

```python
def _get_kb0_context(self, transcript: str, kb0_dataset_ids: list[str]) -> str:
    """Retrieve relevant KB-0 context for summary generation."""
    if not kb0_dataset_ids:
        return ""
    
    # Используем первые 500 символов транскрипта как query
    query = transcript[:500]
    
    context_parts = []
    for dataset_id in kb0_dataset_ids:
        results = self.dify.retrieve(query=query, dataset_id=dataset_id, top_k=2)
        for r in results:
            if r["score"] > 0.3:  # минимальный порог релевантности
                context_parts.append(r["content"])
    
    if not context_parts:
        return ""
    
    return "=== КОНТЕКСТ О КОМПАНИИ ===\n" + "\n\n---\n\n".join(context_parts)


def _summarize_lead_calls(self, lead_id, calls, prompt, dataset_config, target_date):
    # ... существующий код ...
    
    # НОВОЕ: обогащаем промпт контекстом из KB-0
    kb0_ids = dataset_config.get("kb0_dataset_ids") or self._get_all_kb0_ids()
    kb0_context = self._get_kb0_context(combined[:500], kb0_ids)
    
    enriched_prompt = prompt
    if kb0_context:
        enriched_prompt = f"{prompt}\n\n{kb0_context}"
    
    summary = self.llm.generate(enriched_prompt, combined)
    # ... остальной код ...
```

**3.2. Обновить `DifyClient.retrieve()` для одного датасета**

Текущий `retrieve()` принимает `dataset_ids: list[str]` — но Dify API на самом деле принимает один датасет в `/v1/datasets/{id}/retrieve`. Нужно исправить:

```python
def retrieve_from_dataset(self, query: str, dataset_id: str, top_k: int = 3) -> list[dict]:
    """Retrieve from a single dataset."""
    url = f"{self.base_url}/v1/datasets/{dataset_id}/retrieve"
    # ... запрос ...

def retrieve_multi(self, query: str, dataset_ids: list[str], top_k: int = 3) -> list[dict]:
    """Retrieve from multiple datasets and merge results."""
    all_results = []
    for dataset_id in dataset_ids:
        results = self.retrieve_from_dataset(query, dataset_id, top_k)
        all_results.extend(results)
    # Сортируем по score
    all_results.sort(key=lambda x: x["score"], reverse=True)
    return all_results[:top_k * 2]  # возвращаем top_k*2 из объединённых
```

---

### Этап 4: RAG-чат с KB-0 контекстом (1-2 часа)

**Текущая схема RAG:** пользователь открывает Dify Chatbot → Dify сам делает retrieval из назначенного датасета.

**Проблема:** Dify Chatbot App привязан к **конкретным датасетам** при настройке. Нельзя "подмешать" KB-0 динамически через Chatbot URL.

**Два варианта решения:**

#### Вариант A: Настроить Dify App с несколькими датасетами (ПРОЩЕ)

В Dify UI при создании Chatbot App:
- Settings → Knowledge → добавить несколько датасетов: KB-клиента + KB-0-offer + KB-0-processes
- Создать отдельный Chatbot App для каждого клиента с нужным набором датасетов

**Плюсы:** Просто, работает через UI, без кода  
**Минусы:** Нужно вручную создавать App для каждого клиента, нет гибкости

#### Вариант B: Telegram-бот как прокси RAG (ГИБЧЕ)

Добавить команду в Telegram бот `/ask LEAD_ID вопрос`:
1. Бот принимает вопрос
2. Делает retrieval из KB-клиента + KB-0 (с учётом настроек клиента)
3. Передаёт объединённый контекст + вопрос в LLM
4. Отправляет ответ в Telegram

```python
async def _cmd_ask(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
    """RAG query for specific client: /ask 506 вопрос о хранении"""
    args = ctx.args
    if len(args) < 2:
        await update.message.reply_text("Использование: /ask LEAD_ID вопрос")
        return
    
    lead_id = args[0]
    query = " ".join(args[1:])
    
    # Получаем конфиг датасетов
    config = self.db.get_dataset_config(lead_id)
    
    # Retrieval из KB клиента
    client_results = self.dify.retrieve_from_dataset(query, config["client_dataset_id"], top_k=5)
    
    # Retrieval из KB-0
    kb0_ids = config.get("kb0_dataset_ids") or self._default_kb0_ids
    kb0_results = self.dify.retrieve_multi(query, kb0_ids, top_k=3)
    
    # Объединяем контекст
    context = self._format_rag_context(client_results, kb0_results)
    
    # Генерируем ответ
    rag_prompt = f"Ты аналитик фулфилмент-компании. Отвечай на вопросы о клиенте LEAD-{lead_id}."
    answer = self.llm.generate(rag_prompt, f"Вопрос: {query}\n\nКонтекст:\n{context}")
    
    await update.message.reply_text(answer)
```

**Рекомендация:** Начать с **Варианта A** (быстро), затем при необходимости реализовать **Вариант B**.

---

### Этап 5: Наполнение KB-0 (постоянно)

**Минимальный стартовый набор документов:**

| Документ | Приоритет | Кто готовит |
|----------|-----------|-------------|
| Договор-оферта (текст) | 🔴 Критично | Юр. отдел / руководство |
| Прайс-лист на услуги | 🔴 Критично | Менеджмент |
| Что такое фулфилмент (краткое описание) | 🔴 Критично | Команда |
| Этапы работы: приёмка → хранение → сборка → отправка | 🟡 Важно | Операционный отдел |
| FAQ: частые вопросы клиентов | 🟡 Важно | Кураторы |
| Глоссарий терминов | 🟢 Желательно | Команда |
| Регламент работы с клиентами | 🟢 Желательно | Руководство |

---

## 5. Технический стек изменений

### Файлы, которые нужно изменить:

```
mvp-auto-summary/
├── .env                              # Добавить KB0_DATASET_ID(s)
├── app/
│   ├── config.py                     # Добавить KB0_DATASET_ID в Settings
│   ├── core/
│   │   ├── db.py                     # Добавить get_dataset_config()
│   │   └── dify_api.py               # Исправить retrieve() → retrieve_from_dataset() + retrieve_multi()
│   ├── tasks/
│   │   └── individual_summary.py     # Добавить KB-0 обогащение промпта
│   └── bot/
│       └── handler.py                # Добавить /ask команду (опционально)
│
└── scripts/
    └── init-db.sql                   # Добавить kb0_dataset_ids в lead_chat_mapping
```

### Новые записи в БД:

```sql
-- Миграция
ALTER TABLE lead_chat_mapping ADD COLUMN kb0_dataset_ids TEXT[] DEFAULT NULL;

-- Примеры настройки (после создания KB-0 датасетов):
-- Клиент 987 — все KB-0 источники:
UPDATE lead_chat_mapping SET kb0_dataset_ids = NULL WHERE lead_id = '987';

-- Клиент 506 — без прайса:
UPDATE lead_chat_mapping SET kb0_dataset_ids = ARRAY[
  'uuid-kb0-offer', 
  'uuid-kb0-processes',
  'uuid-kb0-faq'
] WHERE lead_id = '506';

-- Клиент 4405 — вообще без KB-0:
UPDATE lead_chat_mapping SET kb0_dataset_ids = ARRAY[]::TEXT[] WHERE lead_id = '4405';
```

---

## 6. Последовательность реализации (рекомендуемая)

```
Неделя 1: Минимальная польза (без кода)
  1. Наполнить документами (оферта, прайс, описание)
  2. Создать KB-0 датасет в Dify UI
  3. Настроить Dify Chatbot Apps с KB-0 + KB-клиента (Вариант A)
  4. Протестировать качество RAG-ответов вручную

Неделя 2: Интеграция с генерацией саммари
  5. Добавить KB0_DATASET_ID в .env и config.py
  6. Исправить DifyClient.retrieve() → отдельные методы
  7. Обновить individual_summary.py — KB-0 в промпте
  8. Добавить kb0_dataset_ids в lead_chat_mapping
  9. Протестировать качество саммари

Неделя 3: Гибкий RAG (опционально)
  10. Реализовать /ask команду в Telegram боте (Вариант B)
  11. Настроить per-клиент фильтрацию KB-0 источников
  12. Мониторинг и fine-tuning промптов
```

---

## 7. Риски и ограничения

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Dify retrieve() медленный (N датасетов = N запросов) | Высокая | Среднее | Параллельные запросы (asyncio), кеш на 1ч |
| Плохое качество KB-0 документов | Средняя | Высокое | Итеративное наполнение, тестирование |
| Dify не поддерживает фильтр по metadata | Средняя | Низкое | Разбить KB-0 на отдельные датасеты |
| KB-0 контекст "засоряет" конкретные саммари | Средняя | Среднее | Настроить top_k=2-3, порог score > 0.4 |
| Увеличение стоимости API (больше токенов) | Высокая | Низкое | ~+20-30% токенов, допустимо при текущих ценах |

---

## 8. Метрики успеха

- [ ] Саммари упоминают конкретные услуги из прайса, если они обсуждались
- [ ] Саммари не содержат "ненужных" объяснений что такое фулфилмент
- [ ] RAG-чат правильно отвечает на вопросы об оферте / условиях
- [ ] Отключение прайса для конкретного клиента работает корректно
- [ ] Время генерации саммари не увеличилось более чем на 30 сек

---

*Создан: 2026-03-07 | Статус: ожидает согласования и начала реализации*
