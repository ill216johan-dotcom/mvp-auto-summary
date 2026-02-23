#!/usr/bin/env python3
"""
Генератор WF02 (Daily Digest 23:00).
Изменения:
- шлёт дайджест во все чаты из таблицы bot_chats
- промпт читается из таблицы prompts (имя: digest_prompt)
- если промпта в БД нет — использует дефолтный
Запуск: python3 scripts/gen_wf02.py
"""
import json
import os

BOT_TOKEN = "8527521201:AAHpyrPn4cig-zq0Xymt7lZ94qBIEXnYAeQ"
DEFAULT_CHAT_ID = -1003872092456
GLM_KEY = "fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6"
PG_CRED = {"id": "F3beGLVPdqgBpqlv", "name": "PostgreSQL"}
TG_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

DEFAULT_PROMPT = (
    "Ты аналитик отдела кураторов фулфилмент-компании. "
    "Тебе дают транскрипты созвонов кураторов с клиентами за день.\n\n"
    "КУРАТОРЫ ОТДЕЛА (определи кто вёл каждый созвон по тексту):\n"
    "- Евгений, Кристина, Анна, Галина, Дарья, Станислав, Андрей\n\n"
    "Сформируй отчёт СТРОГО по следующему формату:\n\n"
    "📊 Отчёт за [ДАТА]\n\n"
    "По каждому куратору кто вёл созвоны сегодня:\n"
    "👤 [ИМЯ КУРАТОРА]:\n"
    "  • Созвонов: N (LEAD-XXXX, LEAD-YYYY — перечисли все)\n"
    "  • Решённых вопросов: N — кратко что решили\n"
    "  • Открытых вопросов: N — кратко что не решили / требует действий\n\n"
    "Если куратора определить не удалось — пиши «👤 Куратор не определён».\n"
    "Если созвонов за день не было — пиши «Созвонов нет».\n"
    "Максимум 3500 символов. Только факты, без воды."
)

default_prompt_js = json.dumps(DEFAULT_PROMPT)

JS_AGGREGATE = (
    "const items = $input.all();\n"
    "if (items.length === 0) { return [{ json: { hasData: false } }]; }\n"
    "const dateLabel = new Date().toLocaleDateString('ru-RU', { timeZone: 'Europe/Moscow' });\n"
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
    "const leadIds = [...new Set(items.slice(0, sections.length).map(i => i.json.lead_id).filter(v => v))];\n"
    "return [{ json: { hasData: true, dateLabel, combined, rowIds, leadIds, count: sections.length } }];"
)

# Достаём промпт из БД, используем дефолтный если не найден
JS_LOAD_PROMPT = (
    "const rows = $input.all();\n"
    f"const defaultPrompt = {default_prompt_js};\n"
    "const meta = $('Aggregate Transcripts').first().json;\n"
    "const promptRow = rows.find(r => r.json && r.json.prompt_text);\n"
    "const systemPrompt = promptRow ? promptRow.json.prompt_text : defaultPrompt;\n"
    "return [{ json: { ...meta, systemPrompt } }];"
)

JS_BUILD_DIGEST = (
    "const meta = $('Prepare GLM').first().json;\n"
    "const g = $json;\n"
    "const msg = g.choices && g.choices[0] ? g.choices[0].message : {};\n"
    "const content = (msg.content || msg.reasoning_content || '').trim() || 'Сводка не получена.';\n"
    "const leadList = meta.leadIds && meta.leadIds.length > 0 ? meta.leadIds.map(id => 'LEAD-' + id).join(', ') : '—';\n"
    "const header = 'Ежедневный дайджест за ' + meta.dateLabel + '\\nВстреч: ' + meta.count + '\\nКлиенты: ' + leadList;\n"
    "const digest = (header + '\\n\\n' + content).trim();\n"
    "return [{ json: { digest: digest, summaryText: content, rowIds: meta.rowIds } }];"
)

