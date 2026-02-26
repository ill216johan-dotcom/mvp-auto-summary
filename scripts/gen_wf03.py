#!/usr/bin/env python3
"""
Генератор WF03 (Individual Summaries: Calls + Chats, 22:00).
Изменения относительно оригинала:
- промпт для созвонов читается из таблицы prompts (имя: call_summary_prompt)
- промпт для чатов читается из таблицы prompts (имя: chat_summary_prompt)
- если промпта нет в БД — используется дефолтный
Запуск: python scripts/gen_wf03.py
"""
import json
import os

GLM_KEY = "fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6"
PG_CRED = {"id": "F3beGLVPdqgBpqlv", "name": "PostgreSQL"}

# ─── Дефолтные промпты (точная копия того что было захардкожено) ───────────────

DEFAULT_CALL_PROMPT = (
    "Ты бизнес-аналитик. Проанализируй транскрипцию созвона с клиентом.\n\n"
    "ВЫХОДНОЙ ФОРМАТ (строго):\n\n"
    "## Краткое резюме\n"
    "[2-3 предложения о главном]\n\n"
    "## Участники\n"
    "- Менеджер: [имя]\n"
    "- Клиент: [компания/имя]\n\n"
    "## Ключевые договорённости\n"
    "- [пункт]\n\n"
    "## Action Items\n"
    "- [ ] [задача] — [ответственный] — [дедлайн]\n\n"
    "## Риски и блокеры\n"
    "- [риск или Нет]\n\n"
    "## Следующие шаги\n"
    "- [что делать дальше]\n\n"
    "## Важные цитаты клиента\n"
    "> [цитата или нет цитат]"
)

DEFAULT_CHAT_PROMPT = (
    "Ты бизнес-аналитик. Проанализируй историю переписки с клиентом в Telegram.\n\n"
    "ВЫХОДНОЙ ФОРМАТ (строго):\n\n"
    "## Период общения\n"
    "[даты первой и последней переписки]\n\n"
    "## Основные темы\n"
    "- [тема]\n\n"
    "## Ключевые договорённости\n"
    "- [пункт или Не зафиксировано]\n\n"
    "## Open questions (вопросы без ответа)\n"
    "- [вопрос или Нет]\n\n"
    "## Тон клиента\n"
    "[позитивный/нейтральный/негативный + причины]\n\n"
    "## Следующие шаги\n"
    "- [что нужно сделать]"
)

default_call_prompt_js = json.dumps(DEFAULT_CALL_PROMPT)
default_chat_prompt_js = json.dumps(DEFAULT_CHAT_PROMPT)

# ─── JavaScript ноды ────────────────────────────────────────────────────────────

JS_PREPARE_CALLS = (
    "const calls = $input.all();\n"
    "const results = [];\n"
    "for (const call of calls) {\n"
    "  const { id, filename, lead_id, transcript_text, call_date } = call.json;\n"
    "  const timeParts = filename.match(/_(\\d{2}-\\d{2})\\./)?.[1] || '00-00';\n"
    "  const truncated = transcript_text.length > 80000 ? transcript_text.slice(0, 80000) + '\\n...[обрезано]' : transcript_text;\n"
    "  results.push({ json: { type: 'call', lead_id: String(lead_id), source_id: id, filename, time_str: timeParts, content: truncated, call_date } });\n"
    "}\n"
    "return results.length > 0 ? results : [{ json: { type: 'call', lead_id: null, empty: true } }];"
)

JS_PREPARE_CHATS = (
    "const chats = $input.all();\n"
    "const results = [];\n"
    "for (const chat of chats) {\n"
    "  const { lead_id, chat_title, chat_text, msg_count } = chat.json;\n"
    "  const truncated = (chat_text || '').length > 50000 ? chat_text.slice(0, 50000) + '\\n...[обрезано]' : (chat_text || '');\n"
    "  results.push({ json: { type: 'chat', lead_id: String(lead_id), chat_title, msg_count, content: truncated } });\n"
    "}\n"
    "return results.length > 0 ? results : [{ json: { type: 'chat', lead_id: null, empty: true } }];"
)

