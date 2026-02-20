#!/usr/bin/env python3
"""
import_chat_to_db.py — Импорт выгруженного Telegram чата в PostgreSQL.

Использование:
    python3 import_chat_to_db.py --lead-id 101 --file ../exports/chats/LEAD-101_chat.json

    # Или для текстового файла (ручная выгрузка):
    python3 import_chat_to_db.py --lead-id 101 --file ../exports/chats/LEAD-101_chat.txt --format txt

Результат:
    Сообщения сохраняются в таблицу chat_messages в PostgreSQL

Требования:
    pip3 install psycopg2-binary
"""

import json
import os
import sys
import argparse
import re
from datetime import datetime

try:
    import psycopg2
    from psycopg2.extras import execute_batch
except ImportError:
    print("Устанавливаю psycopg2-binary...")
    os.system("pip3 install psycopg2-binary")
    import psycopg2
    from psycopg2.extras import execute_batch


# PostgreSQL connection settings
DB_CONFIG = {
    'host': os.environ.get('POSTGRES_HOST', 'localhost'),
    'port': int(os.environ.get('POSTGRES_PORT', 5432)),
    'database': os.environ.get('POSTGRES_DB', 'n8n'),
    'user': os.environ.get('POSTGRES_USER', 'n8n'),
    'password': os.environ.get('POSTGRES_PASSWORD', ''),
}


