#!/usr/bin/env python3
"""
Генератор WF04 (Telegram Bot /report).
Изменения:
- убран offset (чтобы не застревал на старых сообщениях)
- при /report запоминает chat_id в таблицу bot_chats
- промпт читается из таблицы prompts (имя: report_prompt)
- если промпта в БД нет — использует дефолтный
Запуск: python3 scripts/gen_wf04.py
"""
import json
import os

DEFAULT_PROMPT = (
    "Ты аналитик отдела кураторов фулфилмент-компании. "
    "Тебе дают транскрипты созвонов кураторов с клиентами за сегодняшний день.\n\n"
    "Составь структурированный ОТЧЁТ ПО КУРАТОРАМ:\n\n"
    "Для каждого куратора (Евгений, Кристина, Анна, Галина, Дарья, Станислав, Андрей), "
    "кто упоминается в созвонах:\n\n"
    "👤 [Имя куратора]\n"
    "• Созвонов сегодня: N\n"
    "• Клиенты: LEAD-XXXX, LEAD-YYYY\n"
    "• Решённые вопросы: ...\n"
    "• Нерешённые вопросы / задачи: ...\n"
    "• Договорённости: ...\n\n"
    "Правила:\n"
    "- Включай только кураторов, кто реально упоминается в транскриптах\n"
    "- Пиши только конкретные факты из текста, не придумывай\n"
    "- Формат: Markdown\n"
    "- Если куратора определить невозможно — укажи 'Куратор не определён' и опиши созвон по клиенту"
)

BOT_TOKEN = "8527521201:AAHpyrPn4cig-zq0Xymt7lZ94qBIEXnYAeQ"
CHAT_ID = -1003872092456
GLM_KEY = "fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6"
PG_CRED = {"id": "F3beGLVPdqgBpqlv", "name": "PostgreSQL"}
TG_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

JS_PARSE_COMMAND = (
    "const updates = $input.first().json.result || [];\n"
    f"if (updates.length === 0) {{ return [{{ json: {{ hasCommand: false, chatId: {CHAT_ID} }} }}]; }}\n"
    "const r = updates.find(u => {\n"
    "  const t = (u.message && u.message.text) ? u.message.text.trim() : '';\n"
    "  return t === '/report' || t.startsWith('/report@');\n"
    "});\n"
    f"return [{{ json: {{ hasCommand: !!r, chatId: r ? r.message.chat.id : {CHAT_ID} }} }}];"
)

JS_AGGREGATE = (
    "const items = $input.all();\n"
    "const chatId = $('Parse Command').first().json.chatId;\n"
    "if (items.length === 0 || (items.length === 1 && !items[0].json.id)) {\n"
    "  return [{ json: { hasData: false, combined: '', rowIds: [], count: 0, chatId: chatId } }];\n"
    "}\n"
    "const MAX = 50000;\n"
    "let combined = '';\n"
    "const rowIds = [];\n"
    "const leadIds = new Set();\n"
    "for (const item of items) {\n"
    "  const row = item.json;\n"
    "  if (!row.id) continue;\n"
    "  rowIds.push(row.id);\n"
    "  leadIds.add(row.lead_id || 'UNKNOWN');\n"
    "  const chunk = '[LEAD-' + row.lead_id + ' | ' + row.filename + ']\\n' + row.transcript_text + '\\n\\n';\n"
    "  if (combined.length + chunk.length < MAX) combined += chunk;\n"
    "}\n"
    "return [{ json: { hasData: rowIds.length > 0, combined: combined.trim(), rowIds: rowIds, leadIds: Array.from(leadIds), count: rowIds.length, chatId: chatId } }];"
)

# Достаём промпт из БД, используем дефолтный если не найден
default_prompt_js = json.dumps(DEFAULT_PROMPT)
JS_LOAD_PROMPT = (
    "const rows = $input.all();\n"
    f"const defaultPrompt = {default_prompt_js};\n"
    "const meta = $('Aggregate Transcripts').first().json;\n"
    "const promptRow = rows.find(r => r.json && r.json.prompt_text);\n"
    "const systemPrompt = promptRow ? promptRow.json.prompt_text : defaultPrompt;\n"
    "return [{ json: { ...meta, systemPrompt } }];"
)

