#!/usr/bin/env python3
"""
generate_individual_summary.py — Генерация индивидуального summary по клиенту.

Использование:
    # Summary по звонку (транскрипт из open-notebook/PostgreSQL):
    python3 generate_individual_summary.py --lead-id 101 --source call

    # Summary по чату (из таблицы chat_messages):
    python3 generate_individual_summary.py --lead-id 101 --source chat

    # Оба (combined):
    python3 generate_individual_summary.py --lead-id 101 --source both

Результат:
    /exports/summaries/2026-02-20/LEAD-101_call_2026-02-20.md
    /exports/summaries/2026-02-20/LEAD-101_chat_2026-02-20.md
    Запись в таблице client_summaries в PostgreSQL

Требования:
    pip3 install psycopg2-binary requests
"""

import os
import sys
import json
import argparse
import requests
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

DB_CONFIG = {
    'host': os.environ.get('POSTGRES_HOST', 'localhost'),
    'port': int(os.environ.get('POSTGRES_PORT', 5432)),
    'database': os.environ.get('POSTGRES_DB', 'n8n'),
    'user': os.environ.get('POSTGRES_USER', 'n8n'),
    'password': os.environ.get('POSTGRES_PASSWORD', ''),
}

SUMMARIES_DIR = os.environ.get('SUMMARIES_DIR', '/root/mvp-auto-summary/exports/summaries')

# =========== ПРОМПТЫ ===========

CALL_SUMMARY_PROMPT = """Ты бизнес-аналитик. Проанализируй транскрипцию созвона с клиентом.

ВЫХОДНОЙ ФОРМАТ (строго):

## Краткое резюме
[2-3 предложения о главном]

## Участники
- Менеджер: [имя или "не указан"]
- Клиент: [компания/имя или "не указан"]

## Ключевые договорённости
- [пункт 1]
- [пункт 2 или "Не зафиксировано"]

## Action Items
- [ ] [задача] — [ответственный] — [дедлайн или "без срока"]

## Риски и блокеры
- [риск 1 или "Нет"]

## Следующие шаги
- [что делать дальше]

## Важные цитаты клиента
> "[цитата 1 или нет цитат]"
"""

CHAT_SUMMARY_PROMPT = """Ты бизнес-аналитик. Проанализируй историю переписки с клиентом в Telegram.

ВЫХОДНОЙ ФОРМАТ (строго):

## Период общения
[дата первого и последнего сообщения]

## Основные темы
- [тема 1]
- [тема 2 или "одна тема"]

## Ключевые договорённости
- [пункт 1 или "Не зафиксировано"]

## Open questions (вопросы без ответа)
- [вопрос 1 или "Нет"]

## Тон клиента
[позитивный/нейтральный/негативный + кратко почему]

## Следующие шаги
- [что нужно сделать]
"""

# =========== ФУНКЦИИ ===========

def connect_db():
    """Подключение к PostgreSQL"""
    try:
        return psycopg2.connect(**DB_CONFIG)
    except Exception as e:
        print(f"❌ Ошибка подключения к PostgreSQL: {e}")
        sys.exit(1)


