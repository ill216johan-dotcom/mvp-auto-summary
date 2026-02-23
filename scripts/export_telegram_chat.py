#!/usr/bin/env python3
"""
Export Telegram chat history to JSON and TXT files.

Usage:
    python3 export_telegram_chat.py --chat "Client Name" --lead-id "101" --output ./exports/

Requirements:
    pip install telethon
"""

import argparse
import json
import os
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.functions.messages import GetHistoryRequest
from telethon.tl.types import PeerUser, PeerChat, PeerChannel

# Configuration
API_ID = None  # Will be set via --api-id or environment
API_HASH = None  # Will be set via --api-hash or environment
SESSION_NAME = 'telegram_export_session'

def parse_args():
    parser = argparse.ArgumentParser(description='Export Telegram chat history')
    parser.add_argument('--chat', required=True, help='Chat name, username, or ID')
    parser.add_argument('--lead-id', required=True, help='LEAD-ID for the client')
    parser.add_argument('--output', default='./exports/chats/', help='Output directory')
    parser.add_argument('--api-id', type=int, help='Telegram API ID')
    parser.add_argument('--api-hash', help='Telegram API Hash')
    parser.add_argument('--limit', type=int, default=1000, help='Max messages to export')
    parser.add_argument('--format', choices=['json', 'txt', 'both'], default='both', help='Output format')
    return parser.parse_args()

async def find_chat(client, chat_name):
    """Find chat by name, username, or ID."""
    # Try as ID first
    try:
        chat_id = int(chat_name)
        return await client.get_entity(chat_id)
    except ValueError:
        pass
    
    # Try as username
    if chat_name.startswith('@'):
        return await client.get_entity(chat_name)
    
    # Search in dialogs
    async for dialog in client.iter_dialogs():
        if chat_name.lower() in dialog.name.lower():
            return dialog.entity
    
    raise ValueError(f"Chat '{chat_name}' not found")

async def export_chat(client, chat, limit=1000):
    """Export chat messages."""
    messages = []
    
    async for message in client.iter_messages(chat, limit=limit):
        msg_data = {
            'id': message.id,
            'date': message.date.isoformat() if message.date else None,
            'sender_id': message.sender_id,
            'text': message.text or '',
            'has_media': message.media is not None,
            'reply_to': message.reply_to_msg_id,
        }
        
        # Try to get sender name
        if message.sender:
            if hasattr(message.sender, 'first_name'):
                msg_data['sender_name'] = message.sender.first_name or ''
                if hasattr(message.sender, 'last_name') and message.sender.last_name:
                    msg_data['sender_name'] += ' ' + message.sender.last_name
            elif hasattr(message.sender, 'title'):
                msg_data['sender_name'] = message.sender.title
            else:
                msg_data['sender_name'] = str(message.sender_id)
        else:
            msg_data['sender_name'] = str(message.sender_id)
        
        messages.append(msg_data)
    
    return messages

def save_json(messages, output_path, lead_id, chat_name):
    """Save messages as JSON."""
    data = {
        'lead_id': lead_id,
        'chat_name': chat_name,
        'exported_at': datetime.now().isoformat(),
        'message_count': len(messages),
        'messages': messages
    }
    
    filepath = os.path.join(output_path, f'LEAD-{lead_id}_chat.json')
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    return filepath

def save_txt(messages, output_path, lead_id, chat_name):
    """Save messages as TXT for summarization."""
    filepath = os.path.join(output_path, f'LEAD-{lead_id}_chat.txt')
    
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write(f"Чат с клиентом: {chat_name}\n")
        f.write(f"LEAD-ID: {lead_id}\n")
        f.write(f"Экспорт: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n")
        f.write(f"Сообщений: {len(messages)}\n")
        f.write("=" * 50 + "\n\n")
        
        for msg in messages:
            date_str = msg['date'][:16] if msg['date'] else 'Unknown'
            sender = msg.get('sender_name', 'Unknown')
            text = msg['text']
            
            f.write(f"[{date_str}] {sender}: {text}\n")
    
    return filepath

async def main():
    args = parse_args()
    
    # Get API credentials
    api_id = args.api_id or os.environ.get('TELEGRAM_API_ID')
    api_hash = args.api_hash or os.environ.get('TELEGRAM_API_HASH')
    
    if not api_id or not api_hash:
        print("ERROR: Telegram API credentials required!")
        print("\n1. Go to https://my.telegram.org/apps")
        print("2. Create an app and get api_id and api_hash")
        print("3. Run with --api-id YOUR_ID --api-hash YOUR_HASH")
        print("\nOr set environment variables:")
        print("  export TELEGRAM_API_ID=12345678")
        print("  export TELEGRAM_API_HASH=abc123...")
        return
    
    # Create output directory
    os.makedirs(args.output, exist_ok=True)
    
    print(f"Connecting to Telegram...")
    async with TelegramClient(SESSION_NAME, api_id, api_hash) as client:
        # Find chat
        print(f"Searching for chat: {args.chat}")
        try:
            chat = await find_chat(client, args.chat)
            chat_name = getattr(chat, 'title', None) or getattr(chat, 'first_name', args.chat)
            print(f"Found: {chat_name}")
        except ValueError as e:
            print(f"ERROR: {e}")
            return
        
        # Export messages
        print(f"Exporting up to {args.limit} messages...")
        messages = await export_chat(client, chat, args.limit)
        print(f"Exported {len(messages)} messages")
        
        # Save files
        if args.format in ['json', 'both']:
            json_path = save_json(messages, args.output, args.lead_id, chat_name)
            print(f"Saved JSON: {json_path}")
        
        if args.format in ['txt', 'both']:
            txt_path = save_txt(messages, args.output, args.lead_id, chat_name)
            print(f"Saved TXT: {txt_path}")
    
    print("\nDone!")

if __name__ == '__main__':
    import asyncio
    asyncio.run(main())
