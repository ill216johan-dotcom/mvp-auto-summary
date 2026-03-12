# Быстрый старт MVP Auto-Summary

> Пошаговая инструкция запуска системы.
> Обновлено: 2026-03-09 — добавлена Bitrix24 интеграция.

> ⚠️ **Перед тем как начать** — прочитай `docs/ERRORS.md`.

---

## Что нужно перед стартом

### От тебя:
- [ ] VPS с Ubuntu 22.04 (2 vCPU, **8 GB RAM**, 40 GB диск)
- [ ] API-ключ Claude (через z.ai) — [получить здесь](https://z.ai)
- [ ] Telegram-бот (создать через @BotFather) + chat_id группы
- [ ] Dify API ключ (`dataset-zyLYATai9CmALb3SzNYkRkjk` — уже настроен)

### От руководителя:
- [ ] IP NFS-сервера и путь к папке с записями (для Jitsi)
- [ ] Настроенный Jitsi + Jibri (записи падают на NFS)
- [ ] Bitrix24 webhook URL (уже есть: `https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/`)

---

## Шаг 1: Подготовка VPS (10 минут)

### 1.1 Подключись к серверу

```bash
ssh -i C:\Users\User\.ssh\mvp_server -o StrictHostKeyChecking=no root@84.252.100.93
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

### 1.4 Смонтируй NFS (для Jitsi-записей)

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

| Переменная | Где взять | Текущее значение |
|------------|-----------|-----------------|
| `POSTGRES_PASSWORD` | Придумай надёжный пароль | — |
| `GLM4_API_KEY` | [z.ai](https://z.ai) → API Keys | уже настроен |
| `TELEGRAM_BOT_TOKEN` | @BotFather в Telegram | уже настроен |
| `TELEGRAM_CHAT_ID` | См. инструкцию ниже | уже настроен |
| `DIFY_API_KEY` | Dify → Знания → Сервисный API | `dataset-zyLYATai9CmALb3SzNYkRkjk` |
| `BITRIX_WEBHOOK_URL` | Битрикс24 → Настройки → REST API | `https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/` |

**Bitrix-переменные (добавить в .env):**

```env
BITRIX_WEBHOOK_URL=https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/
BITRIX_CONTRACT_FIELD=UF_CRM_1632960743049
BITRIX_SYNC_HOUR=6
```

**И в docker-compose.yml в секцию `environment` сервиса orchestrator:**

```yaml
- BITRIX_WEBHOOK_URL=${BITRIX_WEBHOOK_URL}
- BITRIX_CONTRACT_FIELD=${BITRIX_CONTRACT_FIELD}
- BITRIX_SYNC_HOUR=${BITRIX_SYNC_HOUR}
```

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

## Шаг 5: Применить миграцию БД (один раз)

Миграция создаёт 6 таблиц для Bitrix синхронизации:

```bash
# Скопировать SQL на сервер
scp -i C:\Users\User\.ssh\mvp_server scripts/migrate_db_v3.sql root@84.252.100.93:/root/

# Применить миграцию
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 \
  "docker exec -i mvp-auto-summary-postgres-1 psql -U n8n -d n8n < /root/migrate_db_v3.sql"

# Проверить таблицы
ssh -i C:\Users\User\.ssh\mvp_server root@84.252.100.93 \
  "docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c '\dt bitrix_*'"
```

Должны появиться таблицы:
- `bitrix_leads` — лиды и контакты из Битрикса
- `bitrix_activities` — звонки, письма, комментарии
- `bitrix_sync_state` — статус синхронизации
- `bitrix_summaries` — саммари по клиентам
- `bitrix_dataset_mapping` — соответствие лид → Dify блокнот
- `bitrix_call_recordings` — метаданные записей звонков

---

## Шаг 6: Историческая синхронизация (первый запуск)

> ⚠️ Этот шаг выполняется **только один раз** — при первом запуске.
> Синхронизирует ВСЮ историю из Битрикса (30k+ лидов, все звонки/письма).

```bash
# Скопировать скрипт в контейнер
docker cp /root/mvp-auto-summary/scripts/run_historical_sync.py \
  mvp-auto-summary-orchestrator-1:/app/scripts/

# Запустить в фоне (займёт несколько часов)
nohup docker exec mvp-auto-summary-orchestrator-1 \
  python /app/scripts/run_historical_sync.py \
  >> /root/bitrix_sync.log 2>&1 &

echo "Синхронизация запущена. PID: $!"
```

### Мониторинг прогресса

```bash
# Следить за логом
tail -f /root/bitrix_sync.log

# Проверить, жив ли процесс
ps aux | grep run_historical | grep -v grep

# Итоги в БД (после завершения)
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -c "
SELECT
  (SELECT COUNT(*) FROM bitrix_leads WHERE entity_type='lead') AS leads,
  (SELECT COUNT(*) FROM bitrix_leads WHERE entity_type='contact') AS contacts,
  (SELECT COUNT(*) FROM bitrix_activities) AS activities,
  (SELECT COUNT(*) FROM bitrix_summaries) AS summaries;
"
```

---

## Шаг 7: Проверь работу (5 минут)

### 7.1 Проверь логи orchestrator

```bash
docker compose logs orchestrator -f
```

### 7.2 Проверь базу данных

```bash
# Jitsi-записи
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT filename, status FROM processed_files ORDER BY id DESC LIMIT 5;"

# Bitrix-данные
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "SELECT entity_type, COUNT(*) FROM bitrix_leads GROUP BY entity_type;"
```

### 7.3 Проверь Dify

Открой `https://dify-ff.duckdns.org` → Knowledge → должны появиться блокноты `ФФ-4405`, `BX-LEAD-*` и т.д.

### 7.4 Проверь Telegram бота

Отправь `/status` в чат с ботом — должен ответить статусом системы.

---

## Как пользоваться

### Ежедневная работа (автоматически)

| Время | Событие |
|-------|---------|
| Каждые 5 мин | Сканирование новых Jitsi-записей |
| **06:00** | Синхронизация из Битрикс24 (звонки, письма, комменты) |
| 22:00 | Саммари по клиентам (Jitsi) |
| 23:00 | Дайджест в Telegram |

### Bitrix24 → Dify: именование блокнотов

| Тип клиента | Название блокнота | Пример |
|---|---|---|
| Контакт с договором (поле ФФ-номера заполнено) | `ФФ-NNNN` | `ФФ-4405` |
| Лид с ФФ в названии ("Иван, ФФ-4405") | `ФФ-NNNN` | `ФФ-4405` |
| Лид без ФФ-номера | `BX-LEAD-{id}` | `BX-LEAD-12345` |
| Контакт без договора | `BX-CONTACT-{id}` | `BX-CONTACT-789` |

### RAG-чат "ФФ Ассистент куратора"

Куратор пишет: **"как там ФФ-4405 поживает?"**
→ Dify ищет в блокноте `ФФ-4405`
→ Отвечает на основе всей истории звонков, писем и комментариев

### Jitsi-созвоны

1. **Проводишь созвон в Jitsi**
   - Комната: `LEAD-12345-conf` (12345 = ID клиента)
   - Запись начнётся автоматически

2. **Система обрабатывает автоматически**
   - Каждые 5 минут сканирует /recordings
   - Транскрибирует через Whisper
   - Сохраняет в базу

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
tail -100 /root/bitrix_sync.log    # Bitrix историческая синхронизация
```

### Перезапуск

```bash
docker compose restart orchestrator
```

### Сброс зависших транскрипций (Jitsi)

```bash
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n \
  -c "DELETE FROM processed_files WHERE status='transcribing' AND created_at < NOW()-INTERVAL '30 minutes';"
```

### Нет сообщений в Telegram

1. Проверь токен: `curl https://api.telegram.org/bot{ТОКЕН}/getMe`
2. Проверь chat_id: отправь сообщение и вызови getUpdates

### Bitrix блокнот не создаётся в Dify

```bash
# Проверить ФФ-парсер
docker exec mvp-auto-summary-orchestrator-1 python -c "
from app.tasks.bitrix_summary import _extract_ff_number
print(_extract_ff_number('Иван Петров, ФФ-4405'))
"
```

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

*Обновлено: 2026-03-09 — добавлена Bitrix24 интеграция, ФФ-именование блокнотов, историческая синхронизация*