# Подставляет промпт из БД или дефолтный, прокидывает content дальше
JS_INJECT_CALL_PROMPT = (
    "const rows = $input.all();\n"
    f"const defaultPrompt = {default_call_prompt_js};\n"
    "const callItem = $('Prepare Calls').item.json;\n"
    "const promptRow = rows.find(r => r.json && r.json.prompt_text);\n"
    "const systemPrompt = promptRow ? promptRow.json.prompt_text : defaultPrompt;\n"
    "return [{ json: { ...callItem, systemPrompt } }];"
)

JS_INJECT_CHAT_PROMPT = (
    "const rows = $input.all();\n"
    f"const defaultPrompt = {default_chat_prompt_js};\n"
    "const chatItem = $('Prepare Chats').item.json;\n"
    "const promptRow = rows.find(r => r.json && r.json.prompt_text);\n"
    "const systemPrompt = promptRow ? promptRow.json.prompt_text : defaultPrompt;\n"
    "return [{ json: { ...chatItem, systemPrompt } }];"
)

JS_EXTRACT_CALL_SUMMARY = (
    "const glmResponse = $json;\n"
    "const prevItem = $('Inject Call Prompt').item.json;\n"
    "const msg = glmResponse.choices?.[0]?.message || {};\n"
    "const rawContent = (msg.content || '').trim();\n"
    "const rawReasoning = (msg.reasoning_content || '').trim();\n"
    "const summaryText = rawContent || rawReasoning || 'Summary не получено.';\n"
    "const dateStr = new Date().toISOString().slice(0, 10);\n"
    "const filename = `LEAD-${prevItem.lead_id}_call_${prevItem.time_str}_${dateStr}.md`;\n"
    "return { json: { type: 'call', lead_id: prevItem.lead_id, source_id: prevItem.source_id, summary_text: summaryText, filename, summary_date: dateStr } };"
)

JS_EXTRACT_CHAT_SUMMARY = (
    "const glmResponse = $json;\n"
    "const prevItem = $('Inject Chat Prompt').item.json;\n"
    "const msg = glmResponse.choices?.[0]?.message || {};\n"
    "const rawContent = (msg.content || '').trim();\n"
    "const rawReasoning = (msg.reasoning_content || '').trim();\n"
    "const summaryText = rawContent || rawReasoning || 'Summary не получено.';\n"
    "const dateStr = new Date().toISOString().slice(0, 10);\n"
    "const filename = `LEAD-${prevItem.lead_id}_chat_${dateStr}.md`;\n"
    "return { json: { type: 'chat', lead_id: prevItem.lead_id, source_id: 0, summary_text: summaryText, filename, summary_date: dateStr } };"
)

IF_EMPTY = lambda name: {
    "conditions": {
        "options": {"caseSensitive": True, "leftValue": "", "typeValidation": "strict"},
        "conditions": [{"id": "not-empty", "leftValue": "={{ $json.empty }}", "rightValue": True,
                        "operator": {"type": "boolean", "operation": "equal"}}],
        "combinator": "any"
    },
    "options": {}
}

# ─── Структура workflow ─────────────────────────────────────────────────────────

