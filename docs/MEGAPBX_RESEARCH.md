# MegaPBX Call Recordings Access Research

> **Date:** 2026-03-13
> **Status:** 🔍 IN PROGRESS
> **Priority:** CRITICAL - блокирует транскрибацию звонков

---

## Problem Statement

**Симптомы:**
- ❌ Невозможно скачать записи звонков для транскрибации
- ❌ Все попытки заканчиваются `Connection timeout` к `vats528994.megapbx.ru`
- ❌ 30 звонков enriched с `record_url`, но `transcript_status = 'failed'`

**Пользовательский impact:**
- Нет транскрипций разговоров в саммари
- Суммари содержат только метаданные (duration, время)
- **Требуется:** полный текст разговора для AI анализа

---

## Current State

### Что известно:

**1. URL записей:**
```
https://vats528994.megapbx.ru/api/v2/call-records/record/2025-01-23/9f7f1e92-98c9-4fbd-9758-b29095ce58a0/evgeniy_rodzevich_out_79099358635_2025_01_23-15_45_04.mp3
```

**2. Сервер:**
- Hostname: `vats528994.megapbx.ru`
- IP: `193.201.230.178`
- Ping: 100% packet loss (недоступен)
- HTTPS: timeout (60s)

**3. Количество записей:**
```sql
SELECT transcript_status, COUNT(*)
FROM bitrix_calls
GROUP BY transcript_status;

-- no_record: 174,303 (нет URL)
-- pending:   30 (есть URL, не скачаны)
-- failed:    10 (timeout при скачивании)
-- completed: 0  (нет транскрипций!)
```

**4. Источник URL:**
- Bitrix24 → VoxImplant.statistic.get → `CALL_RECORD_URL`
- enriched через `_enrich_call_record_urls()` в `bitrix_sync.py`

---

## Research Tasks (на завтра)

### Задача 1: Проверить доступ к MegaPBX из офиса

**Вопросы:**
- [ ] Пингуется ли `vats528994.megapbx.ru` из офисной сети?
- [ ] Открывается ли URL в браузере с офисного IP?
- [ ] Нужен ли VPN для доступа к vats* доменам?

**Действия:**
```bash
# Из офиса
ping vats528994.megapbx.ru
curl -I "https://vats528994.megapbx.ru/api/v2/call-records/record/..."

# Если недоступен - проверить с VPN Мегафона
```

---

### Задача 2: Найти документацию MegaPBX API

**Что искать:**
- [ ] Официальная документация API MegaPBX
- [ ] Требуется ли API key/token?
- [ ] Как получить доступ к записям через API?
- [ ] Есть ли альтернативный метод скачивания (SFTP, webhook)?

**Источники:**
1. Поиск: "MegaPBX API documentation"
2. Поиск: "Мегафон виртуальная АТС API"
3. Портал поддержки Мегафона
4. Личный кабинет MegaPBX

---

### Задача 3: Проверить авторизацию в Bitrix24

**Гипотеза:** Возможно Bitrix24 уже имеет токен доступа к MegaPBX

**Действия:**
```python
# Проверить headers при запросе через Bitrix API
# Возможно есть authentication token в SETTINGS
```

**Что проверить:**
- [ ] Есть ли в `crm.activity.list` дополнительные поля с токеном?
- [ ] Есть ли в `voximplant.statistic.get` секретный параметр?
- [ ] Нужен ли API key в запросах к record_url?

---

### Задача 4: Найти альтернативные источники транскрипций

**Варианты:**

1. **VoxImplant API напрямую**
   - Проверить есть ли метод `voximplant.call.getRecord`?
   - Возможно можно скачать через VoxImplant API вместо прямого HTTP

2. **Bitrix24 встроенные транскрипции**
   - Проверить новые поля в API (может есть transcription в activity?)
   - Проверить webhooks - может приходят транскрипции в реальном времени?

3. **Telegram бот (временный костыль)**
   - Переслать record_url в Telegram
   - Скачать файл локально с офисного компьютера
   - Загрузить на сервер через scp

