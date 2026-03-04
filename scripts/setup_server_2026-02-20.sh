#!/bin/bash
# setup_server_2026-02-20.sh — Настройка сервера для тестирования 20.02.2026
#
# Запускать на сервере (84.252.100.93) через PuTTY:
#   bash /root/mvp-auto-summary/scripts/setup_server_2026-02-20.sh

echo ""
echo "============================================================"
echo "  MVP Auto-Summary: Подготовка к тестированию 2026-02-20"
echo "============================================================"
echo ""

# ==================== 1. ПАПКИ ====================
echo "[1/5] Создание папок..."

mkdir -p /mnt/recordings/2026/02/20/
chmod 777 /mnt/recordings/2026/02/20/
mkdir -p /root/mvp-auto-summary/exports/summaries/2026-02-20/
mkdir -p /root/mvp-auto-summary/exports/chats/
mkdir -p /root/mvp-auto-summary/scripts/
chmod -R 777 /root/mvp-auto-summary/exports/

echo "    OK: папки созданы"

# ==================== 2. POSTGRESQL ТАБЛИЦЫ ====================
echo ""
echo "[2/5] Создание таблиц в PostgreSQL..."

docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n << 'EOF'

-- История сообщений из Telegram чатов
CREATE TABLE IF NOT EXISTS chat_messages (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR(50),
    chat_title VARCHAR(255),
    chat_id BIGINT,
    sender VARCHAR(100),
    message_text TEXT,
    message_date TIMESTAMP,
    imported_at TIMESTAMP DEFAULT NOW(),
    summary_sent BOOLEAN DEFAULT FALSE
);

-- Индивидуальные summaries (звонки + чаты)
CREATE TABLE IF NOT EXISTS client_summaries (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR(50),
    source_type VARCHAR(20),
    source_id INTEGER,
    summary_text TEXT,
    summary_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);

-- ТАБЛИЦА МАППИНГА: договор → Telegram чат
-- Заполняется вручную один раз для каждого клиента
CREATE TABLE IF NOT EXISTS lead_chat_mapping (
    id SERIAL PRIMARY KEY,
    lead_id VARCHAR(50) NOT NULL,         -- номер договора / ID клиента
    lead_name VARCHAR(255),               -- название клиента (для удобства)
    chat_id BIGINT,                       -- Telegram chat_id (число, можно получить скриптом)
    chat_username VARCHAR(255),           -- @username группы (если есть)
    chat_title VARCHAR(255),              -- название чата как видно в Telegram
    chat_type VARCHAR(20) DEFAULT 'group', -- 'group', 'supergroup', 'private'
    active BOOLEAN DEFAULT TRUE,          -- можно деактивировать не удаляя
    notes TEXT,                           -- произвольные заметки
    created_at TIMESTAMP DEFAULT NOW()
);

-- Индексы
CREATE INDEX IF NOT EXISTS idx_chat_messages_lead_id ON chat_messages(lead_id);
CREATE INDEX IF NOT EXISTS idx_chat_messages_date ON chat_messages(message_date);
CREATE INDEX IF NOT EXISTS idx_client_summaries_lead_id ON client_summaries(lead_id);
CREATE INDEX IF NOT EXISTS idx_client_summaries_date ON client_summaries(summary_date);
CREATE INDEX IF NOT EXISTS idx_lead_chat_mapping_lead_id ON lead_chat_mapping(lead_id);

SELECT 'OK: все таблицы созданы' as status;
EOF

echo "    OK: таблицы chat_messages, client_summaries, lead_chat_mapping"

# ==================== 3. PYTHON ЗАВИСИМОСТИ ====================
echo ""
echo "[3/5] Установка Python-зависимостей..."

pip3 install telethon psycopg2-binary requests --quiet 2>/dev/null && \
    echo "    OK: telethon, psycopg2-binary, requests установлены" || \
    echo "    WARN: pip3 не сработал, зависимости установятся при первом запуске скрипта"

# ==================== 4. ПЕРЕМЕННЫЕ ОКРУЖЕНИЯ ====================
echo ""
echo "[4/5] Проверка переменных окружения..."

POSTGRES_PASSWORD=$(grep POSTGRES_PASSWORD /root/mvp-auto-summary/.env 2>/dev/null | cut -d= -f2 | tr -d ' \r\n')
TELEGRAM_BOT_TOKEN=$(grep TELEGRAM_BOT_TOKEN /root/mvp-auto-summary/.env 2>/dev/null | cut -d= -f2 | tr -d ' \r\n')

if [ -n "$POSTGRES_PASSWORD" ]; then
    echo "    OK: POSTGRES_PASSWORD найден в .env"
else
    echo "    WARN: POSTGRES_PASSWORD не найден в .env — при запуске скриптов передавай вручную"
fi

if [ -n "$TELEGRAM_BOT_TOKEN" ]; then
    echo "    OK: TELEGRAM_BOT_TOKEN найден в .env"
fi

# ==================== 5. ИТОГ ====================
echo ""
echo "[5/5] Проверка..."

echo ""
echo "    Папки:"
[ -d /mnt/recordings/2026/02/20/ ]                             && echo "    OK  /mnt/recordings/2026/02/20/" || echo "    FAIL /mnt/recordings/2026/02/20/"
[ -d /root/mvp-auto-summary/exports/summaries/2026-02-20/ ]    && echo "    OK  exports/summaries/2026-02-20/" || echo "    FAIL exports/summaries/2026-02-20/"
[ -d /root/mvp-auto-summary/exports/chats/ ]                   && echo "    OK  exports/chats/" || echo "    FAIL exports/chats/"

echo ""
echo "    Таблицы:"
docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -tAc \
    "SELECT string_agg('    OK  ' || table_name, E'\n') FROM information_schema.tables WHERE table_schema='public' AND table_name IN ('chat_messages','client_summaries','lead_chat_mapping','processed_files');"

echo ""
echo "============================================================"
echo "  ГОТОВО!"
echo ""
  echo "  Что дальше:"
  echo ""
  echo "  1. На РАБОЧЕМ КОМПЬЮТЕРЕ авторизуй каждого куратора (один раз):"
  echo "     python3 authorize_curator.py --name masha"
  echo "     python3 authorize_curator.py --name petya"
  echo "     (создаст файлы session_masha.session, session_petya.session)"
  echo ""
  echo "  2. Скопируй .session файлы через WinSCP на сервер:"
  echo "     → /root/mvp-auto-summary/scripts/session_masha.session"
  echo "     → /root/mvp-auto-summary/scripts/session_petya.session"
  echo ""
  echo "  3. Получи список чатов каждого куратора:"
  echo "     cd /root/mvp-auto-summary/scripts"
  echo "     python3 list_telegram_chats.py --session session_masha"
  echo "     python3 list_telegram_chats.py --session session_petya"
  echo ""
  echo "  4. Выгрузить конкретный чат:"
  echo "     python3 export_telegram_chat.py --session session_masha --chat CHAT_ID --lead-id 101"
  echo ""
  echo "  Пароль PostgreSQL:"
  echo "     grep POSTGRES_PASSWORD /root/mvp-auto-summary/.env"
echo "============================================================"