# Разбивает текст на части и размножает по всем чатам из bot_chats
JS_SPLIT_CHATS = (
    "const digest = $('Build Digest').first().json.digest || '';\n"
    "const chats = $input.all().map(i => i.json.chat_id);\n"
    "if (chats.length === 0) chats.push(" + str(DEFAULT_CHAT_ID) + ");\n"
    "const max = 3500;\n"
    "const chunks = [];\n"
    "for (let i = 0; i < digest.length; i += max) chunks.push(digest.slice(i, i + max));\n"
    "const result = [];\n"
    "for (const chatId of chats) {\n"
    "  for (const chunk of chunks) {\n"
    "    result.push({ json: { chatId: chatId, text: chunk } });\n"
    "  }\n"
    "}\n"
    "return result;"
)

JS_COLLAPSE = (
    "const meta = $('Build Digest').first().json;\n"
    "const rowIds = Array.isArray(meta.rowIds) ? meta.rowIds : [];\n"
    "const rowIdsSql = rowIds.length > 0 ? rowIds.join(',') : '-1';\n"
    "const summaryEscaped = (meta.summaryText || '').replace(/'/g, \"''\");\n"
    "return [{ json: { rowIdsSql, summaryEscaped } }];"
)

IF_HAS_DATA = {
    "conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
        "conditions": [{"id": "has-data", "leftValue": "={{ $json.combined }}", "rightValue": "", "operator": {"type": "string", "operation": "notEmpty"}}],
        "combinator": "and"
    }
}

