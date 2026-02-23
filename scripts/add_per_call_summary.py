#!/usr/bin/env python3
"""
Добавляет в Workflow 01 два шага после Save Success?:
  1. GLM-4 Summarize Call — саммари конкретного созвона
  2. Save Call Summary to Notebook — сохраняет в ноутбук

Цепочка:
  Save Success? (yes) → GLM-4 Summarize Call → Save Call Summary to Notebook → Mark Completed
"""
import json, subprocess

WF_ID = 'bLd3WCDd8CEdkl54'

def psql(query):
    r = subprocess.run(
        ['docker','exec','mvp-auto-summary-postgres-1','psql','-U','n8n','-d','n8n','-t','-A','-c', query],
        capture_output=True, text=True
    )
    return r.stdout.strip()

# Читаем nodes и connections
nodes = json.loads(psql(f"SELECT nodes::text FROM workflow_entity WHERE id = '{WF_ID}';"))
connections = json.loads(psql(f"SELECT connections::text FROM workflow_entity WHERE id = '{WF_ID}';"))

print('Nodes:', [n['name'] for n in nodes])

# Находим позицию Mark Completed
mark_completed_pos = [880, 0]
for n in nodes:
    if n['name'] == 'Mark Completed':
        mark_completed_pos = n.get('position', [880, 0])
        break

# === НОДА 1: GLM-4 Summarize Call ===
# HTTP запрос к GLM-4 с промптом саммари конкретного созвона
glm_node = {
    "parameters": {
        "method": "POST",
        "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
        "sendBody": True,
        "specifyBody": "json",
        "jsonBody": "={{ JSON.stringify({ model: 'glm-4.7-flash', messages: [ { role: 'system', content: 'Ты аналитик отдела кураторов фулфилмент-компании. Проанализируй транскрипцию созвона куратора с клиентом.\\n\\nКУРАТОРЫ ОТДЕЛА: Евгений, Кристина, Анна (основные), Галина, Дарья (консультанты), Станислав, Андрей (руководители).\\n\\nВЫДАЙ СТРОГО В ТАКОМ ФОРМАТЕ:\\n\\n## Созвон: LEAD-[ID] [дата]\\n\\n**Куратор:** [определи из текста или «Не определён»]\\n**Клиент:** [название компании/имя если упоминается]\\n\\n**Краткое резюме:** [2-3 предложения — о чём был звонок]\\n\\n**Договорённости:**\\n- [пункт 1]\\n- [пункт 2]\\n\\n**Открытые вопросы:**\\n- [что не решили / требует действий, или «Нет»]\\n\\n**Тон клиента:** [позитивный / нейтральный / негативный]' }, { role: 'user', content: 'LEAD-ID: ' + $json.leadId + '\\n\\nТРАНСКРИПЦИЯ:\\n' + $('Extract Transcript').first().json.transcript } ], temperature: 0.2, max_tokens: 800, stream: false, thinking: { type: 'disabled' } }) }}",
        "sendHeaders": True,
        "headerParameters": {
            "parameters": [
                {"name": "Authorization", "value": "Bearer fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6"},
                {"name": "Content-Type", "value": "application/json"}
            ]
        },
        "options": {"timeout": 120000}
    },
    "id": "glm-summarize-call",
    "name": "GLM-4 Summarize Call",
    "type": "n8n-nodes-base.httpRequest",
    "typeVersion": 4.2,
    "position": [mark_completed_pos[0] - 440, mark_completed_pos[1]]
}