def get_call_transcripts(lead_id: str, target_date: date, conn) -> list:
    """Получить транскрипты созвонов за дату"""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT id, filename, transcript_text, created_at
            FROM processed_files
            WHERE lead_id = %s
              AND status = 'completed'
              AND transcript_text IS NOT NULL
              AND DATE(created_at) = %s
            ORDER BY created_at
        """, (lead_id, target_date))
        
        rows = cur.fetchall()
        return [
            {'id': r[0], 'filename': r[1], 'text': r[2], 'created_at': r[3]}
            for r in rows
        ]


def get_chat_messages(lead_id: str, target_date: date, conn, all_history: bool = False) -> list:
    """Получить сообщения чата за дату (или всю историю если all_history=True)"""
    with conn.cursor() as cur:
        if all_history:
            cur.execute("""
                SELECT id, chat_title, sender, message_text, message_date
                FROM chat_messages
                WHERE lead_id = %s
                ORDER BY message_date
            """, (lead_id,))
        else:
            cur.execute("""
                SELECT id, chat_title, sender, message_text, message_date
                FROM chat_messages
                WHERE lead_id = %s
                  AND DATE(message_date) = %s
                ORDER BY message_date
            """, (lead_id, target_date))
        
        rows = cur.fetchall()
        return [
            {
                'id': r[0],
                'chat_title': r[1],
                'sender': r[2],
                'text': r[3],
                'date': r[4]
            }
            for r in rows
        ]


def call_glm4(prompt: str, content: str, max_tokens: int = 2000) -> str:
    """Вызвать GLM-4 для суммаризации"""
    headers = {
        "Authorization": f"Bearer {GLM_API_KEY}",
        "Content-Type": "application/json"
    }
    
    payload = {
        "model": GLM_MODEL,
        "messages": [
            {"role": "system", "content": prompt},
            {"role": "user", "content": content}
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
        
        # Fallback на reasoning_content если content пустой (E043)
        content_text = (msg.get('content') or '').strip()
        reasoning_text = (msg.get('reasoning_content') or '').strip()
        
        return content_text or reasoning_text or 'Summary не получено.'
        
    except requests.exceptions.Timeout:
        return f"❌ Timeout: GLM-4 не ответил за 120 секунд. Попробуй позже."
    except Exception as e:
        return f"❌ Ошибка GLM-4: {str(e)}"


def save_summary(lead_id: str, source_type: str, summary_text: str, 
                 target_date: date, filename_extra: str = '') -> str:
    """Сохранить summary в файл"""
    date_str = target_date.strftime('%Y-%m-%d')
    dir_path = os.path.join(SUMMARIES_DIR, date_str)
    os.makedirs(dir_path, exist_ok=True)
    
    extra = f"_{filename_extra}" if filename_extra else ''
    filename = f"LEAD-{lead_id}_{source_type}{extra}_{date_str}.md"
    file_path = os.path.join(dir_path, filename)
    
    header = f"# Summary: LEAD-{lead_id} | {source_type.upper()} | {date_str}\n\n"
    header += f"_Сгенерировано: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Модель: {GLM_MODEL}_\n\n---\n\n"
    
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(header + summary_text)
    
    return file_path


def save_summary_to_db(lead_id: str, source_type: str, source_id: int,
                       summary_text: str, target_date: date, conn):
    """Сохранить summary в таблицу client_summaries"""
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO client_summaries 
                (lead_id, source_type, source_id, summary_text, summary_date)
            VALUES (%s, %s, %s, %s, %s)
        """, (lead_id, source_type, source_id, summary_text, target_date))
        conn.commit()


def generate_call_summaries(lead_id: str, target_date: date, conn) -> list:
    """Генерировать summary для всех звонков"""
    transcripts = get_call_transcripts(lead_id, target_date, conn)
    
    if not transcripts:
        print(f"  ℹ️  Нет транскриптов за {target_date} для LEAD-{lead_id}")
        return []
    
    print(f"  Найдено транскриптов: {len(transcripts)}")
    summaries = []
    
    for i, call in enumerate(transcripts):
        print(f"  [{i+1}/{len(transcripts)}] Обработка: {call['filename']}")
        
        # Извлекаем время из имени файла
        parts = call['filename'].split('_')
        time_str = parts[2].replace('.wav', '').replace('.mp3', '').replace('.webm', '') if len(parts) > 2 else '00-00'
        
        summary_text = call_glm4(CALL_SUMMARY_PROMPT, call['text'])
        
        file_path = save_summary(lead_id, 'call', summary_text, target_date, time_str)
        save_summary_to_db(lead_id, 'call', call['id'], summary_text, target_date, conn)
        
        print(f"    ✅ Сохранено: {file_path}")
        summaries.append({'type': 'call', 'file': file_path, 'summary': summary_text})
    
    return summaries


def generate_chat_summary(lead_id: str, target_date: date, conn, all_history: bool = False) -> dict:
    """Генерировать summary для чата"""
    messages = get_chat_messages(lead_id, target_date, conn, all_history=all_history)
    
    if not messages:
        if all_history:
            print(f"  ℹ️  Нет сообщений в базе для LEAD-{lead_id}")
        else:
            print(f"  ℹ️  Нет сообщений за {target_date} для LEAD-{lead_id}")
        return None
    
    period = "вся история" if all_history else str(target_date)
    print(f"  Найдено сообщений: {len(messages)} ({period})")
    
    # Форматируем чат для GLM
    chat_title = messages[0]['chat_title']
    chat_text = f"Чат: {chat_title}\n\n"
    for msg in messages:
        chat_text += f"[{msg['date'].strftime('%Y-%m-%d %H:%M')}] {msg['sender']}: {msg['text']}\n"
    
    # Ограничение контекста (50K символов)
    if len(chat_text) > 50000:
        chat_text = chat_text[:50000] + "\n...[сообщения обрезаны]"
    
    summary_text = call_glm4(CHAT_SUMMARY_PROMPT, chat_text)
    
    file_path = save_summary(lead_id, 'chat', summary_text, target_date)
    
    # Используем ID последнего сообщения как source_id
    save_summary_to_db(lead_id, 'chat', messages[-1]['id'], summary_text, target_date, conn)
    
    print(f"  ✅ Сохранено: {file_path}")
    return {'type': 'chat', 'file': file_path, 'summary': summary_text}