JS_BUILD_DIGEST = (
    "const meta = $('Load Report Prompt').first().json;\n"
    "const g = $json;\n"
    "const msg = g.choices && g.choices[0] ? g.choices[0].message : {};\n"
    "const content = (msg.content || msg.reasoning_content || '').trim() || 'Отчёт не получен.';\n"
    "const now = new Date().toLocaleString('ru-RU', { timeZone: 'Europe/Moscow', day: '2-digit', month: '2-digit', year: 'numeric' });\n"
    "const header = '📊 *Отчёт по кураторам* (' + now + ')\\n'"
    " + 'Созвонов: ' + meta.count + ' | Клиенты: ' + meta.leadIds.map(id => 'LEAD-' + id).join(', ') + '\\n\\n';\n"
    "return [{ json: { digest: header + content, rowIds: meta.rowIds, chatId: meta.chatId } }];"
)

JS_CHUNK = (
    "const text = $json.digest || '';\n"
    "const chatId = $json.chatId;\n"
    "const rowIds = $json.rowIds;\n"
    "const max = 3500;\n"
    "const chunks = [];\n"
    "for (let i = 0; i < text.length; i += max) chunks.push(text.slice(i, i + max));\n"
    "return chunks.map((c, i) => ({ json: { text: c, chatId: chatId, rowIds: rowIds, isLast: i === chunks.length - 1 } }));"
)

IF_CONDITION_TRUE = {
    "conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
        "conditions": [{"id": "cond", "leftValue": "={{ String($json.hasCommand) }}", "rightValue": "true", "operator": {"type": "string", "operation": "equals"}}],
        "combinator": "and"
    }
}

IF_HAS_DATA = {
    "conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "loose"},
        "conditions": [{"id": "cond", "leftValue": "={{ String($json.hasData) }}", "rightValue": "true", "operator": {"type": "string", "operation": "equals"}}],
        "combinator": "and"
    }
}

