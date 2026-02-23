# ⚠️ ВАЖНО: Как обновлять workflow в n8n

## Проблема (стоила нам недели!)

**n8n НЕ читает workflow из файлов!** Он хранит их в PostgreSQL.

```
❌ НЕПРАВИЛЬНО:
WinSCP → копирую файл в папку → n8n не видит изменений

✅ ПРАВИЛЬНО:
n8n UI → редактирую ноду → Save → работает
```

---

## Способы обновить workflow

### Способ 1: Ручное редактирование (РЕКОМЕНДУЕТСЯ)

1. Открой n8n: `http://84.252.100.93:5678`
2. Открой нужный workflow
3. Кликни на ноду → редактируй параметры
4. **Save** (Ctrl+S)
5. Протестируй (Execute)

### Способ 2: Import через UI

1. Открой workflow
2. **⋮** (три точки) → **Import from File**
3. Выбери `.json` файл
4. **ВАЖНО:** Проверь что все ноды на месте!
5. **Save**

### Способ 3: Удалить и создать заново

1. Удали старый workflow полностью
2. **Add workflow** → **Import from File**
3. Настрой Credentials (PostgreSQL)
4. **Save** → **Activate**

---

## Workflow 01: Правильные параметры нод

### Save Transcript to Notebook (HTTP Request)

| Параметр | Значение |
|----------|----------|
| **Method** | POST |
| **URL** | `http://open-notebook:5055/api/sources/json` |
| **Authentication** | Header Auth |
| **Header** | `Authorization: Bearer password` |
| **Body** | Expression (см. ниже) |

**Body Expression:**
```javascript
{{ JSON.stringify({ 
  notebooks: [$json.notebookId], 
  type: "text", 
  content: $('Extract Transcript').first().json.transcript, 
  title: $('Extract Transcript').first().json.sourceTitle, 
  embed: true, 
  async_processing: false 
}) }}
```

### Get Notebooks (HTTP Request)

| Параметр | Значение |
|----------|----------|
| **Method** | GET |
| **URL** | `http://open-notebook:5055/api/notebooks` |
| **Header** | `Authorization: Bearer password` |

### Create Notebook (HTTP Request)

| Параметр | Значение |
|----------|----------|
| **Method** | POST |
| **URL** | `http://open-notebook:5055/api/notebooks` |
| **Header** | `Authorization: Bearer password` |
| **Body** | Expression |

**Body Expression:**
```javascript
{{ JSON.stringify({ 
  name: $('Extract Transcript').first().json.notebookName, 
  description: 'Client meetings for ' + $('Extract Transcript').first().json.notebookName 
}) }}
```

### Save Success? (IF)

| Параметр | Значение |
|----------|----------|
| **Condition** | Expression |
| **Left** | `{{ ($json.id \|\| $json.source_id \|\| '').length }}` |
| **Operator** | Greater than |
| **Right** | `0` |

---

## Open-Notebook API Endpoints

**Base URL:** `http://open-notebook:5055` (внутри Docker network)

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/notebooks` | GET | Список ноутбуков |
| `/api/notebooks` | POST | Создать ноутбук |
| `/api/sources/json` | POST | Создать source (текст) |
| `/api/sources` | POST | Создать source (multipart) |

---

## Диагностика проблем

### 404 Not Found

**Причина:** Неправильный URL endpoint'а

**Проверка:**
```bash
docker exec mvp-auto-summary-open-notebook-1 curl -s http://localhost:5055/api/notebooks
```

### JSON parameter needs to be valid JSON

**Причина:** Неправильный формат body

**Решение:** Используй Expression с `JSON.stringify({...})`

### Wrong type: ... is an object but was expecting a string

**Причина:** IF нода ожидает строку, получает объект

**Решение:** Используй `.length` для проверки на пустоту

---

## Полезные команды

### Проверить логи open-notebook:
```bash
docker logs mvp-auto-summary-open-notebook-1 --tail=50
```

### Проверить статус в БД:
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT id, filename, status FROM processed_files ORDER BY id DESC LIMIT 5;"
```

### Проверить API напрямую:
```bash
docker exec mvp-auto-summary-open-notebook-1 curl -s http://localhost:5055/api/notebooks
```

---

*Создано: 2026-02-21 — после недели боли и страданий*