def main():
    parser = argparse.ArgumentParser(
        description='Генерация индивидуального summary по клиенту',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Примеры:
  # Summary по звонку за сегодня:
  python3 generate_individual_summary.py --lead-id 101 --source call

  # Summary по чату за сегодня:
  python3 generate_individual_summary.py --lead-id 101 --source chat

  # Оба источника:
  python3 generate_individual_summary.py --lead-id 101 --source both

  # За конкретную дату:
  python3 generate_individual_summary.py --lead-id 101 --source both --date 2026-02-20

  # Все лиды за сегодня:
  python3 generate_individual_summary.py --lead-id all --source both
        """
    )
    parser.add_argument('--lead-id', required=True, 
                        help='ID лида (число) или "all" для всех')
    parser.add_argument('--source', choices=['call', 'chat', 'both'], default='both',
                        help='Источник данных (по умолчанию: both)')
    parser.add_argument('--date', default=date.today().strftime('%Y-%m-%d'),
                        help='Дата в формате YYYY-MM-DD (по умолчанию: сегодня)')
    parser.add_argument('--all-history', action='store_true',
                        help='Суммаризировать всю историю чата без фильтра по дате')
    parser.add_argument('--db-password',
                        help='Пароль PostgreSQL')
    parser.add_argument('--api-key',
                        help='GLM-4 API ключ')
    
    args = parser.parse_args()
    
    if args.db_password:
        DB_CONFIG['password'] = args.db_password
    if args.api_key:
        global GLM_API_KEY
        GLM_API_KEY = args.api_key
    
    try:
        target_date = datetime.strptime(args.date, '%Y-%m-%d').date()
    except ValueError:
        print(f"❌ Неверный формат даты: {args.date}. Используй YYYY-MM-DD")
        sys.exit(1)
    
    conn = connect_db()
    
    all_history = args.all_history

    # Определяем список лидов
    if args.lead_id.lower() == 'all':
        with conn.cursor() as cur:
            lead_ids = set()
            if args.source in ('call', 'both'):
                cur.execute("SELECT DISTINCT lead_id FROM processed_files WHERE status='completed' AND DATE(created_at)=%s", (target_date,))
                lead_ids.update(r[0] for r in cur.fetchall())
            if args.source in ('chat', 'both'):
                if all_history:
                    cur.execute("SELECT DISTINCT lead_id FROM chat_messages")
                else:
                    cur.execute("SELECT DISTINCT lead_id FROM chat_messages WHERE DATE(message_date)=%s", (target_date,))
                lead_ids.update(r[0] for r in cur.fetchall())
        lead_ids = sorted(lead_ids)
    else:
        lead_ids = [args.lead_id]
    
    if not lead_ids:
        print(f"⚠️  Нет данных за {target_date}")
        conn.close()
        sys.exit(0)
    
    period_label = "вся история" if all_history else str(target_date)
    print(f"\n{'='*60}")
    print(f"  Генерация summaries")
    print(f"  Период:   {period_label}")
    print(f"  Лиды:     {', '.join(f'LEAD-{l}' for l in lead_ids)}")
    print(f"  Источник: {args.source}")
    print(f"{'='*60}")
    
    all_summaries = []
    
    for lead_id in lead_ids:
        print(f"\n--- LEAD-{lead_id} ---")
        
        if args.source in ('call', 'both'):
            print("\n  Созвоны:")
            summaries = generate_call_summaries(lead_id, target_date, conn)
            all_summaries.extend(summaries)
        
        if args.source in ('chat', 'both'):
            print("\n  Чат:")
            summary = generate_chat_summary(lead_id, target_date, conn, all_history=all_history)
            if summary:
                all_summaries.append(summary)
    
    conn.close()
    
    date_str = target_date.strftime('%Y-%m-%d')
    print(f"\n{'='*60}")
    print(f"✅ Готово! Создано summaries: {len(all_summaries)}")
    print(f"   Папка: {SUMMARIES_DIR}/{date_str}/")
    print(f"\nСледующий шаг:")
    print(f"  python3 combine_client_data.py --date {date_str}")


if __name__ == '__main__':
    main()
