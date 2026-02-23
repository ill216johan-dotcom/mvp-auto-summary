#!/usr/bin/env python3
"""
Import exported Telegram chat into PostgreSQL database.

Usage:
    python3 import_chat_to_db.py --file ./exports/chats/LEAD-101_chat.json --lead-id 101
"""

import argparse
import json
import os
import sys
from datetime import datetime

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

def parse_args():
    parser = argparse.ArgumentParser(description='Import Telegram chat to database')
    parser.add_argument('--file', required=True, help='Path to exported JSON file')
    parser.add_argument('--lead-id', help='Override LEAD-ID (optional, uses file value if not set)')
    parser.add_argument('--db-host', default='localhost', help='Database host')
    parser.add_argument('--db-port', type=int, default=5432, help='Database port')
    parser.add_argument('--db-name', default='n8n', help='Database name')
    parser.add_argument('--db-user', default='n8n', help='Database user')
    parser.add_argument('--db-password', default='', help='Database password')
    return parser.parse_args()

def import_with_psycopg2(args):
    """Import using psycopg2 (if available)."""
    try:
        import psycopg2
    except ImportError:
        return False, "psycopg2 not installed"
    
    # Load JSON file
    with open(args.file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    lead_id = args.lead_id or data.get('lead_id', 'UNKNOWN')
    chat_name = data.get('chat_name', 'Unknown Chat')
    messages = data.get('messages', [])
    
    # Connect to database
    conn = psycopg2.connect(
        host=args.db_host,
        port=args.db_port,
        dbname=args.db_name,
        user=args.db_user,
        password=args.db_password
    )
    
    cursor = conn.cursor()
    inserted = 0
    
    for msg in messages:
        # Parse date
        msg_date = None
        if msg.get('date'):
            try:
                msg_date = datetime.fromisoformat(msg['date'].replace('Z', '+00:00'))
            except:
                pass
        
        # Insert message
        cursor.execute("""
            INSERT INTO chat_messages 
            (lead_id, chat_title, sender, message_text, message_date, summary_sent)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            lead_id,
            chat_name,
            msg.get('sender_name', 'Unknown'),
            msg.get('text', ''),
            msg_date,
            False
        ))
        inserted += 1
    
    conn.commit()
    cursor.close()
    conn.close()
    
    return True, f"Imported {inserted} messages for LEAD-{lead_id}"

def import_with_docker_exec(args):
    """Import using docker exec (fallback method)."""
    # Load JSON file
    with open(args.file, 'r', encoding='utf-8') as f:
        data = json.load(f)
    
    lead_id = args.lead_id or data.get('lead_id', 'UNKNOWN')
    chat_name = data.get('chat_name', 'Unknown Chat').replace("'", "''")
    messages = data.get('messages', [])
    
    # Generate SQL statements
    sql_statements = []
    for msg in messages:
        sender = msg.get('sender_name', 'Unknown').replace("'", "''")
        text = msg.get('text', '').replace("'", "''")
        
        msg_date = 'NULL'
        if msg.get('date'):
            try:
                dt = datetime.fromisoformat(msg['date'].replace('Z', '+00:00'))
                msg_date = f"'{dt.isoformat()}'"
            except:
                pass
        
        sql = f"INSERT INTO chat_messages (lead_id, chat_title, sender, message_text, message_date, summary_sent) VALUES ('{lead_id}', '{chat_name}', '{sender}', '{text[:5000]}', {msg_date}, false);"
        sql_statements.append(sql)
    
    # Write to temp file
    temp_file = '/tmp/import_chat.sql'
    with open(temp_file, 'w', encoding='utf-8') as f:
        f.write('\n'.join(sql_statements))
    
    print(f"Generated {len(sql_statements)} SQL statements")
    print(f"Saved to: {temp_file}")
    print(f"\nTo import, run on server:")
    print(f"  docker cp /tmp/import_chat.sql mvp-auto-summary-postgres-1:/tmp/")
    print(f"  docker exec mvp-auto-summary-postgres-1 psql -U n8n -d n8n -f /tmp/import_chat.sql")
    
    return True, f"Generated SQL file with {len(sql_statements)} statements"

def main():
    args = parse_args()
    
    if not os.path.exists(args.file):
        print(f"ERROR: File not found: {args.file}")
        return
    
    # Try psycopg2 first
    success, message = import_with_psycopg2(args)
    
    if not success:
        print(f"Note: {message}")
        print("Falling back to SQL file generation...")
        success, message = import_with_docker_exec(args)
    
    print(message)

if __name__ == '__main__':
    main()