def connect_db():
    """Подключение к PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        print(f"\n❌ Ошибка подключения к PostgreSQL: {e}")
        print("\nПроверь:")
        print("  1. Docker контейнер запущен: docker ps | grep postgres")
        print("  2. Пароль: посмотри в .env файле (POSTGRES_PASSWORD)")
        print("  3. Порт доступен: если запускаешь на сервере — используй порт 5432")
        print("     Если с локальной машины — порт из docker-compose.yml")
        sys.exit(1)


def load_json_chat(file_path: str, lead_id: str) -> list:
    """Загрузить чат из JSON файла (от export_telegram_chat.py)"""
    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    chat_title = data.get('chat_title', f'LEAD-{lead_id} chat')
    messages = data.get('messages', [])
    
    result = []
    for msg in messages:
        try:
            msg_date = datetime.strptime(msg['date'], '%Y-%m-%d %H:%M:%S')
        except ValueError:
            msg_date = datetime.now()
        
        result.append({
            'lead_id': lead_id,
            'chat_title': chat_title,
            'sender': msg.get('sender', 'Неизвестно'),
            'message_text': msg.get('text', ''),
            'message_date': msg_date,
        })
    
    return result


def load_txt_chat(file_path: str, lead_id: str) -> list:
    """Загрузить чат из TXT файла (ручная выгрузка)"""
    # Паттерны формата:
    # [10.02.2026 14:30] Алексей: Текст сообщения
    # [2026-02-10 14:30:00] Алексей: Текст
    patterns = [
        r'\[(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2})\]\s+([^:]+):\s+(.*)',  # DD.MM.YYYY HH:MM
        r'\[(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2}:\d{2})\]\s+([^:]+):\s+(.*)',  # YYYY-MM-DD HH:MM:SS
        r'(\d{2}\.\d{2}\.\d{4}),\s+(\d{2}:\d{2})\s+-\s+([^:]+):\s+(.*)',  # Telegram Desktop export
    ]
    
    chat_title = f'LEAD-{lead_id} chat (ручной импорт)'
    result = []
    
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Читаем строки заголовка чтобы найти title
    lines = content.split('\n')
    for line in lines[:5]:
        if line.startswith('Чат:'):
            chat_title = line.replace('Чат:', '').strip()
            break
    
    # Парсим сообщения
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        parsed = False
        for pattern in patterns:
            match = re.match(pattern, line)
            if match:
                groups = match.groups()
                date_str = groups[0]
                time_str = groups[1]
                sender = groups[2].strip()
                text = groups[3].strip()
                
                # Парсим дату
                try:
                    if '.' in date_str:
                        dt_str = f"{date_str} {time_str}"
                        if len(time_str) == 5:  # HH:MM
                            msg_date = datetime.strptime(dt_str, '%d.%m.%Y %H:%M')
                        else:
                            msg_date = datetime.strptime(dt_str, '%d.%m.%Y %H:%M:%S')
                    else:
                        dt_str = f"{date_str} {time_str}"
                        if len(time_str) == 5:
                            msg_date = datetime.strptime(dt_str, '%Y-%m-%d %H:%M')
                        else:
                            msg_date = datetime.strptime(dt_str, '%Y-%m-%d %H:%M:%S')
                except ValueError:
                    msg_date = datetime.now()
                
                result.append({
                    'lead_id': lead_id,
                    'chat_title': chat_title,
                    'sender': sender,
                    'message_text': text,
                    'message_date': msg_date,
                })
                parsed = True
                break
        
        # Если строка не распознана и уже есть сообщения — это продолжение предыдущего
        if not parsed and result and not line.startswith('[') and not line.startswith('='):
            result[-1]['message_text'] += '\n' + line
    
    return result


def import_messages(messages: list, conn, clear_existing: bool = False) -> int:
    """Загрузить сообщения в PostgreSQL"""
    if not messages:
        print("  Нет сообщений для импорта")
        return 0
    
    lead_id = messages[0]['lead_id']
    
    with conn.cursor() as cur:
        if clear_existing:
            cur.execute("DELETE FROM chat_messages WHERE lead_id = %s", (lead_id,))
            print(f"  Удалены старые сообщения для LEAD-{lead_id}")
        
        # Проверяем сколько уже есть
        cur.execute("SELECT COUNT(*) FROM chat_messages WHERE lead_id = %s", (lead_id,))
        existing = cur.fetchone()[0]
        
        # Вставляем батчами
        insert_sql = """
            INSERT INTO chat_messages 
                (lead_id, chat_title, sender, message_text, message_date)
            VALUES 
                (%(lead_id)s, %(chat_title)s, %(sender)s, %(message_text)s, %(message_date)s)
        """
        
        execute_batch(cur, insert_sql, messages, page_size=500)
        conn.commit()
        
        cur.execute("SELECT COUNT(*) FROM chat_messages WHERE lead_id = %s", (lead_id,))
        new_total = cur.fetchone()[0]
        
        imported = new_total - existing
    
    return imported


def main():
    parser = argparse.ArgumentParser(
        description='Импорт Telegram чата в PostgreSQL',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Из JSON (после export_telegram_chat.py):
  python3 import_chat_to_db.py --lead-id 101 --file ../exports/chats/LEAD-101_chat.json

  # Из TXT (ручная выгрузка из Telegram Desktop):
  python3 import_chat_to_db.py --lead-id 102 --file ../exports/chats/LEAD-102_chat.txt --format txt

  # Перезаписать существующие данные:
  python3 import_chat_to_db.py --lead-id 101 --file chat.json --clear

Переменные окружения для БД:
  POSTGRES_HOST=localhost (или имя контейнера)
  POSTGRES_PORT=5432
  POSTGRES_DB=n8n
  POSTGRES_USER=n8n
  POSTGRES_PASSWORD=ваш_пароль
        """
    )
    parser.add_argument('--lead-id', required=True, help='ID лида (например: 101)')
    parser.add_argument('--file', required=True, help='Файл для импорта (.json или .txt)')
    parser.add_argument('--format', choices=['json', 'txt'], 
                        help='Формат файла (определяется автоматически по расширению)')
    parser.add_argument('--clear', action='store_true', 
                        help='Удалить старые записи этого лида перед импортом')
    parser.add_argument('--db-password', 
                        help='Пароль PostgreSQL (или установи POSTGRES_PASSWORD)')
    
    args = parser.parse_args()
    
    # Устанавливаем пароль если передан
    if args.db_password:
        DB_CONFIG['password'] = args.db_password
    
    if not os.path.exists(args.file):
        print(f"\n❌ Файл не найден: {args.file}")
        sys.exit(1)
    
    # Определяем формат
    file_format = args.format
    if not file_format:
        if args.file.endswith('.json'):
            file_format = 'json'
        elif args.file.endswith('.txt'):
            file_format = 'txt'
        else:
            print("❌ Не могу определить формат файла. Укажи --format json или --format txt")
            sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"  Импорт чата для LEAD-{args.lead_id}")
    print(f"  Файл:   {args.file}")
    print(f"  Формат: {file_format}")
    print(f"{'='*60}")
    
    # Загружаем сообщения
    print(f"\n[1/3] Чтение файла...")
    if file_format == 'json':
        messages = load_json_chat(args.file, args.lead_id)
    else:
        messages = load_txt_chat(args.file, args.lead_id)
    
    print(f"    Прочитано: {len(messages)} сообщений")
    
    if not messages:
        print("\n⚠️  Файл пустой или формат не распознан")
        sys.exit(1)
    
    # Показываем пример
    print(f"\n    Пример первого сообщения:")
    first = messages[0]
    print(f"    [{first['message_date']}] {first['sender']}: {first['message_text'][:100]}...")
    
    # Подключаемся к БД
    print(f"\n[2/3] Подключение к PostgreSQL...")
    conn = connect_db()
    print("    Подключено!")
    
    # Импортируем
    print(f"\n[3/3] Импорт в базу данных...")
    imported = import_messages(messages, conn, clear_existing=args.clear)
    conn.close()
    
    print(f"\n✅ Готово! Импортировано: {imported} сообщений")
    print(f"\nСледующий шаг:")
    print(f"  python3 generate_individual_summary.py --lead-id {args.lead_id} --source chat")


if __name__ == '__main__':
    main()
