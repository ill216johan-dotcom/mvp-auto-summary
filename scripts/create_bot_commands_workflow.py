#!/usr/bin/env python3
"""
Создаёт Workflow 04 — Telegram Bot Commands.
Слушает команды /report и /status через webhook.

/report — немедленно запускает логику Workflow 02 (дайджест → Telegram)
/status — отвечает статистикой: сколько файлов обработано, последний созвон
"""
import json, subprocess

BOT_TOKEN = "8527521201:AAHpyrPn4cig-zq0Xymt7lZ94qBIEXnYAeQ"
CHAT_ID = -1003872092456
N8N_HOST = "84.252.100.93"
N8N_PORT = "5678"

# Логика обработки команды /report — повторяет Workflow 02 но без расписания
REPORT_JS_CODE = r"""
const body = $json.body || $json;
const message = body.message || {};
const text = (message.text || '').trim();
const chatId = message.chat?.id || CHAT_ID_PLACEHOLDER;
const fromName = message.from?.first_name || 'Unknown';

// Проверяем что это команда /report
if (!text.startsWith('/report')) {
  return [{ json: { skip: true, reason: 'not /report command' } }];
}

return [{ json: { chatId, fromName, isReport: true } }];
""".replace('CHAT_ID_PLACEHOLDER', str(CHAT_ID))

LOAD_TRANSCRIPTS_QUERY = """
SELECT id, lead_id, transcript_text, filename
FROM processed_files
WHERE status = 'completed'
  AND summary_sent = false
  AND transcript_text IS NOT NULL
ORDER BY created_at DESC
"""

AGGREGATE_JS = r"""
const items = $input.all();
if (items.length === 0) {
  return [{ json: { hasData: false, combined: '', rowIds: [], leadIds: [], count: 0, dateLabel: 'сейчас' } }];
}

const dateLabel = new Date().toLocaleDateString('ru-RU', { timeZone: 'Europe/Moscow' }) + ' (принудительный отчёт)';
const MAX_CHARS = 50000;
const sections = [];
let totalLen = 0;
let truncated = false;

for (const item of items) {
  const leadId = item.json.lead_id || 'unknown';
  const transcript = item.json.transcript_text || '';
  const section = `LEAD-${leadId}:\n${transcript}`;
  if (totalLen + section.length > MAX_CHARS) { truncated = true; break; }
  sections.push(section);
  totalLen += section.length;
}

const combined = sections.join('\n\n---\n\n') + (truncated ? '\n\n[...обрезано...]' : '');
const rowIds = items.slice(0, sections.length).map(i => i.json.id);
const leadIds = [...new Set(items.slice(0, sections.length).map(i => i.json.lead_id).filter(Boolean))];

return [{ json: { hasData: true, dateLabel, combined, rowIds, leadIds, count: sections.length } }];
"""

BUILD_DIGEST_JS = r"""
const meta = $('Aggregate for Report').first().json;
const glmResponse = $json;

if (!meta.hasData) {
  return [{ json: { digest: '📊 Нет новых созвонов для отчёта.', summaryText: '', rowIds: [] } }];
}

const msg = glmResponse.choices?.[0]?.message || {};
const content = (msg.content || msg.reasoning_content || 'Сводка не получена.').trim();

const leadList = meta.leadIds?.map(id => `LEAD-${id}`).join(', ') || '—';
const header = `📊 Промежуточный отчёт за ${meta.dateLabel}\nСозвонов: ${meta.count}\nКлиенты: ${leadList}`;
const digest = `${header}\n\n${content}`.trim();

return [{ json: { digest, summaryText: content, rowIds: meta.rowIds, leadIds: meta.leadIds } }];
"""

NO_DATA_JS = r"""
const chatId = $('Parse Command').first().json.chatId;
return [{ json: { chatId, text: '📊 Нет новых созвонов для отчёта. Все уже отправлены или ещё не обработаны.' } }];
"""