---

## План действий

### Option A: Доступ есть (наиболее вероятно)

**Если megaprbx доступен из офисной сети:**

1. **Добавить VPN туннель:**
   ```bash
   # На сервере поднять VPN до офисной сети
   # Или пробросить порт через ssh -R
   ```

2. **Настроить proxy:**
   ```python
   # В transcribe_pending_calls
   proxies = {
       'http': 'http://office-proxy:port',
       'https': 'http://office-proxy:port'
   }
   requests.get(record_url, proxies=proxies, timeout=120)
   ```

3. **Тестировать транскрибацию:**
   ```python
   stats = transcribe_pending_calls(db, transcribe_url, limit=1)
   ```

---

### Option B: Нужен API токен

**Если требуется авторизация:**

1. **Получить токен:**
   - Зарегистрироваться в MegaPBX
   - Создать API key в личном кабинете
   - Добавить в `.env`: `MEGAPBX_API_KEY=xxx`

2. **Обновить код скачивания:**
   ```python
   headers = {'Authorization': f'Bearer {MEGAPBX_API_KEY}'}
   requests.get(record_url, headers=headers, timeout=120)
   ```

---

### Option C: Альтернативный источник

**Если прямого доступа нет:**

1. **VoxImplant API:**
   - Изучить документацию: https://voximplant.com/docs/references/httpapi/
   - Найти метод для скачивания записей

2. **Bitrix24 CDN:**
   - Проверить можно ли скачать через `crm.activity.download`?

3. **Ручной импорт (временный):**
   - Скачать 10-20 записей вручную
   - Загрузить через scp
   - Протестировать саммари

---

## Technical Details

### URL структура записей:

```
https://vats528994.megapbx.ru/api/v2/call-records/record/
  {YYYY-MM-DD}/                           # Дата звонка
  {uuid}/                                  # Уникальный ID записи
  {direction}_{phone}_{timestamp}.mp3     # Имя файла
```

**Пример:**
```
https://vats528994.megapbx.ru/api/v2/call-records/record/2025-01-23/9f7f1e92-98c9-4fbd-9758-b29095ce58a0/evgeniy_rodzevich_out_79099358635_2025_01_23-15_45_04.mp3
```

### Формат:

- **Codec:** MP3
- **Duration:** varies (10s - 5min)
- **Size:** ~100KB - 2MB

### Текущий код скачивания:

**File:** `app/tasks/bitrix_summary.py:transcribe_pending_calls()`

```python
# Download recording
dl_resp = requests.get(record_url, timeout=60, stream=True)
if dl_resp.status_code in (403, 404):
    log.warning("transcribe_unavailable", call_id=call["id"], status=dl_resp.status_code)
    db.update_call_transcript(call["id"], "", "failed")
    stats["failed"] += 1
    continue
```

**Проблема:** timeout (60s) → Connection timeout

---

## Expected Results

После решения:

1. **Транскрибация работает:**
   - `transcribe_pending_calls()` успешно скачивает записи
   - Whisper генерирует `transcript_text`

2. **Суммари с разговорами:**
   ```
   ## Звонки (2025-01-23)
   - 10:00 - 5 мин 23 сек
   - **Содержание:** "Алло, здравствуйте. Да, это Алексей.
     Хотел уточнить по договору ФФ-4405..."
   ```

3. **RAG поиск работает:**
   - Пользователь: "Что обсуждали 23 января?"
   - RAG находит по транскрипции

---

## Контактная информация

**Мегафон:**
- Сайт: https://megapbx.ru/
- Поддержка: +7 800 333 00 00
- Личный кабинет: https://lab.megafon.ru/

**Bitrix24:**
- Документация: https://dev.1c-bitrix.ru/rest_help/
- VoxImplant: https://voximplant.com/

---

**Последнее обновление:** 2026-03-13 01:15 MSK
**Статус:** Жду research от пользователя
