# Быстрый старт MVP Auto-Summary

> Пошаговая инструкция запуска системы. Рассчитана на человека БЕЗ технического опыта.
> Проверено: 2026-02-18. Все шаги протестированы на реальном сервере.

> ⚠️ **Перед тем как начать** — прочитай `docs/ERRORS.md`. Там описаны все грабли на которые наступили при первом деплое. Это сэкономит тебе 3-4 часа.

---

## Что тебе нужно перед стартом

### От тебя (продакт):
- [ ] VPS с Ubuntu 22.04 (2 vCPU, **8-16 GB RAM**, 40 GB диск) — ~2-3K руб/мес
- [ ] API-ключ GLM-4 (ZhipuAI) — [получить здесь](https://z.ai)
- [ ] Telegram-бот (создать через @BotFather) + chat_id группы кураторов

### От руководителя:
- [ ] IP NFS-сервера и путь к папке с записями
- [ ] Настроенный Jitsi + Jibri (записи падают на NFS)

### Что НЕ нужно:
- ❌ Yandex Cloud аккаунт (используем бесплатный self-hosted Whisper)
- ❌ Yandex SpeechKit API ключ (Whisper заменяет его)
- ❌ S3 bucket (файлы обрабатываются локально)
- ❌ Навыки программирования

---

## Шаг 1: Подготовка VPS (10 минут)

### 1.1 Подключись к серверу

```bash
ssh root@YOUR_VPS_IP
```

### 1.2 Установи Docker

```bash
# Обновить систему
apt update && apt upgrade -y

# Установить Docker
curl -fsSL https://get.docker.com | sh

# Установить Docker Compose
apt install -y docker-compose-plugin

# Проверить
docker --version
docker compose version
```

### 1.3 Установи вспомогательные утилиты

```bash
apt install -y git nfs-common ffmpeg
```

### 1.4 Смонтируй NFS (если руководитель уже настроил)

```bash
# Создать точку монтирования
mkdir -p /mnt/recordings

# Смонтировать (замени IP и путь на реальные)
mount -t nfs NFS_SERVER_IP:/recordings /mnt/recordings

# Автомонтирование при перезагрузке
echo "NFS_SERVER_IP:/recordings /mnt/recordings nfs defaults 0 0" >> /etc/fstab
```

> **Если NFS ещё не готов** — создай пустую папку и кидай туда тестовые файлы вручную:
> ```bash
> mkdir -p /mnt/recordings/2026/02/18
> ```

---

## Шаг 2: Скопируй проект на сервер (2 минуты)

**С Windows (PowerShell или CMD):**
```powershell
scp -r C:\Projects\mvp-auto-summary root@YOUR_VPS_IP:/root/
```

**Или через git (если есть репозиторий):**
```bash
cd /root
git clone https://github.com/YOUR_ORG/mvp-auto-summary.git
```

Все дальнейшие команды выполняются из папки `/root/mvp-auto-summary` на сервере.

---

## Шаг 3: Настрой переменные окружения (5 минут)

```bash
# Скопировать шаблон
cp .env.example .env

# Сгенерировать ключ шифрования
echo "N8N_ENCRYPTION_KEY=$(openssl rand -hex 16)" >> .env

# Сгенерировать пароли
echo "N8N_PASSWORD=$(openssl rand -base64 12)" >> .env
echo "POSTGRES_PASSWORD=$(openssl rand -base64 12)" >> .env
echo "SURREAL_PASSWORD=$(openssl rand -base64 12)" >> .env
```

### 3.1 Открой .env и заполни вручную:

```bash
nano .env
```

Что нужно заполнить **обязательно**:

| Переменная | Где взять | Пример |
|------------|-----------|--------|
| `GLM4_API_KEY` | [z.ai](https://z.ai) → API Keys | `abc123def456...` |
| `TELEGRAM_BOT_TOKEN` | @BotFather в Telegram | `7123456789:AAF...` |
| `TELEGRAM_CHAT_ID` | См. инструкцию ниже | `-1001234567890` |
| `N8N_WEBHOOK_URL` | IP твоего VPS | `http://123.45.67.89:5678` |
| `OPEN_NOTEBOOK_TOKEN` | По умолчанию `password` | `password` |

### Как получить Telegram chat_id:

1. Создай бота через @BotFather → скопируй токен
2. Добавь бота в нужный групповой чат
3. Отправь любое сообщение в чат
4. Открой в браузере:
   ```
   https://api.telegram.org/bot{ТВОЙ_ТОКЕН}/getUpdates
   ```
5. Найди `"chat":{"id":-1001234567890}` — это твой chat_id

### Как получить API-ключ GLM-4:

1. Зарегистрируйся на [z.ai](https://z.ai) (бывший open.bigmodel.cn)
2. Перейди в "API Keys"
3. Создай новый ключ → скопируй

---

## Шаг 4: Запусти систему (5-10 минут)

```bash
cd /root/mvp-auto-summary

# Поднять все сервисы
docker compose up -d

# Подождать пока всё запустится (особенно Whisper — скачивает модель ~1.5 GB)
sleep 120

# Проверить что всё работает
docker compose ps
```

Ты должен увидеть 5 сервисов в статусе "Up":
```
NAME                               STATUS
mvp-auto-summary-n8n-1             Up
mvp-auto-summary-postgres-1        Up (healthy)
mvp-auto-summary-surrealdb-1       Up
mvp-auto-summary-open-notebook-1   Up
mvp-auto-summary-whisper-1         Up
```

> **Первый запуск Whisper займёт 5-10 минут** — скачивает модель (~1.5 GB для medium).

### ⚠️ ВАЖНО: перезапусти open-notebook после старта

Open-notebook иногда стартует раньше чем SurrealDB готов принимать соединения (race condition). После того как все сервисы поднялись — перезапусти его:

```bash
# Подождать что SurrealDB полностью запустился
sleep 30

# Перезапустить open-notebook
docker compose restart open-notebook

# Убедиться что воркер стабилен (не перезапускается)
sleep 15
docker compose logs open-notebook --tail=5
# Должно быть: "success: worker entered RUNNING state" — и больше ничего
```

### Проверь доступность:

| Сервис | URL | Что должно быть |
|--------|-----|-----------------|
| n8n | `http://VPS_IP:5678` | Страница входа или форма регистрации |
| open-notebook | `http://VPS_IP:8888` | Интерфейс блокнотов |
| Whisper | `http://VPS_IP:9000/docs` | Swagger API документация |

> **Если n8n показывает форму регистрации** — это нормально при первом запуске. Введи любой email и пароль из `.env` (`N8N_PASSWORD`). Эти данные станут твоим логином.

---

## Шаг 5: Настрой n8n (15-20 минут)

### 5.1 Войди в n8n

1. Открой `http://VPS_IP:5678` в браузере
2. **При первом открытии** — покажет форму регистрации. Введи:
   - Email: любой (например `admin@mvp.local`)
   - Имя: любое
   - Пароль: тот же что в `.env` (`N8N_PASSWORD`)
3. При следующих входах — используй эти же email и пароль

### 5.2 Создай credentials для PostgreSQL

Это нужно сделать ДО импорта workflows, иначе придётся настраивать каждую ноду вручную.

1. В n8n: левое меню → **Credentials** → кнопка **Add credential**
2. Найди **PostgreSQL** → выбери
3. Заполни:
   - **Host**: `postgres` ← именно так, не IP!
   - **Port**: `5432`
   - **Database**: `n8n`
   - **User**: `n8n`
   - **Password**: значение `POSTGRES_PASSWORD` из `.env`
   - **SSL**: `disable`
4. Нажми **Save** — назови credential `PostgreSQL MVP`

### 5.3 Импортируй Workflows

1. В n8n: левое меню → **Workflows** → кнопка **⋮** (три точки) → **Import from file**
2. Загрузи файл `n8n-workflows/01-new-recording.json`
3. После импорта — открой workflow, убедись что все PostgreSQL-ноды используют credential `PostgreSQL MVP`
4. Повтори для `n8n-workflows/02-daily-digest.json`

> **Если credential не привязался автоматически**: кликни на каждую ноду с базой данных → в поле Credential выбери `PostgreSQL MVP` вручную.

### 5.4 Активируй Workflows

1. Открой **Workflow 01** (01 New Recording...)
2. В правом верхнем углу переключи тогл с **Inactive** на **Active**
3. Повтори для **Workflow 02** (02 Daily Digest...)

После активации workflow 01 начнёт сканировать папку каждые 5 минут автоматически.

---

## Шаг 6: Протестируй (10 минут)

### 6.1 Создай тестовую папку и файл

На сервере (в Putty):
```bash
# Создать папку с сегодняшней датой
mkdir -p /mnt/recordings/$(date +%Y/%m/%d)

# Создать тестовый WAV-файл (замени ДАТУ на сегодняшнюю в формате YYYY-MM-DD)
dd if=/dev/urandom bs=96000 count=1 > /mnt/recordings/$(date +%Y/%m/%d)/99999_$(date +%Y-%m-%d)_10-00.wav

# Убедиться что файл создан
ls -lh /mnt/recordings/$(date +%Y/%m/%d)/
```

> **Примечание**: тестовый файл из `/dev/urandom` — это случайный шум, не речь. Whisper распознает его как "СПОКОЙНАЯ МУЗЫКА" или пустую строку. Это нормально — pipeline всё равно пройдёт полностью. Для реального теста нужна реальная запись разговора.

### 6.2 Запусти Workflow 01 вручную

1. Открой в браузере `http://VPS_IP:5678`
2. Войди в n8n → открой **Workflow 01 New Recording v3 FINAL**
3. Нажми кнопку **Execute Workflow** (в правом нижнем углу)
4. Наблюдай как ноды загораются зелёным слева направо

**Ожидаемый результат**: все ноды зелёные, последняя — **Mark Completed**.

### 6.3 Проверь результат в базе

В Putty:
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT filename, status, summary_sent, created_at FROM processed_files ORDER BY created_at DESC LIMIT 5;"
```

Должно быть `status = completed`.

### 6.4 Проверь open-notebook

1. Открой `http://VPS_IP:8888`
2. Должен появиться блокнот `LEAD-99999`
3. Внутри — транскрипт из Whisper (даже если это "СПОКОЙНАЯ МУЗЫКА")

### 6.5 Протестируй дайджест (Workflow 02)

> **Важно**: Workflow 02 отправляет дайджест только если есть записи со статусом `completed` за сегодня. После шага 6.2 такая запись есть.

1. В n8n открой **Workflow 02 — Daily Digest → GLM-4 → Telegram**
2. Нажми **Execute Workflow**
3. Подожди 20-30 секунд (GLM-4 суммаризирует)
4. Проверь Telegram-чат кураторов — должен прийти дайджест

### 6.6 Что делать если что-то пошло не так

```bash
# Посмотреть логи n8n
docker compose logs n8n --tail=30

# Посмотреть логи open-notebook
docker compose logs open-notebook --tail=20

# Посмотреть состояние базы
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT filename, status FROM processed_files ORDER BY created_at DESC;"

# Сбросить тестовые данные и начать заново
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "DELETE FROM processed_files;"
```

Смотри `docs/ERRORS.md` — там описаны все известные ошибки с решениями.

---

## Как пользоваться системой (для менеджеров)

### Каждый день

1. **Проводишь созвон с клиентом в Jitsi**
   - Открываешь Jitsi (адрес даст руководитель)
   - Создаёшь комнату с названием `LEAD-12345-conf` (вместо 12345 — ID клиента)
   - Проводишь встречу как обычно
   - Всё, запись начнётся автоматически

2. **Ничего больше делать не надо**
   - Через 5-10 минут после созвона система найдёт запись
   - Расшифрует её в текст
   - Сохранит в базу

3. **В 23:00 приходит дайджест в Telegram**
   - Открываешь чат с ботом
   - Читаешь: "Сегодня 3 созвона. Ключевые договорённости:..."

### Когда нужно вспомнить, о чём говорили

**Вариант 1: Telegram-дайджесты**
- Просто листаешь историю чата с ботом
- Дайджесты приходят каждый вечер

**Вариант 2: Через open-notebook**
1. Открываешь браузер: `http://IP-СЕРВЕРА:8888`
2. Видишь список блокнотов — каждый клиент = свой блокнот `LEAD-12345`
3. Кликаешь на нужный → видишь все встречи с этим клиентом
4. Можно спросить: "О чём договорились в прошлый раз?"

### Важные правила

| Правило | Почему важно |
|---------|--------------|
| Называй комнату `LEAD-{ID}-conf` | Без ID система не поймёт, какой это клиент |
| Не переименовывай файлы записей | Система ищет файлы по шаблону |
| Жди 5-10 минут после созвона | Система проверяет папку каждые 5 минут |

---

## Что дальше?

### Ежедневная работа
- Система работает полностью автоматически
- Менеджеры проводят созвоны в Jitsi (комнаты `LEAD-{ID}-conf`)
- Записи автоматически падают на NFS → транскрибируются → сохраняются
- В 23:00 приходит дайджест в Telegram

### Мониторинг
- **n8n Executions** (`http://VPS_IP:5678/executions`) — все запуски workflow
- Ошибки видны как красные execution'ы

### Если что-то сломалось
- Смотри `docs/ERRORS.md` — там типичные ошибки с решениями
- Логи: `docker compose logs n8n` или `docker compose logs whisper`
- Рестарт: `docker compose restart`

---

## Требования к VPS (обновлённые)

С Whisper вместо Yandex SpeechKit нужно больше RAM:

| Модель Whisper | RAM | Скорость (60 мин аудио) | Качество русского |
|----------------|-----|------------------------|-------------------|
| `tiny` | +1 GB | ~5 мин | Плохое |
| `base` | +1 GB | ~10 мин | Среднее |
| `small` | +2 GB | ~20 мин | Хорошее |
| **`medium`** | **+3 GB** | **~40 мин** | **Очень хорошее** |
| `large-v3` | +5 GB | ~90 мин | Отличное |

**Рекомендация**: VPS с **8 GB RAM** для `medium` модели. Если бюджет позволяет — 16 GB для `large-v3`.

### Стоимость (обновлённая)

| Компонент | Стоимость/мес |
|-----------|---------------|
| VPS 2 vCPU / 8 GB RAM | ~2,500 руб |
| GLM-4.7-FlashX API | ~300 руб |
| **ИТОГО** | **~2,800 руб/мес** |

> Экономия **~25,000 руб/мес** по сравнению с Yandex SpeechKit!

---

## Частые проблемы при первом запуске

| Симптом | Причина | Решение |
|---------|---------|---------|
| n8n показывает форму регистрации | Первый запуск | Нормально — введи любые данные |
| open-notebook не открывается сразу | Race condition с SurrealDB | `docker compose restart open-notebook` |
| Workflow 01 ничего не делает | Нет файлов или все уже обработаны | Создай новый файл с другим именем |
| Workflow 01 застрял на ноде — статус `error` | Whisper или open-notebook недоступен | `docker compose ps` — проверь все контейнеры |
| Workflow 02 ничего не отправляет | Нет `status='completed'` записей | Сначала запусти Workflow 01 с тестовым файлом |
| Whisper стартует долго | Скачивает модель (~1.5 GB) | Подожди 5-10 минут при первом запуске |
| `EROFS: read-only file system` | Попытка писать внутрь контейнера n8n | Создавай файлы на хосте, в `/mnt/recordings/` |
| Файлы .webm застревают в `transcribing` | n8n таймаут 30 мин < время транскрипции | Файлы > 100MB пропускаются автоматически. Для зависших: `DELETE FROM processed_files WHERE status='transcribing';` |
| ffmpeg не найден в n8n контейнере | Alpine (musl) несовместим с Ubuntu ffmpeg | Установить статический ffmpeg: см. E057 в ERRORS.md |
| Workflow 01 дублирует файлы | Несколько активных версий workflow | Деактивировать старые — оставить только `ZCtnggR6qrPy7bS6` |

---

## Именование файлов записей

Единственное обязательное правило: **файл должен начинаться с цифр (ID клиента)**.

```
101_2026-02-20_10-30.mp3        ✅ строгий формат
101_разговор_про_доставку.mp3   ✅ любое название — работает
101_zoom.wav                    ✅ работает
101.mp3                         ✅ работает

разговор_с_клиентом.mp3         ❌ нет цифр в начале — пропустит
митинг_101.wav                  ❌ цифры не в начале — пропустит
```

Поддерживаемые форматы: mp3, wav, webm, ogg, m4a, flac.

---

## Подключение Telegram-чатов

### Зачем

Помимо созвонов система собирает историю переписки с клиентами в Telegram и суммаризирует её. Итог — в вечернем дайджесте будет и что говорили на созвоне, и о чём переписывались.

### Ключевой принцип: один аккаунт = один куратор

Каждый куратор видит только своих клиентов. Поэтому каждый куратор авторизуется один раз — и получает собственный файл сессии (`session_masha.session`, `session_petya.session`, и т.д.).

Одно Telegram-приложение (api_id/api_hash) работает для всех аккаунтов — ничего дополнительно регистрировать не нужно.

---

### Первичная настройка (один раз на каждого куратора)

**Шаг 1** — Авторизовать куратора (выполняется на рабочем компьютере, куратор рядом):

Открой командную строку (Win+R → cmd) и запусти:
```
python C:\Users\dev\mvp-autosummary\scripts\authorize_curator.py --name masha
```
Замени `masha` на имя куратора латиницей (например: `petya`, `ivan`, `olga`).

Что произойдёт:
1. Выбери **1 — QR-код** (рекомендуется)
2. Куратор открывает Telegram на телефоне: **Настройки → Устройства → Подключить устройство**
3. Наводит камеру на QR-код в командной строке
4. Если у куратора включена двухфакторная аутентификация — вводишь пароль когда попросит
5. Появится: `✅ Авторизован: Мария Иванова`
6. Создастся файл: `C:\Users\dev\mvp-autosummary\scripts\session_masha.session`

> **Если куратор удалённый** (не в офисе): отправь ему скрипт `authorize_curator.py`, он запускает его сам на своём компьютере и присылает `.session` файл тебе.

**Шаг 2** — Скопировать файл сессии на сервер через WinSCP:
- Откуда: `C:\Users\dev\mvp-autosummary\scripts\session_masha.session`
- Куда: `/root/mvp-auto-summary/scripts/session_masha.session`

Повтори шаги 1-2 для каждого куратора.

**Шаг 3** — Получить список чатов каждого куратора (в PuTTY на сервере):
```bash
cd /root/mvp-auto-summary/scripts

python3 list_telegram_chats.py --session session_masha
# → показывает все чаты Маши, сохраняет в exports/chats/chats_masha.txt

python3 list_telegram_chats.py --session session_petya
# → показывает все чаты Пети, сохраняет в exports/chats/chats_petya.txt
```

Запиши: какой chat_id соответствует какому клиенту (ID договора / лида).

**Шаг 4** — Выгрузить переписку с клиентом:
```bash
# Маша ведёт клиента 101 в чате с ID -1009876543210:
python3 export_telegram_chat.py --session session_masha --chat -1009876543210 --lead-id 101

# Петя ведёт клиента 102 в чате с ID -1001234567890:
python3 export_telegram_chat.py --session session_petya --chat -1001234567890 --lead-id 102
```

**Шаг 5** — Загрузить в базу:
```bash
DB_PASS=$(grep POSTGRES_PASSWORD /root/mvp-auto-summary/.env | cut -d= -f2)

python3 import_chat_to_db.py --lead-id 101 \
    --file ../exports/chats/LEAD-101_chat.json \
    --db-password $DB_PASS

python3 import_chat_to_db.py --lead-id 102 \
    --file ../exports/chats/LEAD-102_chat.json \
    --db-password $DB_PASS
```

**Шаг 6** — Заполнить таблицу маппинга (для справки и автоматизации):
```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "
INSERT INTO lead_chat_mapping (lead_id, lead_name, chat_id, chat_title, chat_type)
VALUES
  ('101', 'ООО Ромашка', -1009876543210, 'Ромашка — поставки', 'supergroup'),
  ('102', 'ИП Иванов',   -1001234567890, 'Иванов ИП чат',      'group');
"
```

---

### Ежедневная работа (после первоначальной настройки)

После настройки всё работает само:
- Workflow 03 в n8n каждый день в 22:00 суммаризирует чаты из `chat_messages`
- Workflow 02 в 23:00 включает summary чатов в общий дайджест

Новые сообщения за день нужно доливать вручную (или настроить крон-задачу):
```bash
# Пример: выгрузить и залить чат клиента 101 (запускать раз в день)
python3 export_telegram_chat.py --session session_masha --chat -1009876543210 --lead-id 101
python3 import_chat_to_db.py --lead-id 101 --file ../exports/chats/LEAD-101_chat.json \
    --db-password $DB_PASS --clear
```

### Проблемы с авторизацией

Все типичные ошибки описаны в `docs/ERRORS.md` разделы E047–E053.

---

*Документ создан: 2026-02-18 | Обновлён: 2026-02-20 — добавлена поддержка нескольких кураторов (authorize_curator.py)*
