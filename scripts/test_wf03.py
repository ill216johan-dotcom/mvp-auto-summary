#!/usr/bin/env python3
"""Simulate WF03: Individual Summaries → GLM-4 → Dify"""
import psycopg2, json, urllib.request, os
from datetime import date
from collections import defaultdict

# --- Config ---
DB_PASS = open('/root/mvp-auto-summary/.env').read().split('POSTGRES_PASSWORD=')[1].split('\n')[0]
GLM_API_KEY = '99918695e8de4146a3303043154f4c51.Op8sSKnavRz8PrIQ'
GLM_BASE_URL = 'https://api.z.ai/api/anthropic'
GLM_MODEL = 'claude-3-5-haiku-20241022'
DIFY_API_KEY = 'dataset-k7rrBrS6TsEixGGIyAvywfb0'
DIFY_BASE_URL = 'http://localhost'

conn = psycopg2.connect(host='localhost', dbname='n8n', user='n8n', password=DB_PASS)
cur = conn.cursor()

# Step 1: Load today's calls
cur.execute("""
SELECT pf.id, pf.filename, pf.lead_id, pf.transcript_text
FROM processed_files pf
WHERE pf.status = 'completed'
AND DATE(COALESCE(pf.file_date, pf.completed_at, pf.created_at)) = CURRENT_DATE
AND pf.transcript_text IS NOT NULL
AND (pf.dify_doc_id IS NULL OR pf.dify_doc_id = '')
ORDER BY pf.lead_id, pf.id LIMIT 20
""")
calls = cur.fetchall()
print(f'Found {len(calls)} calls to process')

if not calls:
    print('No calls found. Exiting.')
    exit()

# Step 2: Dataset map
cur.execute('SELECT lead_id, dify_dataset_id FROM lead_chat_mapping WHERE active = true')
ds_map = {row[0]: row[1] for row in cur.fetchall()}

# Step 3: Group by lead
grouped = defaultdict(list)
for call_id, filename, lead_id, text in calls:
    grouped[lead_id].append({'id': call_id, 'filename': filename, 'text': text})

today = date.today().isoformat()

for lead_id, lead_calls in grouped.items():
    print(f'\n=== Processing LEAD-{lead_id} ({len(lead_calls)} calls) ===')
    dataset_id = ds_map.get(lead_id, '')

    # Step 4: GLM-4
    combined = '\n\n'.join([f'--- Звонок {i+1} ({c["filename"]}) ---\n{c["text"]}' for i, c in enumerate(lead_calls)])
    prompt = 'Ты бизнес-аналитик. Проанализируй транскрипцию(и) созвона с клиентом.\nВыдай:\n1) Краткое резюме (2-3 предл.)\n2) Участники звонка\n3) Ключевые договорённости\n4) Action Items с дедлайнами (если есть)\n5) Риски/проблемы\n6) Тон клиента (позитивный/нейтральный/негативный)\nФормат: Markdown. Не более 1500 слов.'

    glm_payload = json.dumps({
        'model': GLM_MODEL,
        'system': prompt,
        'messages': [
            {'role': 'user', 'content': combined}
        ],
        'max_tokens': 2000
    }).encode()

    req = urllib.request.Request(
        f'{GLM_BASE_URL}/v1/messages',
        data=glm_payload,
        headers={
            'x-api-key': GLM_API_KEY,
            'anthropic-version': '2023-06-01',
            'Content-Type': 'application/json'
        }
    )

    try:
        resp = urllib.request.urlopen(req, timeout=120)
        glm_data = json.loads(resp.read())
        print('API response keys:', list(glm_data.keys()))
        # Support both OpenAI and Anthropic response formats
        if 'choices' in glm_data:
            summary = glm_data['choices'][0]['message']['content'].strip()
        elif 'content' in glm_data:
            # Anthropic format
            texts = [b['text'] for b in glm_data['content'] if b.get('type') == 'text']
            summary = '\n'.join(texts).strip()
        else:
            print(f'Unknown response format: {str(glm_data)[:500]}')
            continue
        print(f'Summary: {len(summary)} chars')
        print(summary[:300] + '...')
    except Exception as e:
        print(f'LLM ERROR: {e}')
        continue

    # Step 5: Write MD
    filename_md = f'LEAD-{lead_id}_call_{today}.md'
    md_dir = f'/var/lib/docker/volumes/mvp-auto-summary_summaries_data/_data/{today}'
    os.makedirs(md_dir, exist_ok=True)
    with open(f'{md_dir}/{filename_md}', 'w', encoding='utf-8') as f:
        f.write(summary)
    print(f'MD file: {md_dir}/{filename_md}')

    # Step 6: Dify push
    doc_id = ''
    if dataset_id:
        doc_name = f'[{today}] LEAD-{lead_id} — Созвоны ({len(lead_calls)} звонок)'
        dify_payload = json.dumps({
            'name': doc_name,
            'text': summary,
            'indexing_technique': 'high_quality',
            'process_rule': {'mode': 'automatic'}
        }).encode()
        dify_req = urllib.request.Request(
            f'{DIFY_BASE_URL}/v1/datasets/{dataset_id}/document/create-by-text',
            data=dify_payload,
            headers={'Authorization': f'Bearer {DIFY_API_KEY}', 'Content-Type': 'application/json'}
        )
        try:
            dify_resp = urllib.request.urlopen(dify_req, timeout=60)
            dify_data = json.loads(dify_resp.read())
            doc_id = dify_data.get('document', {}).get('id', '')
            print(f'Dify doc: {doc_id}')
        except Exception as e:
            print(f'Dify ERROR: {e}')

    # Step 7: Save to DB
    call_ids = [c['id'] for c in lead_calls]
    cur.execute(
        'INSERT INTO client_summaries (lead_id, source_type, summary_text, summary_date) VALUES (%s, %s, %s, %s) RETURNING id',
        (lead_id, 'call', summary, today)
    )
    sid = cur.fetchone()[0]
    for cid in call_ids:
        cur.execute('UPDATE processed_files SET dify_doc_id=%s, summary_text=%s WHERE id=%s', (doc_id, summary, cid))
    conn.commit()
    print(f'DB saved: summary_id={sid}')
    print(f'LEAD-{lead_id} DONE!')

conn.close()
print('\n=== WF03 COMPLETE ===')
