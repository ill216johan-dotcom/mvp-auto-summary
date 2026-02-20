#!/usr/bin/env python3
"""
combine_client_data.py — Объединение всех данных по клиенту в один файл + daily digest.

Использование:
    python3 combine_client_data.py --date 2026-02-20

Результат:
    /exports/summaries/2026-02-20/LEAD-101_combined_2026-02-20.md  ← объединённое
    /exports/summaries/2026-02-20/daily_digest_2026-02-20.md       ← краткий дайджест

Требования:
    pip3 install psycopg2-binary requests
"""

import os
import sys
import json
import argparse
import requests
import glob
from datetime import datetime, date

try:
    import psycopg2
except ImportError:
    os.system("pip3 install psycopg2-binary")
    import psycopg2

# =========== НАСТРОЙКИ ===========

GLM_API_KEY = os.environ.get('GLM4_API_KEY', 'fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6')
GLM_ENDPOINT = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GLM_MODEL = "glm-4.7-flash"

SUMMARIES_DIR = os.environ.get('SUMMARIES_DIR', '/root/mvp-auto-summary/exports/summaries')

DB_CONFIG = {
    'host': os.environ.get('POSTGRES_HOST', 'localhost'),
    'port': int(os.environ.get('POSTGRES_PORT', 5432)),
    'database': os.environ.get('POSTGRES_DB', 'n8n'),
    'user': os.environ.get('POSTGRES_USER', 'n8n'),
    'password': os.environ.get('POSTGRES_PASSWORD', ''),
}

TELEGRAM_BOT_TOKEN = os.environ.get('TELEGRAM_BOT_TOKEN', '')
TELEGRAM_CHAT_ID = os.environ.get('TELEGRAM_CHAT_ID', '')

# =========== ПРОМПТЫ ===========

DIGEST_PROMPT = """Ты бизнес-аналитик. Создай СВЕРХКРАТКИЙ ежедневный дайджест на основе предоставленных summaries.

ПРАВИЛА:
- Максимум 500 символов общего текста
- Только самое важное: договорённости, риски, срочное
- По одному предложению на клиента

ФОРМАТ:
📅 Дайджест за {date}

👥 Клиенты: {lead_list}

📝 По каждому:
{lead_lines}

⚠️ Срочное:
• [если есть срочное или риски — укажи, иначе "Нет"]
"""

# =========== ФУНКЦИИ ===========

def connect_db():
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        sys.exit(1)


def call_glm4(system_prompt: str, user_content: str, max_tokens: int = 1000) -> str:
    """Вызвать GLM-4"""
    headers = {
        "Authorization": f"Bearer {GLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": GLM_MODEL,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content}
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
        "thinking": {"type": "disabled"}
    }
    
    try:
        response = requests.post(GLM_ENDPOINT, headers=headers, json=payload, timeout=120)
        response.raise_for_status()
        
        data = response.json()
        msg = data['choices'][0]['message']
        content_text = (msg.get('content') or '').strip()
        reasoning_text = (msg.get('reasoning_content') or '').strip()
        
        return content_text or reasoning_text or 'Дайджест не получен.'
    except Exception as e:
        return f"❌ Ошибка GLM-4: {str(e)}"


def get_summaries_for_date(target_date: date, conn) -> dict:
    """Получить все summaries за дату из БД"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT lead_id, source_type, summary_text
            FROM client_summaries
            WHERE summary_date = %s
            ORDER BY lead_id, source_type
        """, (target_date,))
        
        rows = cur.fetchall()
    
    # Группируем по lead_id
    result = {}
    for lead_id, source_type, summary_text in rows:
        if lead_id not in result:
            result[lead_id] = []
        result[lead_id].append({'type': source_type, 'text': summary_text})
    
    return result


def create_combined_summary(lead_id: str, summaries: list, target_date: date) -> str:
    """Создать объединённый файл для клиента"""
    date_str = target_date.strftime('%Y-%m-%d')
    dir_path = os.path.join(SUMMARIES_DIR, date_str)
    os.makedirs(dir_path, exist_ok=True)
    
    file_path = os.path.join(dir_path, f"LEAD-{lead_id}_combined_{date_str}.md")
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(f"# Сводка по LEAD-{lead_id} за {date_str}\n\n")
        f.write(f"_Создано: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n")
        f.write("---\n\n")
        
        for s in summaries:
            source_label = '📞 Созвон' if s['type'] == 'call' else '💬 Чат'
            f.write(f"## {source_label}\n\n")
            f.write(s['text'])
            f.write("\n\n---\n\n")
    
    return file_path


def send_telegram(text: str, bot_token: str, chat_id: str) -> bool:
    """Отправить сообщение в Telegram"""
    if not bot_token or not chat_id:
        print("  ⚠️  Telegram не настроен (нет TELEGRAM_BOT_TOKEN или TELEGRAM_CHAT_ID)")
        return False
    
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "Markdown"
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.ok:
            return True
        else:
            print(f"  ❌ Telegram ошибка: {response.text}")
            return False
    except Exception as e:
        print(f"  ❌ Telegram исключение: {e}")
        return False


