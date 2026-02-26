#!/usr/bin/env python3
"""
Создаёт Workflow 04 (Bot Commands) напрямую в PostgreSQL.
"""
import json, subprocess, uuid

BOT_TOKEN = "8527521201:AAHpyrPn4cig-zq0Xymt7lZ94qBIEXnYAeQ"
CHAT_ID = -1003872092456
GLM_KEY = "fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6"
PG_CRED_ID = "F3beGLVPdqgBpqlv"

def psql_run(sql_bytes):
    return subprocess.run(
        ['docker','exec','-i','mvp-auto-summary-postgres-1','psql','-U','n8n','-d','n8n'],
        input=sql_bytes, capture_output=True
    )

def psql_query(query):
    r = subprocess.run(
        ['docker','exec','mvp-auto-summary-postgres-1','psql','-U','n8n','-d','n8n','-t','-A','-c', query],
        capture_output=True, text=True
    )
    return r.stdout.strip()

# ── NODES ──────────────────────────────────────────────────────────────────────

nodes = [
    # 1. Webhook trigger
    {
        "parameters": {
            "httpMethod": "POST",
            "path": "tg-bot-commands",
            "responseMode": "responseNode",
            "options": {}
        },
        "id": "webhook-trigger",
        "name": "Telegram Webhook",
        "type": "n8n-nodes-base.webhook",
        "typeVersion": 2,
        "position": [0, 0],
        "webhookId": "tg-bot-commands"
    },

    # 2. Parse command
    {
        "parameters": {
            "jsCode": (
                "const body = $json.body || $json;\n"
                "const message = body.message || {};\n"
                "const text = (message.text || '').trim();\n"
                "const chatId = message.chat && message.chat.id ? message.chat.id : " + str(CHAT_ID) + ";\n"
                "const fromName = message.from && message.from.first_name ? message.from.first_name : 'Unknown';\n"
                "const isReport = text.startsWith('/report');\n"
                "const isStatus = text.startsWith('/status');\n"
                "return [{ json: { chatId, fromName, isReport, isStatus, text } }];\n"
            )
        },
        "id": "parse-command",
        "name": "Parse Command",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [220, 0]
    },

    # 3. IF is /report
    {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [{"id": "c1", "leftValue": "={{ $json.isReport }}", "rightValue": True, "operator": {"type": "boolean", "operation": "equals"}}],
                "combinator": "and"
            }
        },
        "id": "if-report",
        "name": "Is /report?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [440, 0]
    },

    # 4. Respond 200 to Telegram (always immediately)
    {
        "parameters": {"respondWith": "text", "responseBody": "OK", "options": {}},
        "id": "respond-ok",
        "name": "Respond OK",
        "type": "n8n-nodes-base.respondToWebhook",
        "typeVersion": 1,
        "position": [660, 200]
    },

    # 5. Load unsent transcripts
    {
        "parameters": {
            "operation": "executeQuery",
            "query": "SELECT id, lead_id, transcript_text, filename FROM processed_files WHERE status = 'completed' AND summary_sent = false AND transcript_text IS NOT NULL ORDER BY created_at DESC",
            "options": {}
        },
        "id": "load-transcripts",
        "name": "Load Unsent Transcripts",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [660, -200],
        "credentials": {"postgres": {"id": PG_CRED_ID, "name": "PostgreSQL"}}
    },

    # 6. Aggregate
    {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": (
                "const items = $input.all();\n"
                "if (items.length === 0) {\n"
                "  return [{ json: { hasData: false, combined: '', rowIds: [], leadIds: [], count: 0, dateLabel: 'сейчас' } }];\n"
                "}\n"
                "const dateLabel = new Date().toLocaleDateString('ru-RU', { timeZone: 'Europe/Moscow' }) + ' (принудительный)';\n"
                "const MAX_CHARS = 50000;\n"
                "const sections = [];\n"
                "let totalLen = 0;\n"
                "for (const item of items) {\n"
                "  const leadId = item.json.lead_id || 'unknown';\n"
                "  const transcript = item.json.transcript_text || '';\n"
                "  const section = 'LEAD-' + leadId + ':\\n' + transcript;\n"
                "  if (totalLen + section.length > MAX_CHARS) break;\n"
                "  sections.push(section);\n"
                "  totalLen += section.length;\n"
                "}\n"
                "const combined = sections.join('\\n\\n---\\n\\n');\n"
                "const rowIds = items.slice(0, sections.length).map(i => i.json.id);\n"
                "const leadIds = [...new Set(items.slice(0, sections.length).map(i => i.json.lead_id).filter(Boolean))];\n"
                "return [{ json: { hasData: true, dateLabel, combined, rowIds, leadIds, count: sections.length } }];\n"
            )
        },
        "id": "aggregate",
        "name": "Aggregate Transcripts",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [880, -200]
    },

    # 7. IF has data
    {
        "parameters": {
            "conditions": {
                "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                "conditions": [{"id": "c2", "leftValue": "={{ $json.combined }}", "rightValue": "", "operator": {"type": "string", "operation": "notEmpty"}}],
                "combinator": "and"
            }
        },
        "id": "if-has-data",
        "name": "Has Data?",
        "type": "n8n-nodes-base.if",
        "typeVersion": 2,
        "position": [1100, -200]
    },

    # 8. Send "no data" message
    {
        "parameters": {
            "method": "POST",
            "url": "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ chat_id: $('Parse Command').first().json.chatId, text: '📊 Нет новых созвонов для отчёта. Все уже были отправлены или ещё не обработаны.' }) }}",
            "options": {"timeout": 30000}
        },
        "id": "send-no-data",
        "name": "Send No Data",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1100, 0]
    },

    # 9. GLM summarize
    {
        "parameters": {
            "method": "POST",
            "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ model: 'glm-4.7-flash', messages: [ { role: 'system', content: 'Ты аналитик отдела кураторов фулфилмент-компании. Тебе дают транскрипты созвонов.\\n\\nКУРАТОРЫ: Евгений, Кристина, Анна (основные), Галина, Дарья (консультанты), Станислав, Андрей (руководители).\\n\\nФОРМАТ ОТЧЁТА:\\n\\n📊 Отчёт за [ДАТА]\\n\\n👤 [КУРАТОР]:\\n  • Созвонов: N (LEAD-XXXX)\\n  • Решённых вопросов: N — кратко\\n  • Открытых вопросов: N — кратко\\n\\nМаксимум 3500 символов.' }, { role: 'user', content: $json.combined } ], temperature: 0.2, max_tokens: 1500, stream: false, thinking: { type: 'disabled' } }) }}",
            "sendHeaders": True,
            "headerParameters": {
                "parameters": [
                    {"name": "Authorization", "value": "Bearer " + GLM_KEY},
                    {"name": "Content-Type", "value": "application/json"}
                ]
            },
            "options": {"timeout": 180000}
        },
        "id": "glm-summarize",
        "name": "GLM-4 Summarize",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1320, -320]
    },

    # 10. Build digest
    {
        "parameters": {
            "jsCode": (
                "const meta = $('Aggregate Transcripts').first().json;\n"
                "const glmResp = $json;\n"
                "const msg = glmResp.choices && glmResp.choices[0] ? glmResp.choices[0].message : {};\n"
                "const content = (msg.content || msg.reasoning_content || 'Сводка не получена.').trim();\n"
                "const leadList = Array.isArray(meta.leadIds) ? meta.leadIds.map(id => 'LEAD-' + id).join(', ') : '—';\n"
                "const header = '📊 Промежуточный отчёт за ' + meta.dateLabel + '\\nСозвонов: ' + meta.count + '\\nКлиенты: ' + leadList;\n"
                "const digest = (header + '\\n\\n' + content).trim();\n"
                "return [{ json: { digest, summaryText: content, rowIds: meta.rowIds, leadIds: meta.leadIds } }];\n"
            )
        },
        "id": "build-digest",
        "name": "Build Digest",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1540, -320]
    },

    # 11. Chunk
    {
        "parameters": {
            "jsCode": (
                "const text = $json.digest || '';\n"
                "const max = 3500;\n"
                "const chunks = [];\n"
                "for (let i = 0; i < text.length; i += max) chunks.push(text.slice(i, i + max));\n"
                "const chatId = $('Parse Command').first().json.chatId;\n"
                "return chunks.map((chunk, idx) => ({ json: {\n"
                "  chatId,\n"
                "  text: chunks.length > 1 ? chunk + '\\n\\n(часть ' + (idx+1) + '/' + chunks.length + ')' : chunk,\n"
                "  rowIds: $json.rowIds,\n"
                "  leadIds: $json.leadIds\n"
                "} }));\n"
            )
        },
        "id": "chunk",
        "name": "Chunk for Telegram",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [1760, -320]
    },

    # 12. Send to Telegram
    {
        "parameters": {
            "method": "POST",
            "url": "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage",
            "sendBody": True,
            "specifyBody": "json",
            "jsonBody": "={{ JSON.stringify({ chat_id: $json.chatId, text: $json.text, disable_web_page_preview: true }) }}",
            "options": {"timeout": 60000}
        },
        "id": "send-tg",
        "name": "Send to Telegram",
        "type": "n8n-nodes-base.httpRequest",
        "typeVersion": 4.2,
        "position": [1980, -320]
    },

    # 13. Collapse chunks
    {
        "parameters": {
            "mode": "runOnceForAllItems",
            "jsCode": (
                "const meta = $('Build Digest').first().json;\n"
                "const rowIds = Array.isArray(meta.rowIds) ? meta.rowIds : [];\n"
                "const rowIdsSql = rowIds.length > 0 ? rowIds.join(',') : '-1';\n"
                "const summaryEscaped = (meta.summaryText || '').replace(/'/g, \"''\");\n"
                "return [{ json: { rowIdsSql, summaryEscaped } }];\n"
            )
        },
        "id": "collapse",
        "name": "Collapse Chunks",
        "type": "n8n-nodes-base.code",
        "typeVersion": 2,
        "position": [2200, -320]
    },

    # 14. Mark sent
    {
        "parameters": {
            "operation": "executeQuery",
            "query": "UPDATE processed_files SET summary_text = '{{ $json.summaryEscaped }}', summary_sent = true WHERE id IN ({{ $json.rowIdsSql }})",
            "options": {}
        },
        "id": "mark-sent",
        "name": "Mark Summary Sent",
        "type": "n8n-nodes-base.postgres",
        "typeVersion": 2.5,
        "position": [2420, -320],
        "credentials": {"postgres": {"id": PG_CRED_ID, "name": "PostgreSQL"}}
    },
]