data = {
    "name": "03 \u2014 Individual Summaries (Calls + Chats)",
    "nodes": [
        # Триггер 22:00
        {
            "parameters": {"rule": {"interval": [{"field": "cronExpression", "expression": "0 22 * * *"}]}},
            "id": "daily-trigger",
            "name": "Daily 22:00",
            "type": "n8n-nodes-base.scheduleTrigger",
            "typeVersion": 1.2,
            "position": [-880, 208]
        },

        # Загрузка созвонов
        {
            "parameters": {
                "operation": "executeQuery",
                "query": (
                    "SELECT id, filename, lead_id, transcript_text, created_at::date as call_date "
                    "FROM processed_files "
                    "WHERE status = 'completed' AND DATE(created_at) = CURRENT_DATE "
                    "AND transcript_text IS NOT NULL ORDER BY lead_id, created_at"
                ),
                "options": {}
            },
            "id": "load-calls",
            "name": "Load Today's Calls",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [-656, 112],
            "credentials": {"postgres": PG_CRED}
        },

        # Загрузка чатов
        {
            "parameters": {
                "operation": "executeQuery",
                "query": (
                    "SELECT lead_id, chat_title, "
                    "STRING_AGG('[' || TO_CHAR(message_date, 'HH24:MI') || '] ' || sender || ': ' || message_text, E'\\n' ORDER BY message_date) as chat_text, "
                    "COUNT(*) as msg_count, MIN(message_date) as first_msg, MAX(message_date) as last_msg "
                    "FROM chat_messages WHERE DATE(message_date) = CURRENT_DATE "
                    "GROUP BY lead_id, chat_title ORDER BY lead_id"
                ),
                "options": {}
            },
            "id": "load-chats",
            "name": "Load Today's Chats",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [-656, 304],
            "credentials": {"postgres": PG_CRED}
        },

        # Подготовка созвонов
        {
            "parameters": {"mode": "runOnceForEachItem", "jsCode": JS_PREPARE_CALLS},
            "id": "prepare-calls",
            "name": "Prepare Calls",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-448, 112]
        },

        # Подготовка чатов
        {
            "parameters": {"mode": "runOnceForEachItem", "jsCode": JS_PREPARE_CHATS},
            "id": "prepare-chats",
            "name": "Prepare Chats",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [-448, 304]
        },

        # Проверка наличия созвонов
        {
            "parameters": IF_EMPTY("call"),
            "id": "has-calls",
            "name": "Has Calls?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [-224, 112]
        },

        # Проверка наличия чатов
        {
            "parameters": IF_EMPTY("chat"),
            "id": "has-chats",
            "name": "Has Chats?",
            "type": "n8n-nodes-base.if",
            "typeVersion": 2,
            "position": [-224, 304]
        },

        # Загружаем промпт для созвона из БД
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
                    "SELECT prompt_text FROM prompts WHERE name = 'call_summary_prompt' LIMIT 1;"
                ),
                "options": {}
            },
            "id": "load-call-prompt",
            "name": "Load Call Prompt",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [-56, 0],
            "credentials": {"postgres": PG_CRED},
            "continueOnFail": True
        },

        # Загружаем промпт для чата из БД
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
                    "SELECT prompt_text FROM prompts WHERE name = 'chat_summary_prompt' LIMIT 1;"
                ),
                "options": {}
            },
            "id": "load-chat-prompt",
            "name": "Load Chat Prompt",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [-56, 208],
            "credentials": {"postgres": PG_CRED},
            "continueOnFail": True
        },

        # Подставляем промпт созвона (из БД или дефолтный)
        {
            "parameters": {"mode": "runOnceForEachItem", "jsCode": JS_INJECT_CALL_PROMPT},
            "id": "inject-call-prompt",
            "name": "Inject Call Prompt",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [164, 0]
        },

        # Подставляем промпт чата (из БД или дефолтный)
        {
            "parameters": {"mode": "runOnceForEachItem", "jsCode": JS_INJECT_CHAT_PROMPT},
            "id": "inject-chat-prompt",
            "name": "Inject Chat Prompt",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [164, 208]
        },

        # GLM: саммари созвона
        {
            "parameters": {
                "method": "POST",
                "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                "sendHeaders": True,
                "headerParameters": {"parameters": [
                    {"name": "Authorization", "value": f"Bearer {GLM_KEY}"},
                    {"name": "Content-Type", "value": "application/json"}
                ]},
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ model: 'glm-4.7-flash', messages: [{ role: 'system', content: $json.systemPrompt }, { role: 'user', content: $json.content }], temperature: 0.2, max_tokens: 1500, stream: false, thinking: { type: 'disabled' } }) }}",
                "options": {"timeout": 120000}
            },
            "id": "glm-call",
            "name": "GLM-4: Summarize Call",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [384, 0]
        },

        # GLM: саммари чата
        {
            "parameters": {
                "method": "POST",
                "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                "sendHeaders": True,
                "headerParameters": {"parameters": [
                    {"name": "Authorization", "value": f"Bearer {GLM_KEY}"},
                    {"name": "Content-Type", "value": "application/json"}
                ]},
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ model: 'glm-4.7-flash', messages: [{ role: 'system', content: $json.systemPrompt }, { role: 'user', content: $json.content }], temperature: 0.2, max_tokens: 1200, stream: false, thinking: { type: 'disabled' } }) }}",
                "options": {"timeout": 120000}
            },
            "id": "glm-chat",
            "name": "GLM-4: Summarize Chat",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [384, 208]
        },

        # Извлечение саммари созвона
        {
            "parameters": {"mode": "runOnceForEachItem", "jsCode": JS_EXTRACT_CALL_SUMMARY},
            "id": "extract-call-summary",
            "name": "Extract Call Summary",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [608, 0]
        },

        # Извлечение саммари чата
        {
            "parameters": {"mode": "runOnceForEachItem", "jsCode": JS_EXTRACT_CHAT_SUMMARY},
            "id": "extract-chat-summary",
            "name": "Extract Chat Summary",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [608, 208]
        },

        # Сохранение саммари созвона в БД
        {
            "parameters": {
                "operation": "executeQuery",
                "query": "INSERT INTO client_summaries (lead_id, source_type, source_id, summary_text, summary_date) VALUES ($1, $2, $3, $4, $5::date)",
                "options": {"queryReplacement": "={{ $json.lead_id }}||={{ $json.type }}||={{ $json.source_id }}||={{ $json.summary_text.replace(/'/g, \"''\") }}||={{ $json.summary_date }}"}
            },
            "id": "save-call-summary",
            "name": "Save Call Summary to DB",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [832, 0],
            "credentials": {"postgres": PG_CRED}
        },

        # Сохранение саммари чата в БД
        {
            "parameters": {
                "operation": "executeQuery",
                "query": "INSERT INTO client_summaries (lead_id, source_type, source_id, summary_text, summary_date) VALUES ($1, $2, $3, $4, $5::date)",
                "options": {"queryReplacement": "={{ $json.lead_id }}||={{ $json.type }}||={{ $json.source_id }}||={{ $json.summary_text.replace(/'/g, \"''\") }}||={{ $json.summary_date }}"}
            },
            "id": "save-chat-summary",
            "name": "Save Chat Summary to DB",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [832, 208],
            "credentials": {"postgres": PG_CRED}
        }
    ],

    "connections": {
        "Daily 22:00": {"main": [
            [{"node": "Load Today's Calls", "type": "main", "index": 0}],
            [{"node": "Load Today's Chats", "type": "main", "index": 0}]
        ]},
        "Load Today's Calls": {"main": [[{"node": "Prepare Calls", "type": "main", "index": 0}]]},
        "Load Today's Chats": {"main": [[{"node": "Prepare Chats", "type": "main", "index": 0}]]},
        "Prepare Calls": {"main": [[{"node": "Has Calls?", "type": "main", "index": 0}]]},
        "Prepare Chats": {"main": [[{"node": "Has Chats?", "type": "main", "index": 0}]]},
        # false-ветка (empty=false) → идём дальше; true-ветка (empty=true) → стоп
        "Has Calls?": {"main": [[], [{"node": "Load Call Prompt", "type": "main", "index": 0}]]},
        "Has Chats?": {"main": [[], [{"node": "Load Chat Prompt", "type": "main", "index": 0}]]},
        "Load Call Prompt": {"main": [[{"node": "Inject Call Prompt", "type": "main", "index": 0}]]},
        "Load Chat Prompt": {"main": [[{"node": "Inject Chat Prompt", "type": "main", "index": 0}]]},
        "Inject Call Prompt": {"main": [[{"node": "GLM-4: Summarize Call", "type": "main", "index": 0}]]},
        "Inject Chat Prompt": {"main": [[{"node": "GLM-4: Summarize Chat", "type": "main", "index": 0}]]},
        "GLM-4: Summarize Call": {"main": [[{"node": "Extract Call Summary", "type": "main", "index": 0}]]},
        "GLM-4: Summarize Chat": {"main": [[{"node": "Extract Chat Summary", "type": "main", "index": 0}]]},
        "Extract Call Summary": {"main": [[{"node": "Save Call Summary to DB", "type": "main", "index": 0}]]},
        "Extract Chat Summary": {"main": [[{"node": "Save Chat Summary to DB", "type": "main", "index": 0}]]}
    },

    "settings": {"executionOrder": "v1", "timezone": "Europe/Moscow"},
    "staticData": None,
    "tags": [{"name": "MVP Auto-Summary"}],
    "triggerCount": 2
}

out_path = os.path.join(os.path.dirname(__file__), '..', 'n8n-workflows', '03-individual-summaries.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

with open(out_path, encoding='utf-8') as f:
    check = json.load(f)

print(f"OK — {os.path.abspath(out_path)}")
print(f"Нод: {len(check['nodes'])} | Connections: {len(check['connections'])}")