data = {
    "name": "02 \u2014 Daily Digest \u2192 GLM-4 \u2192 Telegram",
    "nodes": [
        {"parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 23 * * *"}]}}, "id": "daily-trigger", "name": "Daily 23:00", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0]},

        {"parameters": {"operation": "executeQuery", "query": "SELECT id, lead_id, transcript_text FROM v_today_completed WHERE summary_sent = false AND transcript_text IS NOT NULL", "options": {}}, "id": "load-today", "name": "Load Today's Transcripts", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": [220, 0], "credentials": {"postgres": PG_CRED}},

        {"parameters": {"mode": "runOnceForAllItems", "jsCode": JS_AGGREGATE}, "id": "aggregate-transcripts", "name": "Aggregate Transcripts", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [440, 0]},

        {"parameters": IF_HAS_DATA, "id": "if-has-data", "name": "Has Data?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [660, 0]},

        # Загружаем промпт из таблицы prompts (имя: digest_prompt)
        {
            "parameters": {
                "operation": "executeQuery",
                "query": (
                    "CREATE TABLE IF NOT EXISTS prompts ("
                    "  name VARCHAR(100) PRIMARY KEY,"
                    "  prompt_text TEXT NOT NULL,"
                    "  last_result TEXT,"
                    "  updated_at TIMESTAMP DEFAULT NOW()"
                    ");"
                    "SELECT prompt_text FROM prompts WHERE name = 'digest_prompt' LIMIT 1;"
                ),
                "options": {}
            },
            "id": "load-prompt",
            "name": "Load Digest Prompt",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [880, -120],
            "credentials": {"postgres": PG_CRED},
            "continueOnFail": True
        },

        # Подготовка GLM — промпт из БД или дефолтный
        {"parameters": {"jsCode": JS_LOAD_PROMPT}, "id": "prepare-glm", "name": "Prepare GLM", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1100, -120]},

        {"parameters": {"method": "POST", "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions", "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify({ model: 'glm-4.7-flash', messages: [{ role: 'system', content: $json.systemPrompt }, { role: 'user', content: $json.combined }], temperature: 0.2, max_tokens: 1500, stream: false, thinking: { type: 'disabled' } }) }}", "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Authorization", "value": f"Bearer {GLM_KEY}"}, {"name": "Content-Type", "value": "application/json"}]}, "options": {"timeout": 180000}}, "id": "glm-summarize", "name": "GLM-4 Summarize", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1320, -120]},

        {"parameters": {"jsCode": JS_BUILD_DIGEST}, "id": "build-digest", "name": "Build Digest", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1540, -120]},

        # Загружаем все chat_id из bot_chats (с fallback на дефолтный)
        {
            "parameters": {
                "operation": "executeQuery",
                "query": (
                    "CREATE TABLE IF NOT EXISTS bot_chats ("
                    "  chat_id BIGINT PRIMARY KEY,"
                    "  added_at TIMESTAMP DEFAULT NOW()"
                    ");"
                    f"INSERT INTO bot_chats (chat_id) VALUES ({DEFAULT_CHAT_ID}) ON CONFLICT DO NOTHING;"
                    "SELECT chat_id FROM bot_chats;"
                ),
                "options": {}
            },
            "id": "load-chats",
            "name": "Load Chat IDs",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [1760, -120],
            "credentials": {"postgres": PG_CRED}
        },

        # Разбиваем дайджест по чатам
        {"parameters": {"jsCode": JS_SPLIT_CHATS}, "id": "split-chats", "name": "Split by Chats", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1980, -120]},

        {"parameters": {"method": "POST", "url": f"{TG_BASE}/sendMessage", "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify({ chat_id: $json.chatId, text: $json.text, disable_web_page_preview: true }) }}", "options": {"timeout": 60000}}, "id": "send-telegram", "name": "Send Telegram", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [2200, -120]},

        {"parameters": {"mode": "runOnceForAllItems", "jsCode": JS_COLLAPSE}, "id": "collapse-chunks", "name": "Collapse Chunks", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [2420, -120]},

        {"parameters": {"operation": "executeQuery", "query": "UPDATE processed_files SET summary_text = '{{ $json.summaryEscaped }}', summary_sent = true WHERE id IN ({{ $json.rowIdsSql }})", "options": {}}, "id": "mark-summary-sent", "name": "Mark Summary Sent", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": [2640, -120], "credentials": {"postgres": PG_CRED}}
    ],
    "connections": {
        "Daily 23:00": {"main": [[{"node": "Load Today's Transcripts", "type": "main", "index": 0}]]},
        "Load Today's Transcripts": {"main": [[{"node": "Aggregate Transcripts", "type": "main", "index": 0}]]},
        "Aggregate Transcripts": {"main": [[{"node": "Has Data?", "type": "main", "index": 0}]]},
        "Has Data?": {"main": [[{"node": "Load Digest Prompt", "type": "main", "index": 0}], []]},
        "Load Digest Prompt": {"main": [[{"node": "Prepare GLM", "type": "main", "index": 0}]]},
        "Prepare GLM": {"main": [[{"node": "GLM-4 Summarize", "type": "main", "index": 0}]]},
        "GLM-4 Summarize": {"main": [[{"node": "Build Digest", "type": "main", "index": 0}]]},
        "Build Digest": {"main": [[{"node": "Load Chat IDs", "type": "main", "index": 0}]]},
        "Load Chat IDs": {"main": [[{"node": "Split by Chats", "type": "main", "index": 0}]]},
        "Split by Chats": {"main": [[{"node": "Send Telegram", "type": "main", "index": 0}]]},
        "Send Telegram": {"main": [[{"node": "Collapse Chunks", "type": "main", "index": 0}]]},
        "Collapse Chunks": {"main": [[{"node": "Mark Summary Sent", "type": "main", "index": 0}]]}
    },
    "settings": {"executionOrder": "v1", "timezone": "Europe/Moscow"},
    "staticData": None,
    "tags": [{"name": "MVP Auto-Summary"}],
    "triggerCount": 1
}

out_path = os.path.join(os.path.dirname(__file__), '..', 'n8n-workflows', '02-daily-digest.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

with open(out_path, encoding='utf-8') as f:
    check = json.load(f)

print(f"OK — {os.path.abspath(out_path)}")
print(f"Нод: {len(check['nodes'])} | Connections: {len(check['connections'])}")
