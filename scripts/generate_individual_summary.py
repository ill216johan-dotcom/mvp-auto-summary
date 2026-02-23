#!/usr/bin/env python3
"""
Generate individual summary for a client from calls and chats.

Usage:
    python3 generate_individual_summary.py --lead-id 101 --date 2026-02-20 --output ./exports/summaries/
"""

import argparse
import json
import os
from datetime import datetime

# GLM-4 API configuration
GLM4_API_URL = "https://open.bigmodel.cn/api/paas/v4/chat/completions"
GLM4_API_KEY = "fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6"
GLM4_MODEL = "glm-4.7-flash"

# Prompts
PROMPT_CALL_SUMMARY = """Ты бизнес-аналитик. Проанализируй транскрипцию созвона с клиентом.

ВЫХОДНОЙ ФОРМАТ (строго):

## Краткое резюме
[2-3 предложения о главном]

## Участники
- Менеджер: [имя если есть]
- Клиент: [информация если есть]

## Ключевые договорённости
- [пункт 1]
- [пункт 2]

## Action Items
- [ ] [задача] — [ответственный] — [дедлайн если есть]

## Риски и блокеры
- [риск 1 или "Нет"]

## Следующие шаги
- [что делать дальше]

## Важные цитаты клиента
> "[цитата 1 если есть]"
"""

PROMPT_CHAT_SUMMARY = """Ты бизнес-аналитик. Проанализируй историю переписки с клиентом в Telegram.

ВЫХОДНОЙ ФОРМАТ (строго):

## Период общения
[даты первой и последней переписки]

## Основные темы
- [тема 1]
- [тема 2]

## Ключевые договорённости
- [пункт 1]
- [пункт 2]

## Open questions (вопросы без ответа)
- [вопрос 1 или "Нет"]

## Тон клиента
[позитивный/нейтральный/негативный + краткое пояснение]

## Следующие шаги
- [что нужно сделать]
"""

def parse_args():
    parser = argparse.ArgumentParser(description='Generate individual client summary')
    parser.add_argument('--lead-id', required=True, help='LEAD-ID of the client')
    parser.add_argument('--date', required=True, help='Date (YYYY-MM-DD)')
    parser.add_argument('--output', default='./exports/summaries/', help='Output directory')
    parser.add_argument('--db-host', default='localhost', help='Database host')
    parser.add_argument('--combine', action='store_true', help='Generate combined summary')
    return parser.parse_args()

def get_data_from_db(lead_id, date, db_host):
    """Get call and chat data from database."""
    # This is a placeholder - in production, connect to PostgreSQL
    # For now, we'll work with files
    
    calls = []
    chats = []
    
    # Look for exported files
    exports_dir = './exports/'
    chat_file = os.path.join(exports_dir, 'chats', f'LEAD-{lead_id}_chat.json')
    
    if os.path.exists(chat_file):
        with open(chat_file, 'r', encoding='utf-8') as f:
            data = json.load(f)
            chats.append(data)
    
    return calls, chats

def summarize_with_glm4(text, prompt, max_tokens=1500):
    """Call GLM-4 API to summarize text."""
    import urllib.request
    import json
    
    payload = {
        "model": GLM4_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": text}
        ],
        "temperature": 0.2,
        "max_tokens": max_tokens,
        "stream": False,
        "thinking": {"type": "disabled"}
    }
    
    data = json.dumps(payload, ensure_ascii=False).encode('utf-8')
    req = urllib.request.Request(
        GLM4_API_URL,
        data=data,
        headers={
            'Authorization': f'Bearer {GLM4_API_KEY}',
            'Content-Type': 'application/json'
        }
    )
    
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode('utf-8'))
            return result['choices'][0]['message']['content']
    except Exception as e:
        return f"Error calling GLM-4: {e}"

