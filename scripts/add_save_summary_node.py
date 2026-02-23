#!/usr/bin/env python3
"""
Добавляет ноду Save Summary to Notebooks в Workflow 02.
Цепочка: Build Digest -> Save Summary to Notebooks -> Chunk for Telegram
"""
import json, subprocess

WF_ID = 'Bp0AB2bkAgui9Jxo'

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

# Позиция ноды Build Digest
build_digest_pos = [224, 0]
for n in nodes:
    if n['name'] == 'Build Digest':
        build_digest_pos = n.get('position', [224, 0])
        break

# JS-код новой ноды (через $http.request — встроенный в n8n Code node)
js_code = r"""
// Сохраняем дневное саммари в ноутбук каждого клиента
const digest = $('Build Digest').first().json;
const summaryText = digest.summaryText || '';
const meta = $('Aggregate Transcripts').first().json;
const leadIds = meta.leadIds || [];
const dateLabel = meta.dateLabel || new Date().toLocaleDateString('ru-RU');

if (!summaryText || leadIds.length === 0) {
  return [{ json: { saved: 0, skipped: 'no data' } }];
}

// Получаем все ноутбуки
const notebooksResp = await $http.request({
  method: 'GET',
  url: 'http://open-notebook:5055/api/notebooks',
});
const notebooks = Array.isArray(notebooksResp) ? notebooksResp : [];

let savedCount = 0;
const savedLeads = [];

for (const leadId of leadIds) {
  const notebookName = 'LEAD-' + leadId;

  // Ищем ноутбук — берём самый старый если дубликаты
  const matches = notebooks.filter(nb => nb.name === notebookName);
  let notebookId = null;

  if (matches.length > 0) {
    const oldest = matches.reduce((a, b) =>
      ((a.created || '') < (b.created || '') ? a : b)
    );
    notebookId = oldest.id;
  } else {
    // Создаём ноутбук если не существует
    const created = await $http.request({
      method: 'POST',
      url: 'http://open-notebook:5055/api/notebooks',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name: notebookName, description: 'Client meetings for ' + notebookName }),
    });
    notebookId = created.id;
  }

  if (!notebookId) continue;

  // Сохраняем саммари как источник текста
  await $http.request({
    method: 'POST',
    url: 'http://open-notebook:5055/api/sources/json',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      notebooks: [notebookId],
      type: 'text',
      content: summaryText,
      title: 'Дневное саммари ' + dateLabel,
      embed: true,
      async_processing: false,
    }),
  });

  savedCount++;
  savedLeads.push(notebookName);
}

return [{ json: { saved: savedCount, savedLeads, leadIds } }];
""".strip()

# Новая нода
new_node = {
    "parameters": { "jsCode": js_code },
    "id": "save-summary-notebook",
    "name": "Save Summary to Notebooks",
    "type": "n8n-nodes-base.code",
    "typeVersion": 2,
    "position": [build_digest_pos[0] + 220, build_digest_pos[1]]
}

# Проверяем что ноды ещё нет
existing_names = [n['name'] for n in nodes]
if 'Save Summary to Notebooks' in existing_names:
    # Обновляем существующую
    for n in nodes:
        if n['name'] == 'Save Summary to Notebooks':
            n['parameters']['jsCode'] = js_code
            print('Updated existing node')
else:
    nodes.append(new_node)
    print('Added new node')

# Обновляем connections
# Было:   Build Digest -> Chunk for Telegram
# Стало:  Build Digest -> Save Summary to Notebooks -> Chunk for Telegram
old_next = connections.get('Build Digest', {}).get('main', [[]])[0]  # [{"node":"Chunk for Telegram",...}]
connections['Build Digest']['main'][0] = [{"node": "Save Summary to Notebooks", "type": "main", "index": 0}]
connections['Save Summary to Notebooks'] = {"main": [old_next]}

print('Build Digest now connects to:', connections['Build Digest']['main'][0])
print('Save Summary connects to:', connections['Save Summary to Notebooks']['main'][0])

# Сохраняем в PostgreSQL
nodes_json = json.dumps(nodes, ensure_ascii=False).replace("'", "''")
conn_json = json.dumps(connections, ensure_ascii=False).replace("'", "''")
sql = f"UPDATE workflow_entity SET nodes = '{nodes_json}'::json, connections = '{conn_json}'::json, \"updatedAt\" = NOW() WHERE id = '{WF_ID}';".encode('utf-8')

result = subprocess.run(
    ['docker', 'exec', '-i', 'mvp-auto-summary-postgres-1', 'psql', '-U', 'n8n', '-d', 'n8n'],
    input=sql, capture_output=True
)
print('DB update exit:', result.returncode)
if result.returncode == 0:
    print('SUCCESS: Workflow 02 updated!')
else:
    print('ERROR:', result.stderr.decode()[:500])
