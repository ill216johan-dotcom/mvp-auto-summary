# 🎯 Финальная настройка системы — Инструкции

## ✅ Что уже сделано (автоматически)

1. **PostgreSQL** — все таблицы пусты и готовы к работе
2. **Dify** — переустановлен с нуля, аккаунт `admin@ff-platform.local` создан
3. **n8n workflows** — активны и готовы обрабатывать файлы
4. **Whisper STT** — работает
5. **Telegram бот** — готов отправлять дайджесты

---

## ⚠️ Проблема с Dify аутентификацией

**Критический баг:** Dify выдаёт ошибку "Invalid encrypted data" при попытке логина через API, даже на свежей установке. Это известная проблема с SECRET_KEY в конфигурации Dify.

**Решение:** Создать аккаунт заново через браузер.

---

## 🔧 Что нужно сделать ВРУЧНУЮ (10 минут)

### Шаг 1: Создать администратора Dify

1. Открой в браузере: `https://dify-ff.duckdns.org/install`
2. Если перенаправляет на `/signin` — очисти кэш браузера (Ctrl+Shift+Del) и попробуй снова
3. Заполни форму:
   - Email: `rod@zevich.ru`
   - Name: `Admin`
   - Password: `FFPlatform2026!` (запиши в надёжное место!)
4. Нажми "Create Account"

---

### Шаг 2: Войти в Dify

1. `https://dify-ff.duckdns.org`
2. Логин: `rod@zevich.ru`
3. Пароль: `FFPlatform2026!`

---

### Шаг 3: Создать датасеты клиентов

1. В Dify UI → **Knowledge** → **Create Knowledge**
2. Создай 6 датасетов:

| Название | Описание |
|----------|----------|
| `LEAD-4405 ФФ-4405` | Созвоны, чаты, саммари клиента ФФ-4405 |
| `LEAD-987 ФФ-987` | Созвоны, чаты, саммари клиента ФФ-987 |
| `LEAD-1381 ФФ-1381` | Созвоны, чаты, саммари клиента ФФ-1381 |
| `LEAD-2048 ФФ-2048` | Созвоны, чаты, саммари клиента ФФ-2048 |
| `LEAD-4550 ФФ-4550` | Созвоны, чаты, саммари клиента ФФ-4550 |
| `LEAD-506 ФФ-506` | Созвоны, чаты, саммари клиента ФФ-506 |

3. Для каждого датасета:
   - Тип: **Knowledge Base**
   - Retrieval method: **Hybrid Search** (если доступно) или **Keyword Search**

---

### Шаг 4: Получить Dataset API key

1. В Dify UI → **Knowledge** → любой датасет → **API Access**
2. Скопируй **Dataset API Key** (начинается с `dataset-...`)
3. Сохрани его в `.env` файл на сервере:

```bash
ssh root@84.252.100.93
nano /root/mvp-auto-summary/.env

# Найди строку DIFY_API_KEY и замени на новый ключ:
DIFY_API_KEY=dataset-ТВОЙ_НОВЫЙ_КЛЮЧ

# Сохрани: Ctrl+O, Enter, Ctrl+X
```

4. Перезапусти n8n чтобы подхватил новый ключ:
```bash
cd /root/mvp-auto-summary
docker compose restart n8n
```

---

### Шаг 5: Обновить маппинг датасетов в PostgreSQL

После создания датасетов нужно записать их ID в базу данных:

```bash
ssh root@84.252.100.93
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n
```

Выполни SQL (подставь реальные Dataset ID из Dify UI):

```sql
UPDATE lead_chat_mapping SET dify_dataset_id='DATASET_ID_ИЗ_DIFY_UI' WHERE lead_id='4405';
UPDATE lead_chat_mapping SET dify_dataset_id='DATASET_ID_ИЗ_DIFY_UI' WHERE lead_id='987';
UPDATE lead_chat_mapping SET dify_dataset_id='DATASET_ID_ИЗ_DIFY_UI' WHERE lead_id='1381';
UPDATE lead_chat_mapping SET dify_dataset_id='DATASET_ID_ИЗ_DIFY_UI' WHERE lead_id='2048';
UPDATE lead_chat_mapping SET dify_dataset_id='DATASET_ID_ИЗ_DIFY_UI' WHERE lead_id='4550';
UPDATE lead_chat_mapping SET dify_dataset_id='DATASET_ID_ИЗ_DIFY_UI' WHERE lead_id='506';

-- Проверь результат:
SELECT lead_id, lead_name, dify_dataset_id FROM lead_chat_mapping;

\q
```

---

### Шаг 6: Создать Chatbot в Dify

1. В Dify UI → **Studio** → **Create from blank** → **Chatbot**
2. Название: `ФФ Ассистент Куратора`
3. В разделе **Knowledge** → **Add Knowledge** → выбери ВСЕ 6 датасетов клиентов
4. Настройки:
   - Model: `Claude 3.5 Haiku` (или любой доступный)
   - Temperature: `0.7`
   - Instructions (системный промпт):

