# План на завтра (2026-03-14)

> **Цель:** Настроить доступ к записям звонков MegaPBX для транскрибации
> **Блокировка:** E072 - Connection timeout к vats528994.megapbx.ru

---

## 🎯 Главная задача

Получить доступ к `https://vats528994.megapbx.ru/api/v2/call-records/record/` для скачивания mp3 файлов.

---

## 📍 Текущее состояние

**Что работает:**
- ✅ Синхронизация звонков из Bitrix24 (174K записей)
- ✅ Phone number extraction (E071 FIXED)
- ✅ Duration extraction (E070 FIXED)
- ✅ Record URL enrichment (38 URLs получено)

**Что НЕ работает:**
- ❌ Скачивание записей (timeout 60s)
- ❌ Транскрибация через Whisper
- ❌ Генерация саммари с текстом разговора

**Метрики:**
```
transcript_status:
  - no_record: 174,303
  - pending:       30  (ожидает скачивания)
  - failed:        10  (timeout)
  - completed:      0  !! НУЖНО ИСПРАВИТЬ
```

---

## 📋 Checklist на завтра

### Утро (исследование)

- [ ] **Проверить доступ из офисной сети**
  ```bash
  # С офисного компьютера
  ping vats528994.megapbx.ru
  curl -I "https://vats528994.megapbx.ru/api/v2/call-records/record/..."

  # Если доступен — нужен VPN/прокси на сервер
  ```

- [ ] **Найти документацию MegaPBX API**
  - Поиск: "MegaPBX API documentation"
  - Поиск: "Мегафон виртуальная АТС API"
  - Проверить личный кабинет: https://lab.megafon.ru/
  - Найти раздел про call recordings

- [ ] **Проверить нужен ли API токен**
  - Зарегистрироваться в MegaPBX (если нет аккаунта)
  - Создать API key в личном кабинете
  - Проверить формат авторизации (Bearer token, Basic auth?)

- [ ] **Проверить VoxImplant API**
  - Возможно можно скачать через VoxImplant напрямую
  - Документация: https://voximplant.com/docs/references/httpapi/
  - Искать метод типа `getRecording`, `downloadRecord`

### День (настройка)

**Option A: Доступ через VPN/Proxy**

- [ ] Настроить VPN между сервером и офисом
  ```bash
  # Или пробросить порт через ssh
  ssh -R 8080:localhost:8080 user@office-pc
  ```

- [ ] Обновить `transcribe_pending_calls()`:
  ```python
  proxies = {'https': 'http://proxy:port'}
  requests.get(record_url, proxies=proxies, timeout=120)
  ```

**Option B: API токен**

- [ ] Добавить в `.env`:
  ```bash
  MEGAPBX_API_KEY=your_token_here
  ```

- [ ] Обновить код:
  ```python
  headers = {'Authorization': f'Bearer {settings.megapbx_api_key}'}
  requests.get(record_url, headers=headers, timeout=120)
  ```

**Option C: Альтернативный источник**

- [ ] Изучить VoxImplant API метод
- [ ] Проверить Bitrix24 CDN для скачивания
- [ ] (Костыль) Ручной импорт 10-20 файлов

### Вечер (тестирование)

- [ ] Тестовое скачивание 1 записи:
  ```python
  stats = transcribe_pending_calls(db, transcribe_url, limit=1)
  # Ожидается: transcribed=1, failed=0
  ```

- [ ] Проверить `transcript_text` в БД:
  ```sql
  SELECT call_date, LEFT(transcript_text, 200)
  FROM bitrix_calls
  WHERE transcript_status = 'completed'
  LIMIT 1;
  ```

- [ ] Сгенерировать саммари для тестового клиента:
  ```python
  stats = generate_bitrix_summaries(db, llm, dify, target_date=None)
  ```

- [ ] Проверить саммари:
  ```sql
  SELECT summary_text
  FROM bitrix_summaries
  WHERE diffy_lead_id = 'ФФ-4405'
  ORDER BY summary_date DESC
  LIMIT 1;
  ```

**Ожидаемый результат в саммари:**
```markdown
## Звонки (2025-01-23)
- 10:00 - 5 мин 23 сек с +79099358635

**Содержание разговора:**
"Алло, здравствуйте. Да, это Алексей. Хотел уточнить
по договору ФФ-4405. Когда будет следующая поставка..."
```

---

## 🔗 Полезные ссылки

**Документация:**
- `docs/MEGAPBX_RESEARCH.md` — детальный план исследования
- `docs/ERRORS.md` → E072 — описание проблемы
- `docs/BITRIX_SYNC_TECHNICAL.md` — архитектура синхронизации

**Код:**
- `app/tasks/bitrix_summary.py:transcribe_pending_calls()` — скачивание
- `app/tasks/bitrix_sync.py:_enrich_call_record_urls()` — enrichment

**SQL для мониторинга:**
```sql
-- Проверка прогресса транскрибации
SELECT
    transcript_status,
    COUNT(*) as count,
    COUNT(transcript_text) as with_text
FROM bitrix_calls
GROUP BY transcript_status;

-- Найти звонки с transcript_text
SELECT
    DATE(call_date) as date,
    COUNT(*) as calls,
    SUM(CASE WHEN transcript_text IS NOT NULL THEN 1 ELSE 0 END) as transcribed
FROM bitrix_calls
WHERE call_date >= '2025-01-01'
GROUP BY DATE(call_date)
ORDER BY date DESC
LIMIT 10;
```

---

## 📞 Контакты

**Мегафон:**
- Поддержка: +7 800 333 00 00
- Личный кабинет: https://lab.megafon.ru/
- MegaPBX: https://megapbx.ru/

**Битрикс (для справки):**
- Документация: https://dev.1c-bitrix.ru/rest_help/
- VoxImplant: https://voximplant.com/

---

## ✅ Success Criteria

**Done когда:**
1. ✅ Успешно скачано минимум 5 записей
2. ✅ Whisper транскрибировал их в `transcript_text`
3. ✅ Сгенерировано саммари с текстом разговора
4. ✅ Пользователь подтвердил что текст корректный

**Метрики успеха:**
```sql
-- До
completed: 0

-- После (минимум)
completed: 5+
failed: 0
```

---

**Создано:** 2026-03-13 01:20 MSK
**Автор:** Claude + User
**Статус:** Ожидает выполнения