workflow = {
    "name": "04 — Telegram Bot Commands (/report /status)",
    "nodes": [
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
        {
            "parameters": {"jsCode": REPORT_JS_CODE},
            "id": "parse-command",
            "name": "Parse Command",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [220, 0]
        },
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [{"id": "is-report", "leftValue": "={{ $json.isReport }}", "rightValue": True, "operator": {"type": "boolean", "operation": "equals"}}],
                    "combinator": "and"
                }
            },
            "id": "is-report-cmd",
            "name": "Is /report?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [440, 0]
        },
        # Ветка NO DATA — ответить что нет данных
        {
            "parameters": {"jsCode": NO_DATA_JS},
            "id": "no-data-msg",
            "name": "No Data Message",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [440, 240]
        },
        {
            "parameters": {
                "operation": "executeQuery",
                "query": LOAD_TRANSCRIPTS_QUERY,
                "options": {}
            },
            "id": "load-transcripts",
            "name": "Load Unsent Transcripts",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [660, -120],
            "credentials": {"postgres": {"id": "F3beGLVPdqgBpqlv", "name": "PostgreSQL"}}
        },
        {
            "parameters": {"mode": "runOnceForAllItems", "jsCode": AGGREGATE_JS},
            "id": "aggregate-report",
            "name": "Aggregate for Report",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [880, -120]
        },
        {
            "parameters": {
                "conditions": {
                    "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
                    "conditions": [{"id": "has-data", "leftValue": "={{ $json.combined }}", "rightValue": "", "operator": {"type": "string", "operation": "notEmpty"}}],
                    "combinator": "and"
                }
            },
            "id": "has-data-check",
            "name": "Has Data?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [1100, -120]
        },
        {
            "parameters": {
                "method": "POST",
                "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ model: 'glm-4.7-flash', messages: [ { role: 'system', content: 'Ты аналитик отдела кураторов фулфилмент-компании. Тебе дают транскрипты созвонов кураторов с клиентами.\\n\\nКУРАТОРЫ ОТДЕЛА (определи кто вёл каждый созвон по тексту):\\n- Евгений (основной куратор)\\n- Кристина (основной куратор)\\n- Анна (основной куратор)\\n- Галина (куратор-консультант)\\n- Дарья (куратор-консультант)\\n- Станислав (куратор-продакт, руководитель)\\n- Андрей (куратор-продакт, руководитель)\\n\\nСформируй отчёт СТРОГО по формату:\\n\\n📊 Отчёт за [ДАТА]\\n\\n👤 [ИМЯ КУРАТОРА]:\\n  • Созвонов: N (LEAD-XXXX, LEAD-YYYY)\\n  • Решённых вопросов: N — кратко\\n  • Открытых вопросов: N — кратко\\n\\nМаксимум 3500 символов.' }, { role: 'user', content: $json.combined } ], temperature: 0.2, max_tokens: 1500, stream: false, thinking: { type: 'disabled' } }) }}",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": "Bearer fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6"},
                        {"name": "Content-Type", "value": "application/json"}
                    ]
                },
                "options": {"timeout": 180000}
            },
            "id": "glm-report",
            "name": "GLM-4 Build Report",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1320, -240]
        },
        {
            "parameters": {"jsCode": BUILD_DIGEST_JS},
            "id": "build-report",
            "name": "Build Report",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1540, -240]
        },
        {
            "parameters": {
                "jsCode": r"""
const text = $json.digest || '';
const max = 3500;
const chunks = [];
for (let i = 0; i < text.length; i += max) {
  chunks.push(text.slice(i, i + max));
}
const chatId = $('Parse Command').first().json.chatId;
return chunks.map((chunk, index) => ({
  json: {
    chatId,
    text: chunks.length > 1 ? `${chunk}\n\n(часть ${index+1}/${chunks.length})` : chunk,
    rowIds: $json.rowIds,
    leadIds: $json.leadIds
  }
}));"""
            },
            "id": "chunk-report",
            "name": "Chunk Report",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1760, -240]
        },
        {
            "parameters": {
                "method": "POST",
                "url": f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ chat_id: $json.chatId, text: $json.text, disable_web_page_preview: true }) }}",
                "options": {"timeout": 60000}
            },
            "id": "send-report-tg",
            "name": "Send Report to Telegram",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1980, -240]
        },
        {
            "parameters": {
                "mode": "runOnceForAllItems",
                "jsCode": r"""
const meta = $('Build Report').first().json;
const rowIds = Array.isArray(meta.rowIds) ? meta.rowIds : [];
const rowIdsSql = rowIds.length > 0 ? rowIds.join(',') : '-1';
const summaryEscaped = (meta.summaryText || '').replace(/'/g, "''");
return [{ json: { rowIdsSql, summaryEscaped } }];"""
            },
            "id": "collapse-report",
            "name": "Collapse Report Chunks",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [2200, -240]
        },
        {
            "parameters": {
                "operation": "executeQuery",
                "query": "UPDATE processed_files SET summary_text = '{{ $json.summaryEscaped }}', summary_sent = true WHERE id IN ({{ $json.rowIdsSql }})",
                "options": {}
            },
            "id": "mark-sent",
            "name": "Mark Report Sent",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [2420, -240],
            "credentials": {"postgres": {"id": "F3beGLVPdqgBpqlv", "name": "PostgreSQL"}}
        },
        # Respond to webhook (200 OK)
        {
            "parameters": {
                "respondWith": "text",
                "responseBody": "OK",
                "options": {}
            },
            "id": "webhook-response",
            "name": "Respond OK",
            "type": "n8n-nodes-base.respondToWebhook",
            "typeVersion": 1,
            "position": [660, 240]
        }
    ],
    "connections": {
        "Telegram Webhook": {"main": [[{"node": "Parse Command", "type": "main", "index": 0}]]},
        "Parse Command": {"main": [[{"node": "Is /report?", "type": "main", "index": 0}]]},
        "Is /report?": {
            "main": [
                [{"node": "Load Unsent Transcripts", "type": "main", "index": 0}],
                [{"node": "No Data Message", "type": "main", "index": 0}]
            ]
        },
        "No Data Message": {"main": [[{"node": "Respond OK", "type": "main", "index": 0}]]},
        "Load Unsent Transcripts": {"main": [[{"node": "Aggregate for Report", "type": "main", "index": 0}]]},
        "Aggregate for Report": {"main": [[{"node": "Has Data?", "type": "main", "index": 0}]]},
        "Has Data?": {
            "main": [
                [{"node": "GLM-4 Build Report", "type": "main", "index": 0}],
                [{"node": "No Data Message", "type": "main", "index": 0}]
            ]
        },
        "GLM-4 Build Report": {"main": [[{"node": "Build Report", "type": "main", "index": 0}]]},
        "Build Report": {"main": [[{"node": "Chunk Report", "type": "main", "index": 0}]]},
        "Chunk Report": {"main": [[{"node": "Send Report to Telegram", "type": "main", "index": 0}]]},
        "Send Report to Telegram": {"main": [[{"node": "Collapse Report Chunks", "type": "main", "index": 0}]]},
        "Collapse Report Chunks": {"main": [[{"node": "Mark Report Sent", "type": "main", "index": 0}]]},
        "Mark Report Sent": {"main": [[{"node": "Respond OK", "type": "main", "index": 0}]]}
    },
    "settings": {"executionOrder": "v1", "timezone": "Europe/Moscow"},
    "staticData": None,
    "tags": [{"name": "MVP Auto-Summary"}]
}