data = {
    "name": "04 \u2014 Telegram Bot Commands (/report)",
    "nodes": [
        {"parameters": {"rule": {"interval": [{"field": "seconds", "secondsInterval": 30}]}}, "id": "poll-trigger", "name": "Poll Every 30s", "type": "n8n-nodes-base.scheduleTrigger", "typeVersion": 1.2, "position": [0, 0]},

        # Получаем обновления БЕЗ offset — Telegram сам помнит что уже отдал
        {"parameters": {"method": "GET", "url": f"{TG_BASE}/getUpdates", "sendQuery": True, "queryParameters": {"parameters": [{"name": "timeout", "value": "5"}, {"name": "allowed_updates", "value": "[\"message\"]"}]}, "options": {"timeout": 10000}}, "id": "get-updates", "name": "Get Updates", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [220, 0], "continueOnFail": True},

        {"parameters": {"jsCode": JS_PARSE_COMMAND}, "id": "parse-command", "name": "Parse Command", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [440, 0]},

        {"parameters": IF_CONDITION_TRUE, "id": "is-report", "name": "Is /report?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [660, 0]},

        # Запоминаем chat_id в таблицу bot_chats (CREATE если нет + INSERT OR IGNORE)
        {
            "parameters": {
                "operation": "executeQuery",
                "query": (
                    "CREATE TABLE IF NOT EXISTS bot_chats ("
                    "  chat_id BIGINT PRIMARY KEY,"
                    "  added_at TIMESTAMP DEFAULT NOW()"
                    ");"
                    "INSERT INTO bot_chats (chat_id) VALUES ($1) ON CONFLICT DO NOTHING;"
                ),
                "options": {"queryReplacement": "={{ $json.chatId }}"}
            },
            "id": "save-chat-id",
            "name": "Save Chat ID",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [880, -200],
            "credentials": {"postgres": PG_CRED}
        },

        {"parameters": {"operation": "executeQuery", "query": "SELECT id, filename, lead_id, transcript_text, created_at FROM processed_files WHERE status = 'completed' AND DATE(created_at) = CURRENT_DATE AND transcript_text IS NOT NULL ORDER BY created_at ASC", "options": {}}, "id": "load-transcripts", "name": "Load Today Transcripts", "type": "n8n-nodes-base.postgres", "typeVersion": 2.5, "position": [1100, -200], "credentials": {"postgres": PG_CRED}},

        {"parameters": {"jsCode": JS_AGGREGATE}, "id": "aggregate", "name": "Aggregate Transcripts", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1320, -200]},

        {"parameters": IF_HAS_DATA, "id": "has-data", "name": "Has Data?", "type": "n8n-nodes-base.if", "typeVersion": 2, "position": [1540, -200]},

        {"parameters": {"method": "POST", "url": f"{TG_BASE}/sendMessage", "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify({ chat_id: $('Parse Command').first().json.chatId, text: '\u0421\u0435\u0433\u043e\u0434\u043d\u044f \u0441\u043e\u0437\u0432\u043e\u043d\u043e\u0432 \u0435\u0449\u0451 \u043d\u0435 \u0431\u044b\u043b\u043e.' }) }}", "options": {}}, "id": "send-no-data", "name": "Send No Data", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [1760, 0]},

        # Загружаем промпт из таблицы prompts (имя: report_prompt)
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
                    "SELECT prompt_text FROM prompts WHERE name = 'report_prompt' LIMIT 1;"
                ),
                "options": {}
            },
            "id": "load-prompt",
            "name": "Load Report Prompt",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [1760, -300],
            "credentials": {"postgres": PG_CRED},
            "continueOnFail": True
        },

        # Подготовка запроса к GLM — промпт из БД или дефолтный
        {"parameters": {"jsCode": JS_LOAD_PROMPT}, "id": "prepare-glm", "name": "Prepare GLM Request", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [1980, -300]},

        {"parameters": {"method": "POST", "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions", "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify({ model: 'glm-4.7-flash', messages: [{ role: 'system', content: $json.systemPrompt }, { role: 'user', content: $json.combined }], temperature: 0.2, max_tokens: 2000, stream: false, thinking: { type: 'disabled' } }) }}", "sendHeaders": True, "headerParameters": {"parameters": [{"name": "Authorization", "value": f"Bearer {GLM_KEY}"}]}, "options": {"timeout": 60000}}, "id": "glm-summarize", "name": "GLM-4 Build Report", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [2200, -300], "continueOnFail": True},

        {"parameters": {"jsCode": JS_BUILD_DIGEST}, "id": "build-digest", "name": "Build Digest", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [2420, -300]},

        {"parameters": {"jsCode": JS_CHUNK}, "id": "chunk-telegram", "name": "Chunk for Telegram", "type": "n8n-nodes-base.code", "typeVersion": 2, "position": [2640, -300]},

        {"parameters": {"method": "POST", "url": f"{TG_BASE}/sendMessage", "sendBody": True, "specifyBody": "json", "jsonBody": "={{ JSON.stringify({ chat_id: $json.chatId, text: $json.text, parse_mode: 'Markdown' }) }}", "options": {}}, "id": "send-telegram", "name": "Send to Telegram", "type": "n8n-nodes-base.httpRequest", "typeVersion": 4.2, "position": [2860, -300], "continueOnFail": True}
    ],
    "connections": {
        "Poll Every 30s": {"main": [[{"node": "Get Updates", "type": "main", "index": 0}]]},
        "Get Updates": {"main": [[{"node": "Parse Command", "type": "main", "index": 0}]]},
        "Parse Command": {"main": [[{"node": "Is /report?", "type": "main", "index": 0}]]},
        "Is /report?": {"main": [[{"node": "Save Chat ID", "type": "main", "index": 0}], []]},
        "Save Chat ID": {"main": [[{"node": "Load Today Transcripts", "type": "main", "index": 0}]]},
        "Load Today Transcripts": {"main": [[{"node": "Aggregate Transcripts", "type": "main", "index": 0}]]},
        "Aggregate Transcripts": {"main": [[{"node": "Has Data?", "type": "main", "index": 0}]]},
        "Has Data?": {"main": [[{"node": "Load Report Prompt", "type": "main", "index": 0}], [{"node": "Send No Data", "type": "main", "index": 0}]]},
        "Load Report Prompt": {"main": [[{"node": "Prepare GLM Request", "type": "main", "index": 0}]]},
        "Prepare GLM Request": {"main": [[{"node": "GLM-4 Build Report", "type": "main", "index": 0}]]},
        "GLM-4 Build Report": {"main": [[{"node": "Build Digest", "type": "main", "index": 0}]]},
        "Build Digest": {"main": [[{"node": "Chunk for Telegram", "type": "main", "index": 0}]]},
        "Chunk for Telegram": {"main": [[{"node": "Send to Telegram", "type": "main", "index": 0}]]}
    },
    "settings": {"executionOrder": "v1", "timezone": "Europe/Moscow"},
    "staticData": None,
    "tags": [{"name": "MVP Auto-Summary"}]
}

out_path = os.path.join(os.path.dirname(__file__), '..', 'n8n-workflows', '04-telegram-bot.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

with open(out_path, encoding='utf-8') as f:
    check = json.load(f)

print(f"OK — {os.path.abspath(out_path)}")
print(f"Нод: {len(check['nodes'])} | Connections: {len(check['connections'])}")