def generate_call_summary(transcript, lead_id, call_time):
    """Generate summary for a call."""
    summary = summarize_with_glm4(transcript[:10000], PROMPT_CALL_SUMMARY)
    
    # Add header
    header = f"""# Summary: Созвон с LEAD-{lead_id}

**Дата:** {call_time}
**Тип:** Созвон
**Источник:** Whisper транскрипция

---

"""
    return header + summary

def generate_chat_summary(messages, lead_id):
    """Generate summary for a chat."""
    # Format messages for summarization
    chat_text = "\n".join([
        f"[{m.get('date', '?')[:16]}] {m.get('sender_name', '?')}: {m.get('text', '')}"
        for m in messages
    ])
    
    summary = summarize_with_glm4(chat_text[:15000], PROMPT_CHAT_SUMMARY)
    
    # Add header
    header = f"""# Summary: Чат с LEAD-{lead_id}

**Тип:** Telegram переписка
**Сообщений:** {len(messages)}
**Период:** {messages[0].get('date', '?')[:10] if messages else '?'} - {messages[-1].get('date', '?')[:10] if messages else '?'}

---

"""
    return header + summary

def generate_combined_summary(call_summaries, chat_summary, lead_id, date):
    """Generate combined summary from all sources."""
    combined_text = "=== СВОНЫ ===\n\n"
    for cs in call_summaries:
        combined_text += cs + "\n\n"
    
    if chat_summary:
        combined_text += "=== ЧАТ ===\n\n" + chat_summary + "\n\n"
    
    prompt = """Ты бизнес-аналитик. Создай ОБЪЕДИНЁННОЕ резюме по клиенту на основе всех источников (созвоны и чаты).

ВЫХОДНОЙ ФОРМАТ (строго):

# Общее резюме по клиенту LEAD-{ID}

## Краткое описание
[2-3 предложения о клиенте и текущем статусе]

## История взаимодействия
[Кратко: сколько было созвонов, переписок, общая динамика]

## Ключевые договорённости (все)
- [пункт 1]
- [пункт 2]

## Открытые Action Items
- [ ] [задача] — [статус]

## Риски и внимание
- [на что обратить внимание]

## Рекомендации
- [что сделать дальше]
"""
    
    combined_prompt = prompt.replace("{ID}", str(lead_id))
    summary = summarize_with_glm4(combined_text[:20000], combined_prompt, max_tokens=2000)
    
    return summary

def main():
    args = parse_args()
    
    # Create output directory
    output_dir = os.path.join(args.output, args.date)
    os.makedirs(output_dir, exist_ok=True)
    
    print(f"Generating summaries for LEAD-{args.lead_id} on {args.date}")
    print(f"Output directory: {output_dir}")
    
    # Get data
    calls, chats = get_data_from_db(args.lead_id, args.date, args.db_host)
    
    # Generate summaries
    call_summaries = []
    
    # If we have chat data, generate chat summary
    if chats:
        for i, chat_data in enumerate(chats):
            messages = chat_data.get('messages', [])
            if messages:
                print(f"Generating chat summary ({len(messages)} messages)...")
                summary = generate_chat_summary(messages, args.lead_id)
                
                output_file = os.path.join(output_dir, f'LEAD-{args.lead_id}_chat.md')
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(summary)
                print(f"Saved: {output_file}")
    
    # If we have call data, generate call summaries
    # (This would be populated from database in production)
    
    # Generate combined summary if requested
    if args.combine:
        print("Generating combined summary...")
        # Load generated summaries
        summaries = []
        for f in os.listdir(output_dir):
            if f.endswith('.md') and f != f'LEAD-{args.lead_id}_combined.md':
                with open(os.path.join(output_dir, f), 'r', encoding='utf-8') as file:
                    summaries.append(file.read())
        
        if summaries:
            combined = generate_combined_summary(summaries, None, args.lead_id, args.date)
            output_file = os.path.join(output_dir, f'LEAD-{args.lead_id}_combined.md')
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(combined)
            print(f"Saved combined summary: {output_file}")
    
    print("\nDone!")

if __name__ == '__main__':
    main()