connections = {
    "Telegram Webhook": {"main": [[{"node": "Parse Command", "type": "main", "index": 0}]]},
    "Parse Command": {"main": [[{"node": "Is /report?", "type": "main", "index": 0}]]},
    "Is /report?": {
        "main": [
            [{"node": "Load Unsent Transcripts", "type": "main", "index": 0}],
            [{"node": "Respond OK", "type": "main", "index": 0}]
        ]
    },
    "Load Unsent Transcripts": {"main": [[{"node": "Aggregate Transcripts", "type": "main", "index": 0}]]},
    "Aggregate Transcripts": {"main": [[{"node": "Has Data?", "type": "main", "index": 0}]]},
    "Has Data?": {
        "main": [
            [{"node": "GLM-4 Summarize", "type": "main", "index": 0}],
            [{"node": "Send No Data", "type": "main", "index": 0}]
        ]
    },
    "GLM-4 Summarize": {"main": [[{"node": "Build Digest", "type": "main", "index": 0}]]},
    "Build Digest": {"main": [[{"node": "Chunk for Telegram", "type": "main", "index": 0}]]},
    "Chunk for Telegram": {"main": [[{"node": "Send to Telegram", "type": "main", "index": 0}]]},
    "Send to Telegram": {"main": [[{"node": "Collapse Chunks", "type": "main", "index": 0}]]},
    "Collapse Chunks": {"main": [[{"node": "Mark Summary Sent", "type": "main", "index": 0}]]},
    "Mark Summary Sent": {"main": [[{"node": "Respond OK", "type": "main", "index": 0}]]},
    "Send No Data": {"main": [[{"node": "Respond OK", "type": "main", "index": 0}]]}
}