# === НОДА 2: Save Call Summary to Notebook ===
save_summary_code = r"""
// Получаем данные
const notebookId = $('Get Notebook ID').first().json.notebookId;
const leadId = $('Extract Transcript').first().json.leadId || $('Parse Filenames & LEAD_ID').first().json.leadId || 'unknown';
const filename = $('Extract Transcript').first().json.filename || $('Parse Filenames & LEAD_ID').first().json.filename || '';
const dateLabel = new Date().toLocaleDateString('ru-RU', { timeZone: 'Europe/Moscow' });

// Извлекаем текст саммари из ответа GLM
const glmResp = $json;
const msg = glmResp.choices?.[0]?.message || {};
const summaryText = (msg.content || msg.reasoning_content || '').trim();

if (!summaryText || !notebookId) {
  return [{ json: { saved: false, reason: !summaryText ? 'no summary' : 'no notebookId' } }];
}

// Сохраняем саммари как источник в ноутбук
const resp = await $http.request({
  method: 'POST',
  url: 'http://open-notebook:5055/api/sources/json',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    notebooks: [notebookId],
    type: 'text',
    content: summaryText,
    title: 'Саммари созвона ' + dateLabel + (filename ? ' | ' + filename.replace(/\.[^.]+$/, '') : ''),
    embed: true,
    async_processing: false,
  }),
});

const sourceId = resp.id || resp.source_id || '';
return [{ json: { saved: true, sourceId, notebookId, leadId } }];
""".strip()

save_node = {
    "parameters": {"jsCode": save_summary_code},
    "id": "save-call-summary",
    "name": "Save Call Summary to Notebook",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [mark_completed_pos[0] - 220, mark_completed_pos[1]]
}

# Проверяем что нод ещё нет — если есть, обновляем
existing = {n['name']: i for i, n in enumerate(nodes)}

if 'GLM-4 Summarize Call' in existing:
    nodes[existing['GLM-4 Summarize Call']]['parameters'] = glm_node['parameters']
    print('Updated GLM-4 Summarize Call')
else:
    nodes.append(glm_node)
    print('Added GLM-4 Summarize Call')

if 'Save Call Summary to Notebook' in existing:
    nodes[existing['Save Call Summary to Notebook']]['parameters']['jsCode'] = save_summary_code
    print('Updated Save Call Summary to Notebook')
else:
    nodes.append(save_node)
    print('Added Save Call Summary to Notebook')

# === ОБНОВЛЯЕМ CONNECTIONS ===
# Было:   Save Success? (yes=0) → Mark Completed
# Стало:  Save Success? (yes=0) → GLM-4 Summarize Call → Save Call Summary to Notebook → Mark Completed

# Сохраняем старую связь Save Success? yes → Mark Completed
old_yes = connections.get('Save Success?', {}).get('main', [[], []])[0]  # [{"node":"Mark Completed",...}]

# Save Success? (yes) → GLM-4 Summarize Call
connections['Save Success?']['main'][0] = [{"node": "GLM-4 Summarize Call", "type": "main", "index": 0}]

# GLM-4 Summarize Call → Save Call Summary to Notebook
connections['GLM-4 Summarize Call'] = {"main": [[{"node": "Save Call Summary to Notebook", "type": "main", "index": 0}]]}

# Save Call Summary to Notebook → Mark Completed (старая цель)
connections['Save Call Summary to Notebook'] = {"main": [old_yes]}

print('\nNew connections:')
print('  Save Success? (yes) ->', connections['Save Success?']['main'][0])
print('  GLM-4 Summarize Call ->', connections['GLM-4 Summarize Call']['main'][0])
print('  Save Call Summary ->', connections['Save Call Summary to Notebook']['main'][0])

# Сохраняем в PostgreSQL
nodes_json = json.dumps(nodes, ensure_ascii=False).replace("'", "''")
conn_json = json.dumps(connections, ensure_ascii=False).replace("'", "''")
sql = f"UPDATE workflow_entity SET nodes = '{nodes_json}'::json, connections = '{conn_json}'::json, \"updatedAt\" = NOW() WHERE id = '{WF_ID}';".encode('utf-8')

result = subprocess.run(
    ['docker', 'exec', '-i', 'mvp-auto-summary-postgres-1', 'psql', '-U', 'n8n', '-d', 'n8n'],
    input=sql, capture_output=True
)
print('\nDB update exit:', result.returncode)
if result.returncode == 0:
    print('SUCCESS: Workflow 01 updated!')
    print('\nЦепочка теперь:')
    print('  Save Transcript → Save Success? (yes)')
    print('  → GLM-4 Summarize Call (саммари созвона)')
    print('  → Save Call Summary to Notebook')
    print('  → Mark Completed')
else:
    print('ERROR:', result.stderr.decode()[:500])
