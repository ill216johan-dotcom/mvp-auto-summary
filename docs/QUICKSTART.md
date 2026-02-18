# Быстрый старт MVP Auto-Summary

> Пошаговая инструкция запуска системы. Рассчитана на человека БЕЗ технического опыта.

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

## Шаг 2: Скачай проект (2 минуты)

```bash
cd /opt
git clone https://github.com/YOUR_ORG/mvp-auto-summary.git
cd mvp-auto-summary
```

> Если репозитория нет на GitHub — просто скопируй папку на сервер через scp:
> ```bash
> scp -r ./mvp-auto-summary root@YOUR_VPS_IP:/opt/
> ```

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

## Шаг 4: Запусти систему (5 минут)

```bash
# Поднять все сервисы
docker compose up -d

# Подождать 1-2 минуты пока всё запустится
sleep 60

# Проверить что всё работает
docker compose ps
```

Ты должен увидеть 5 сервисов в статусе "Up":
```
NAME                          STATUS
mvp-auto-summary-n8n-1        Up
mvp-auto-summary-postgres-1   Up
mvp-auto-summary-surrealdb-1  Up
mvp-auto-summary-open-notebook-1  Up
mvp-auto-summary-whisper-1    Up
```

> **Первый запуск Whisper займёт 3-5 минут** — он скачивает модель (~1.5 GB для medium).

### Проверь доступность:

| Сервис | URL | Что должно быть |
|--------|-----|-----------------|
| n8n | `http://VPS_IP:5678` | Страница входа |
| open-notebook | `http://VPS_IP:8888` | Интерфейс блокнотов |
| Whisper | `http://VPS_IP:9000/docs` | Swagger API документация |

---

## Шаг 5: Настрой n8n (10 минут)

### 5.1 Войди в n8n

1. Открой `http://VPS_IP:5678`
2. Логин: значение `N8N_USER` из .env (по умолчанию `admin`)
3. Пароль: значение `N8N_PASSWORD` из .env

### 5.2 Импортируй Workflows

1. В n8n перейди: **Menu** → **Import from file**
2. Загрузи `n8n-workflows/01-new-recording.json`
3. Повтори для `n8n-workflows/02-daily-digest.json`

### 5.3 Настрой PostgreSQL Credentials

В каждом workflow есть ноды PostgreSQL. Нужно создать credentials:

1. Кликни на любой PostgreSQL node
2. Нажми **Create new credential**
3. Заполни:
   - **Host**: `postgres`
   - **Port**: `5432`
   - **Database**: `n8n` (или значение из .env)
   - **User**: `n8n` (или значение из .env)
   - **Password**: значение `POSTGRES_PASSWORD` из .env
4. Нажми **Save**
5. Выбери эти credentials во ВСЕХ PostgreSQL нодах обоих workflows

### 5.4 Активируй Workflows

1. Открой каждый workflow
2. В правом верхнем углу нажми тогл **Active** → включи
3. Workflow начнёт работать по расписанию

---

## Шаг 6: Протестируй (5 минут)

### 6.1 Создай тестовый файл записи

```bash
# На VPS:
cd /opt/mvp-auto-summary
chmod +x scripts/simulate-recording.sh
bash scripts/simulate-recording.sh 99999
```

Это создаст тестовый файл `/mnt/recordings/2026/02/18/99999_2026-02-18_XX-XX.mp3`.

### 6.2 Подожди 5 минут

Workflow 01 сканирует папку каждые 5 минут. Или запусти вручную:
1. В n8n открой Workflow 01
2. Нажми **Execute Workflow** (кнопка ▶)

### 6.3 Проверь результат

1. В n8n → **Executions** — должно быть успешное выполнение
2. В open-notebook (`http://VPS_IP:8888`) — должен появиться блокнот `LEAD-99999`
3. В PostgreSQL (через n8n SQL node): `SELECT * FROM processed_files`

### 6.4 Протестируй дайджест

1. В n8n открой Workflow 02
2. Нажми **Execute Workflow** вручную
3. Проверь Telegram-чат — должен прийти дайджест

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

*Документ создан: 2026-02-18 | Для вопросов: см. docs/ERRORS.md*