wf_id = "wf04-bot-commands-001"

nodes_json = json.dumps(nodes, ensure_ascii=False).replace("'", "''")
conn_json = json.dumps(connections, ensure_ascii=False).replace("'", "''")

sql = f"""
INSERT INTO workflow_entity (id, name, active, nodes, connections, settings, "staticData", "triggerCount", "versionId", "updatedAt", "createdAt")
VALUES (
    '{wf_id}',
    '04 — Telegram Bot Commands (/report /status)',
    true,
    '{nodes_json}'::json,
    '{conn_json}'::json,
    '{{"executionOrder": "v1", "timezone": "Europe/Moscow"}}'::json,
    null,
    1,
    '{str(uuid.uuid4())}',
    NOW(),
    NOW()
)
ON CONFLICT (id) DO UPDATE SET
    nodes = EXCLUDED.nodes,
    connections = EXCLUDED.connections,
    active = true,
    "updatedAt" = NOW();
""".encode('utf-8')

result = psql_run(sql)
print("Insert exit:", result.returncode)
if result.returncode == 0:
    print("SUCCESS: Workflow 04 created!")
    print(f"Workflow ID: {wf_id}")
    print(f"\nWebhook URL: http://84.252.100.93:5678/webhook/tg-bot-commands")
else:
    print("ERROR:", result.stderr.decode()[:500])
    print("STDOUT:", result.stdout.decode()[:500])