```
Ты — ассистент куратора ФФ Платформы. Отвечаешь на вопросы по истории взаимодействия с клиентами: созвоны, чаты, договорённости.

Если спрашивают про клиента (например "ФФ-4405 что обсуждали?"), ищи информацию в базе знаний.

Формат ответа:
- Краткое резюме
- Ключевые договорённости
- Нерешённые вопросы (если есть)

Отвечай по-русски, чётко и по делу.
```

5. **Publish** → скопируй **Chat URL** (будет вида `https://dify-ff.duckdns.org/chat/XXXXXXXX`)

6. Сохрани URL в `.env`:
```bash
nano /root/mvp-auto-summary/.env

# Обнови строку:
DIFY_CHATBOT_URL=https://dify-ff.duckdns.org/chat/ТВОЙ_ID_ЧАТА
```

---

## 🧪 E2E Тест системы

### Подготовка тестового файла

1. Найди любой короткий аудиофайл (1-2 минуты, формат webm/mp3/wav)
2. Переименуй в формат: `4405_2026-03-02_15-00.mp3` (LEAD_ID обязателен!)
3. Загрузи через WinSCP на сервер:
   - Подключись к `84.252.100.93` (логин `root`, пароль из документации)
   - Путь на сервере: `/mnt/recordings/`
   - Положи файл туда

---

### Автоматический флоу (проверяется по шагам)

**Через 5 минут после загрузки файла:**

#### 1️⃣ WF01 — Транскрипция
```bash
ssh root@84.252.100.93
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT id, filename, status FROM processed_files ORDER BY id DESC LIMIT 1;"
```

**Ожидаемо:** статус `completed`, есть `transcript_text`

---

#### 2️⃣ WF03 — Саммари + Dify KB (запускается в 22:00)

Или запусти вручную:
1. Открой n8n: `http://84.252.100.93:5678`
2. Логин: `rod@zevich.ru` / `Ill216johan511lol2`
3. Открой **WF03 — Individual Summaries**
4. Нажми **Execute Workflow**

Проверь результат:
```bash
# Саммари сохранён в БД?
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "SELECT lead_id, source_type, LEFT(summary_text,100) FROM client_summaries ORDER BY id DESC LIMIT 1;"

# Файл .md создан?
ls -lh /var/lib/docker/volumes/mvp-auto-summary_summaries_data/_data/$(date +%Y-%m-%d)/
```

**Ожидаемо:** 
- Запись в `client_summaries`
- Файл `LEAD-4405_call_2026-03-02.md` в summaries
- Документ добавлен в Dify KB (проверь в Dify UI → Knowledge → LEAD-4405)

---

#### 3️⃣ Dify Chatbot — RAG запрос

1. Открой chatbot: скопированный URL из Шага 6 (`https://dify-ff.duckdns.org/chat/...`)
2. Задай вопрос: **"ФФ-4405 что обсуждали?"**

**Ожидаемо:** Chatbot отвечает на основе загруженного саммари (цитирует источник из KB)

---

#### 4️⃣ WF02 — Telegram дайджест (запускается в 23:00)

Или запусти вручную:
1. n8n UI → **WF02 — Daily Digest** → **Execute Workflow**

Проверь Telegram группу **"Отчёты ФФ Платформы"** — должно прийти сообщение с дайджестом за день.

---

## 📊 Итоговый чеклист

- [ ] Dify аккаунт создан и логин работает
- [ ] 6 датасетов клиентов созданы
- [ ] Dataset API key обновлён в `.env`
- [ ] Маппинг `dify_dataset_id` обновлён в PostgreSQL
- [ ] Chatbot создан и опубликован
- [ ] Тестовый файл загружен в `/mnt/recordings/`
- [ ] WF01 обработал файл (статус `completed` в БД)
- [ ] WF03 создал саммари + документ в Dify KB
- [ ] Chatbot отвечает на вопросы по клиенту
- [ ] WF02 отправил дайджест в Telegram

---

## 🆘 Если что-то не работает

### Dify не даёт войти через браузер

**Попробуй:**
1. Другой браузер (Chrome → Firefox)
2. Режим инкогнито
3. Очисти все cookies для `dify-ff.duckdns.org`
4. Попробуй с мобильного телефона

Если всё равно не работает — это баг Dify с SECRET_KEY. Нужна консультация с разработчиками Dify или полная переустановка с исправлением конфигурации.

### WF01 не обрабатывает файлы

```bash
# Проверь что WF01 активен
docker exec mvp-auto-summary-n8n-1 n8n list:workflow --active
```

### Chatbot не находит информацию

Проверь что документ действительно добавлен в KB:
1. Dify UI → Knowledge → LEAD-4405 ФФ-4405 → Documents
2. Должен быть документ с текстом саммари

---

**Создано:** 2026-03-03  
**Версия системы:** MVP Phase 0 — Clean Install
