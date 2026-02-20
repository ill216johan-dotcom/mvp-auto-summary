#!/usr/bin/env python3
"""
export_telegram_chat.py — Выгрузка истории чата из Telegram через Telethon.

Использование:
    python3 export_telegram_chat.py --session session_masha --chat "@client_username" --lead-id 101
    python3 export_telegram_chat.py --session session_petya --chat "123456789" --lead-id 102

Результат:
    ../exports/chats/LEAD-101_chat.json   — полная история в JSON
    ../exports/chats/LEAD-101_chat.txt    — текст для суммаризации

Требования (установить один раз):
    pip3 install telethon
"""

import asyncio
import json
import os
import sys
import argparse
from datetime import datetime

# Установить зависимости если не установлены
try:
    from telethon import TelegramClient
    from telethon.tl.types import User, Chat, Channel
except ImportError:
    print("Устанавливаю telethon...")
    os.system("pip3 install telethon")
    from telethon import TelegramClient
    from telethon.tl.types import User, Chat, Channel


def get_sender_name(sender) -> str:
    """Получить имя отправителя"""
    if sender is None:
        return "Неизвестно"
    if hasattr(sender, 'first_name'):
        parts = [sender.first_name or '', sender.last_name or '']
        name = ' '.join(p for p in parts if p).strip()
        return name if name else f"user_{sender.id}"
    if hasattr(sender, 'title'):
        return sender.title
    return str(sender.id)


async def export_chat(api_id: int, api_hash: str, chat_identifier: str, output_prefix: str,
                      limit: int = 10000, session_file: str = 'mvp_session'):
    """Выгрузить историю чата"""
    
    print(f"\n[1/4] Подключение к Telegram...")
    client = TelegramClient(session_file, api_id, api_hash)
    
    await client.start()
    print("    Подключено!")
    
    print(f"\n[2/4] Поиск чата: {chat_identifier}")
    entity = None
    chat_title = chat_identifier

    # Сначала пробуем напрямую (работает для @username и когда сущность уже в кэше)
    try:
        entity = await client.get_entity(chat_identifier)
        chat_title = getattr(entity, 'title', None) or getattr(entity, 'first_name', None) or chat_identifier
        print(f"    Найден: {chat_title}")
    except Exception:
        pass

    # Если не нашли — ищем по диалогам (работает всегда для числовых ID)
    if entity is None:
        print(f"    Прямой поиск не сработал, ищу в диалогах...")
        try:
            # Нормализуем ID для сравнения
            target_id = int(chat_identifier)
            async for dialog in client.iter_dialogs():
                d_entity = dialog.entity
                # Группы и супергруппы: ID хранится как отрицательное число
                d_id = getattr(d_entity, 'id', None)
                if d_id is None:
                    continue
                # Проверяем разные форматы ID
                possible_ids = [d_id, -d_id, int(f"-100{d_id}"), -(d_id)]
                if target_id in possible_ids or dialog.id == target_id:
                    entity = d_entity
                    chat_title = dialog.name or str(target_id)
                    print(f"    Найден в диалогах: {chat_title}")
                    break
        except Exception as e:
            print(f"    ОШИБКА при поиске в диалогах: {e}")

    if entity is None:
        print(f"    ОШИБКА: чат не найден: {chat_identifier}")
        print("    Проверь что ID правильный (скопирован из list_telegram_chats.py)")
        await client.disconnect()
        sys.exit(1)
    
    print(f"\n[3/4] Загрузка сообщений (максимум {limit})...")
    messages = []
    count = 0
    
    async for message in client.iter_messages(entity, limit=limit):
        if not message.text:
            continue  # Пропускаем медиа без текста
        
        try:
            sender = await message.get_sender()
            sender_name = get_sender_name(sender)
        except Exception:
            sender_name = "Неизвестно"
        
        msg_data = {
            "id": message.id,
            "date": message.date.strftime("%Y-%m-%d %H:%M:%S"),
            "sender": sender_name,
            "text": message.text,
        }
        messages.append(msg_data)
        count += 1
        
        if count % 500 == 0:
            print(f"    Загружено: {count} сообщений...")
    
    # Сортируем от старых к новым
    messages.sort(key=lambda x: x["date"])
    
    print(f"    Всего загружено: {len(messages)} сообщений")
    
    print(f"\n[4/4] Сохранение файлов...")
    
    # Убедимся что папка существует
    os.makedirs(os.path.dirname(output_prefix) if os.path.dirname(output_prefix) else '.', exist_ok=True)
    
    # JSON формат
    json_path = f"{output_prefix}_chat.json"
    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump({
            "chat_title": chat_title,
            "exported_at": datetime.now().isoformat(),
            "total_messages": len(messages),
            "messages": messages
        }, f, ensure_ascii=False, indent=2)
    print(f"    JSON: {json_path}")
    
    # TXT формат (для суммаризации)
    txt_path = f"{output_prefix}_chat.txt"
    with open(txt_path, 'w', encoding='utf-8') as f:
        f.write(f"Чат: {chat_title}\n")
        f.write(f"Экспортировано: {datetime.now().strftime('%d.%m.%Y %H:%M')}\n")
        f.write(f"Сообщений: {len(messages)}\n")
        f.write("=" * 60 + "\n\n")
        
        for msg in messages:
            dt = msg["date"]
            sender = msg["sender"]
            text = msg["text"]
            f.write(f"[{dt}] {sender}: {text}\n")
    
    print(f"    TXT: {txt_path}")
    
    await client.disconnect()
    
    print(f"\n✅ Готово! Файлы сохранены:")
    print(f"   {json_path}")
    print(f"   {txt_path}")
    print(f"\nСледующий шаг:")
    print(f"   python3 import_chat_to_db.py --lead-id ??? --file {json_path}")
    
    return json_path, txt_path


SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def main():
    parser = argparse.ArgumentParser(
        description='Выгрузка истории Telegram чата',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  python3 export_telegram_chat.py --session session_masha --chat "@client_username" --lead-id 101
  python3 export_telegram_chat.py --session session_petya --chat "123456789" --lead-id 102 --limit 5000
  python3 export_telegram_chat.py --session session_ivan  --chat "ООО Ромашка" --lead-id 103
        """
    )
    parser.add_argument('--session', default='mvp_session',
                        help='Имя файла сессии без .session (например: session_masha)')
    parser.add_argument('--chat', required=True, 
                        help='Чат для выгрузки: @username, числовой ID или название')
    parser.add_argument('--lead-id', required=True, 
                        help='ID лида (например: 101)')
    parser.add_argument('--output-dir', default='../exports/chats',
                        help='Папка для сохранения (по умолчанию: ../exports/chats)')
    parser.add_argument('--limit', type=int, default=10000,
                        help='Максимум сообщений (по умолчанию: 10000)')
    
    args = parser.parse_args()
    
    # API credentials захардкожены (одно приложение на всех)
    api_id   = 32782815
    api_hash = 'a4c241e64433835b4a335b62520ab005'

    session_file = os.path.join(SCRIPT_DIR, args.session)

    # Проверяем что сессия существует
    if not os.path.exists(session_file + ".session"):
        print(f"\n❌ Файл сессии не найден: {session_file}.session")
        print(f"\nСначала авторизуй куратора:")
        curator = args.session.replace('session_', '')
        print(f"  python3 authorize_curator.py --name {curator}")
        sys.exit(1)

    output_prefix = os.path.join(args.output_dir, f"LEAD-{args.lead_id}")
    curator_name = args.session.replace('session_', '')

    print(f"\n{'='*60}")
    print(f"  Экспорт чата: {args.chat}")
    print(f"  Куратор:      {curator_name}")
    print(f"  LEAD ID:      {args.lead_id}")
    print(f"  Выход:        {output_prefix}_chat.json")
    print(f"{'='*60}")
    
    asyncio.run(export_chat(api_id, api_hash, args.chat, output_prefix, args.limit, session_file))


if __name__ == '__main__':
    main()