# Импортируем через n8n API
import urllib.request, urllib.error

# Логин
login_data = json.dumps({"emailOrLdapLoginId": "rod@zevich.ru", "password": "Ill216johan511lol2"}).encode()
req = urllib.request.Request(f"http://{N8N_HOST}:{N8N_PORT}/rest/login",
    data=login_data, headers={"Content-Type": "application/json"}, method="POST")

opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor())
with opener.open(req) as resp:
    login_resp = json.loads(resp.read())
    print("Login:", "OK" if "data" in login_resp else login_resp)

# Создаём workflow
wf_data = json.dumps(workflow).encode('utf-8')
req2 = urllib.request.Request(f"http://{N8N_HOST}:{N8N_PORT}/rest/workflows",
    data=wf_data, headers={"Content-Type": "application/json"}, method="POST")

with opener.open(req2) as resp:
    result = json.loads(resp.read())
    wf_id = result.get("data", {}).get("id", "")
    print(f"Workflow created: {wf_id}")
    print(f"Name: {result.get('data',{}).get('name','?')}")

# Активируем
req3 = urllib.request.Request(f"http://{N8N_HOST}:{N8N_PORT}/rest/workflows/{wf_id}/activate",
    data=b'', headers={"Content-Type": "application/json"}, method="POST")
with opener.open(req3) as resp:
    act = json.loads(resp.read())
    print(f"Active: {act.get('data',{}).get('active','?')}")

print(f"\nWebhook URL: http://{N8N_HOST}:{N8N_PORT}/webhook/tg-bot-commands")
print(f"Workflow ID: {wf_id}")