def main():
    parser = argparse.ArgumentParser(
        description='Объединение summaries и генерация daily digest',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # За сегодня:
  python3 combine_client_data.py

  # За конкретную дату:
  python3 combine_client_data.py --date 2026-02-20

  # Отправить дайджест в Telegram:
  python3 combine_client_data.py --send-telegram

  # С указанием параметров вручную:
  python3 combine_client_data.py --date 2026-02-20 --send-telegram --bot-token TOKEN --chat-id -1001234567890
        """
    )
    parser.add_argument('--date', default=date.today().strftime('%Y-%m-%d'),
                        help='Дата YYYY-MM-DD (по умолчанию: сегодня)')
    parser.add_argument('--send-telegram', action='store_true',
                        help='Отправить дайджест в Telegram')
    parser.add_argument('--bot-token', help='Telegram bot token')
    parser.add_argument('--chat-id', help='Telegram chat ID')
    parser.add_argument('--db-password', help='Пароль PostgreSQL')
    parser.add_argument('--api-key', help='GLM-4 API ключ')
    
    args = parser.parse_args()
    
    if args.db_password:
        DB_CONFIG['password'] = args.db_password
    if args.api_key:
        global GLM_API_KEY
        GLM_API_KEY = args.api_key
    
    bot_token = args.bot_token or TELEGRAM_BOT_TOKEN
    chat_id = args.chat_id or TELEGRAM_CHAT_ID
    
    try:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    except ValueError:
        print(f"❌ Неверный формат даты: {args.date}")
        sys.exit(1)
    
    print(f"\n{'='*60}")
    print(f"  Генерация combined summaries и daily digest")
    print(f"  Дата: {target_date}")
    print(f"{'='*60}")
    
    conn = connect_db()
    
    # Получаем все summaries за дату
    print(f"\n[1/4] Загрузка summaries из БД...")
    summaries_by_lead = get_summaries_for_date(target_date, conn)
    
    if not summaries_by_lead:
        print(f"  ⚠️  Нет summaries за {target_date}")
        print("  Сначала запусти: python3 generate_individual_summary.py --date " + args.date)
        conn.close()
        sys.exit(0)
    
    print(f"  Найдено лидов: {len(summaries_by_lead)}")
    
    # Создаём combined файлы
    print(f"\n[2/4] Создание combined файлов...")
    combined_files = []
    all_summaries_text = []
    
    for lead_id in sorted(summaries_by_lead.keys()):
        summaries = summaries_by_lead[lead_id]
        file_path = create_combined_summary(lead_id, summaries, target_date)
        combined_files.append(file_path)
        
        # Текст для дайджеста
        combined_text = f"LEAD-{lead_id}:\n"
        for s in summaries:
            combined_text += s['text'][:500] + "\n"
        all_summaries_text.append(combined_text)
        
        print(f"  ✅ LEAD-{lead_id}: {file_path}")
    
    # Генерируем daily digest через GLM-4
    print(f"\n[3/4] Генерация daily digest (GLM-4)...")
    
    lead_list = ", ".join(f"LEAD-{l}" for l in sorted(summaries_by_lead.keys()))
    lead_lines = "\n".join(f"• LEAD-{l}: [одно предложение]" for l in sorted(summaries_by_lead.keys()))
    
    system_prompt = DIGEST_PROMPT.format(
        date=target_date.strftime('%d.%m.%Y'),
        lead_list=lead_list,
        lead_lines=lead_lines
    )
    
    all_summaries_combined = "\n\n".join(all_summaries_text)
    digest_text = call_glm4(system_prompt, all_summaries_combined, max_tokens=600)
    
    # Сохраняем digest в файл
    date_str = target_date.strftime('%Y-%m-%d')
    dir_path = os.path.join(SUMMARIES_DIR, date_str)
    os.makedirs(dir_path, exist_ok=True)
    digest_file = os.path.join(dir_path, f"daily_digest_{date_str}.md")
    
    with open(digest_file, 'w', encoding='utf-8') as f:
        f.write(f"# Daily Digest — {date_str}\n\n")
        f.write(f"_Создано: {datetime.now().strftime('%Y-%m-%d %H:%M')}_\n\n---\n\n")
        f.write(digest_text)
    
    print(f"  ✅ Digest: {digest_file}")
    
    conn.close()
    
    # Отправляем в Telegram
    print(f"\n[4/4] Telegram...")
    if args.send_telegram:
        success = send_telegram(digest_text, bot_token, chat_id)
        if success:
            print("  ✅ Отправлено в Telegram!")
        else:
            print("  ❌ Не удалось отправить в Telegram")
    else:
        print("  ℹ️  Пропущено (добавь --send-telegram для отправки)")
    
    print(f"\n{'='*60}")
    print(f"✅ Готово!")
    print(f"   Combined файлов: {len(combined_files)}")
    print(f"   Digest: {digest_file}")
    print(f"\nСодержимое digest:")
    print(f"{'─'*40}")
    print(digest_text[:600])
    print(f"{'─'*40}")


if __name__ == '__main__':
    main()
