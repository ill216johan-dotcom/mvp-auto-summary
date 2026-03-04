# Быстрый старт MVP Auto-Summary

> Пошаговая инструкция запуска системы.
> Обновлено: 2026-03-04 — Python orchestrator (без n8n).

> ⚠️ **Перед тем как начать** — прочитай `docs/ERRORS.md`.

---

## Что нужно перед стартом

### От тебя:
- [ ] VPS с Ubuntu 22.04 (2 vCPU, **8 GB RAM**, 40 GB диск)
- [ ] API-ключ Claude (через z.ai) — [получить здесь](https://z.ai)
- [ ] Telegram-бот (создать через @BotFather) + chat_id группы

### От руководителя:
- [ ] IP NFS-сервера и путь к папке с записями
- [ ] Настроенный Jitsi + Jibri (записи падают на NFS)

---

## Шаг 1: Подготовка VPS (10 минут)

### 1.1 Подключись к серверу

```bash
ssh root@YOUR_VPS_IP
```

### 1.2 Установи Docker

```bash
apt update && apt upgrade -y
curl -fsSL https://get.docker.com | sh
apt install -y docker-compose-plugin
docker --version
```

### 1.3 Установи утилиты

```bash
apt install -y git nfs-common ffmpeg
```

### 1.4 Смонтируй NFS

```bash
mkdir -p /mnt/recordings
mount -t nfs NFS_SERVER_IP:/recordings /mnt/recordings
echo "NFS_SERVER_IP:/recordings /mnt/recordings nfs defaults 0 0" >> /etc/fstab
```

> **Если NFS не готов** — создай папку вручную:
> ```bash
> mkdir -p /mnt/recordings/2026/03/04
> ```

---

## Шаг 2: Скопируй проект (2 минуты)

```bash
cd /root
git clone https://github.com/YOUR_ORG/mvp-auto-summary.git
cd mvp-auto-summary
```

---

## Шаг 3: Настрой .env (5 минут)

```bash
cp .env.example .env
nano .env
```

**Обязательно заполни:**

| Переменная | Где взять |
|------------|-----------|
| `POSTGRES_PASSWORD` | Придумай надёжный пароль |
| `GLM4_API_KEY` | [z.ai](https://z.ai) → API Keys |
| `TELEGRAM_BOT_TOKEN` | @BotFather в Telegram |
| `TELEGRAM_CHAT_ID` | См. инструкцию ниже |
| `DIFY_API_KEY` | Dify → Знания → Сервисный API |

### Как получить Telegram chat_id:

1. Создай бота через @BotFather
2. Добавь бота в групповой чат
3. Отправь сообщение в чат
4. Открой: `https://api.telegram.org/bot{ТОКЕН}/getUpdates`
5. Найди `"chat":{"id":-1001234567890}` — это chat_id

---

## Шаг 4: Запусти систему (5-10 минут)

```bash
cd /root/mvp-auto-summary

# Собрать и запустить
docker compose build orchestrator
docker compose up -d orchestrator

# Проверить статус
docker compose ps
```

Должны быть запущены:
```
NAME                    STATUS
mvp-auto-summary-orchestrator-1   Up
mvp-auto-summary-postgres-1       Up (healthy)
mvp-auto-summary-transcribe-1     Up
mvp-auto-summary-summaries-nginx-1 Up
```

### Запустить Whisper (если нужен self-hosted STT):

```bash
docker compose --profile whisper up -d whisper
```

---

## Шаг 5: Проверь работу (5 минут)

### 5.1 Создай тестовый файл

```bash
mkdir -p /mnt/recordings/$(date +%Y/%m/%d)
echo "test" > /mnt/recordings/$(date +%Y/%m/%d)/99999_$(date +%Y-%m-%d)_10-00.wav
```

### 5.2 Проверь логи

```bash
docker compose logs orchestrator -f
```

Должен появиться лог о сканировании файлов.

### 5.3 Проверь базу

```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT filename, status FROM processed_files ORDER BY id DESC LIMIT 5;"
```

### 5.4 Проверь Telegram бота

Отправь `/status` в чат с ботом — должен ответить статусом системы.

---

## Шаг 6: Инициализация базы (один раз)

Если база пустая, выполни:

```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -f /docker-entrypoint-initdb.d/init.sql
```

---

## Как пользоваться

### Ежедневная работа

1. **Проводишь созвон в Jitsi**
   - Комната: `LEAD-12345-conf` (12345 = ID клиента)
   - Запись начнётся автоматически

2. **Система обрабатывает автоматически**
   - Каждые 5 минут сканирует /recordings
   - Транскрибирует через Whisper
   - Сохраняет в базу

3. **В 22:00** — индивидуальные summaries по клиентам

4. **В 23:00** — дайджест в Telegram

### Telegram команды

| Команда | Действие |
|---------|----------|
| `/report` | Промежуточный отчёт |
| `/status` | Статус системы |
| `/rag` | Ссылка на Dify RAG |
| `/help` | Справка |

---

## Подключение Telegram-чатов (для историй переписки)

### Авторизация куратора

```bash
cd /root/mvp-auto-summary/scripts
python3 authorize_curator.py --name masha
```

1. Выбери QR-код
2. Открой Telegram: Настройки → Устройства → Подключить
3. Наведи камеру на QR
4. Файл сессии: `session_masha.session`

### Выгрузка чата

```bash
# Получить список чатов
python3 list_telegram_chats.py --session session_masha

# Выгрузить конкретный чат
python3 export_telegram_chat.py --session session_masha \
    --chat -1009876543210 --lead-id 101

# Загрузить в базу
DB_PASS=$(grep POSTGRES_PASSWORD ../.env | cut -d= -f2)
python3 import_chat_to_db.py --lead-id 101 \
    --file ../exports/chats/LEAD-101_chat.json \
    --db-password $DB_PASS
```

---

## Траблшутинг

### Логи

```bash
docker compose logs orchestrator --tail 50
docker compose logs transcribe --tail 20
```

### Перезапуск

```bash
docker compose restart orchestrator
```

### Сброс зависших транскрипций

```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "DELETE FROM processed_files WHERE status='transcribing' AND created_at < NOW()-INTERVAL '30 minutes';"
```

### Нет сообщений в Telegram

1. Проверь токен: `curl https://api.telegram.org/bot{ТОКЕН}/getMe`
2. Проверь chat_id: отправь сообщение и вызови getUpdates

---

## Откат на n8n (legacy)

Если нужно временно вернуть n8n:

```bash
docker compose --profile legacy up -d n8n
# UI: http://VPS_IP:5678
```

После проверки останови:
```bash
docker compose --profile legacy stop n8n
```

---

## Требования к VPS

| Модель Whisper | RAM | Качество RU |
|----------------|-----|-------------|
| small | +2 GB | Хорошее |
| **medium** | **+3 GB** | **Очень хорошее** |
| large-v3 | +5 GB | Отличное |

**Рекомендация**: 8 GB RAM для medium модели.

### Стоимость

| Компонент | Стоимость/мес |
|-----------|---------------|
| VPS 2 vCPU / 8 GB RAM | ~2,500 руб |
| Claude API | ~300 руб |
| **ИТОГО** | **~2,800 руб/мес** |

---

*Обновлено: 2026-03-04 — Python orchestrator, n8n удалён из основной документации*
