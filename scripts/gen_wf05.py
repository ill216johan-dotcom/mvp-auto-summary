#!/usr/bin/env python3
"""
Генератор WF05 — Prompt Tester (тестирование промптов на реальных данных).

Как пользоваться:
1. Открой WF05 в n8n
2. В ноде "Set Test Prompt" — вставь свой промпт в поле prompt_text
3. В ноде "Set Test Prompt" — укажи lead_id клиента чей транскрипт взять (или оставь пустым — возьмёт последний)
4. Нажми "Test workflow" (кнопка вверху)
5. Результат увидишь прямо в n8n в ноде "Show Result"

Ничего не ломает — это изолированный workflow только для тестов.
Запуск: python3 scripts/gen_wf05.py
"""
import json
import os

GLM_KEY = "fda5cc088ab04a1a92d5966b373e81a3.rfUescuUieAO78M6"
PG_CRED = {"id": "F3beGLVPdqgBpqlv", "name": "PostgreSQL"}

# Промпт по умолчанию — саммари одного созвона (самое важное)
DEFAULT_PROMPT = (
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

JS_LOAD_TRANSCRIPT = """
// Берём транскрипт — либо указанного клиента, либо последний доступный
const leadId = $json.test_lead_id;
const query = leadId
  ? `SELECT transcript_text, lead_id, filename FROM processed_files WHERE lead_id = '${leadId}' AND transcript_text IS NOT NULL ORDER BY created_at DESC LIMIT 1`
  : `SELECT transcript_text, lead_id, filename FROM processed_files WHERE transcript_text IS NOT NULL ORDER BY created_at DESC LIMIT 1`;

// Передаём запрос дальше
return [{ json: { ...($json), sql_query: query } }];
""".strip()

JS_CHECK_RESULT = """
const items = $input.all();
const promptData = $('Set Test Prompt').first().json;
const transcript = items[0]?.json?.transcript_text || '';
const leadId = items[0]?.json?.lead_id || 'не найден';
const filename = items[0]?.json?.filename || '—';

if (!transcript) {
  return [{ json: {
    status: 'ОШИБКА',
    message: 'Транскрипт не найден. Убедись что в базе есть обработанные файлы.',
    lead_id: leadId
  }}];
}

const systemPrompt = promptData.prompt_text || 'Сделай краткое саммари.';
const MAX = 40000;
const truncated = transcript.length > MAX;
const combined = truncated ? transcript.slice(0, MAX) + '\n...[обрезано]' : transcript;

return [{ json: {
  systemPrompt,
  combined,
  lead_id: leadId,
  filename,
  chars: transcript.length,
  truncated
}}];
""".strip()

JS_SHOW_RESULT = """
const glmResp = $json;
const msg = glmResp.choices && glmResp.choices[0] ? glmResp.choices[0].message : {};
const content = (msg.content || msg.reasoning_content || '').trim() || 'Ответ не получен.';
const meta = $('Check & Prepare').first().json;

return [{ json: {
  '=== РЕЗУЛЬТАТ ПРОМПТА ===': content,
  '--- МЕТА ---': {
    клиент: 'LEAD-' + meta.lead_id,
    файл: meta.filename,
    символов_в_транскрипте: meta.chars,
    обрезан: meta.truncated,
    длина_ответа: content.length
  }
}}];
""".strip()

JS_SAVE_PROMPT = """
// Сохраняем промпт в таблицу prompts под именем которое указал пользователь
// Если имя не указано — сохраняем как 'test_draft'
const promptName = $('Set Test Prompt').first().json.save_as || 'test_draft';
const promptText = $('Set Test Prompt').first().json.prompt_text || '';
const glmResp = $json;
const msg = glmResp.choices && glmResp.choices[0] ? glmResp.choices[0].message : {};
const result = (msg.content || '').trim();

return [{ json: {
  prompt_name: promptName,
  prompt_text: promptText,
  last_result: result.slice(0, 500) + (result.length > 500 ? '...' : '')
}}];
""".strip()

data = {
    "name": "05 \u2014 Prompt Tester (\u0442\u0435\u0441\u0442\u0438\u0440\u043e\u0432\u0430\u043d\u0438\u0435 \u043f\u0440\u043e\u043c\u043f\u0442\u043e\u0432)",
    "nodes": [
        # Триггер — запускается вручную кнопкой "Test workflow"
        {
            "parameters": {},
            "id": "manual-trigger",
            "name": "Manual Trigger",
            "type": "n8n-nodes-base.manualTrigger",
            "typeVersion": 1,
            "position": [0, 0]
        },

        # Здесь пользователь вставляет свой промпт и указывает lead_id для теста
        {
            "parameters": {
                "assignments": {
                    "assignments": [
                        {
                            "id": "prompt-field",
                            "name": "prompt_text",
                            "value": DEFAULT_PROMPT,
                            "type": "string"
                        },
                        {
                            "id": "lead-field",
                            "name": "test_lead_id",
                            "value": "",
                            "type": "string"
                        },
                        {
                            "id": "save-field",
                            "name": "save_as",
                            "value": "",
                            "type": "string"
                        }
                    ]
                },
                "options": {}
            },
            "id": "set-prompt",
            "name": "Set Test Prompt",
            "type": "n8n-nodes-base.set",
            "typeVersion": 3.4,
            "position": [220, 0],
            "notes": "РЕДАКТИРУЙ ЗДЕСЬ:\n\n🔑 save_as — КАКОЙ ПРОМПТ ТЕСТИРУЕШЬ (указать одно из):\n  call_summary_prompt  — саммари созвона → в open-notebook (WF03) ⬅ НАЧНИ С ЭТОГО\n  chat_summary_prompt  — саммари Telegram-чата (WF03)\n  report_prompt        — отчёт по /report (WF04)\n  digest_prompt        — ежедневный дайджест (WF02)\n\n📝 prompt_text — вставь новый промпт сюда\n\n🎯 test_lead_id — LEAD ID клиента (оставь пустым — возьмёт последний транскрипт)"
        },

        # Подготовка SQL запроса
        {
            "parameters": {"jsCode": JS_LOAD_TRANSCRIPT},
            "id": "prepare-query",
            "name": "Prepare Query",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [440, 0]
        },

        # Загрузка транскрипта из БД
        {
            "parameters": {
                "operation": "executeQuery",
                "query": "={{ $json.sql_query }}",
                "options": {}
            },
            "id": "load-transcript",
            "name": "Load Transcript",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [660, 0],
            "credentials": {"postgres": PG_CRED},
            "continueOnFail": True
        },

        # Проверка и подготовка запроса к GLM
        {
            "parameters": {"jsCode": JS_CHECK_RESULT},
            "id": "check-prepare",
            "name": "Check & Prepare",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [880, 0]
        },

        # Вызов GLM-4
        {
            "parameters": {
                "method": "POST",
                "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions",
                "sendBody": True,
                "specifyBody": "json",
                "jsonBody": "={{ JSON.stringify({ model: 'glm-4.7-flash', messages: [{ role: 'system', content: $json.systemPrompt }, { role: 'user', content: $json.combined }], temperature: 0.3, max_tokens: 2000, stream: false, thinking: { type: 'disabled' } }) }}",
                "sendHeaders": True,
                "headerParameters": {
                    "parameters": [
                        {"name": "Authorization", "value": f"Bearer {GLM_KEY}"},
                        {"name": "Content-Type", "value": "application/json"}
                    ]
                },
                "options": {"timeout": 90000}
            },
            "id": "glm-test",
            "name": "GLM-4 Test Call",
            "type": "n8n-nodes-base.httpRequest",
            "typeVersion": 4.2,
            "position": [1100, 0],
            "continueOnFail": True
        },

        # Показываем результат
        {
            "parameters": {"jsCode": JS_SHOW_RESULT},
            "id": "show-result",
            "name": "Show Result",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1320, 0]
        },

        # Сохранение промпта в БД (только если указано save_as)
        {
            "parameters": {"jsCode": JS_SAVE_PROMPT},
            "id": "prepare-save",
            "name": "Prepare Save",
            "type": "n8n-nodes-base.code",
            "typeVersion": 2,
            "position": [1540, 0]
        },

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
                    "INSERT INTO prompts (name, prompt_text, last_result, updated_at)"
                    "  VALUES ($1, $2, $3, NOW())"
                    "  ON CONFLICT (name) DO UPDATE"
                    "    SET prompt_text = EXCLUDED.prompt_text,"
                    "        last_result = EXCLUDED.last_result,"
                    "        updated_at = NOW();"
                    "SELECT name, updated_at, LEFT(prompt_text, 80) as preview FROM prompts WHERE name = $1;"
                ),
                "options": {
                    "queryReplacement": "={{ $json.prompt_name }}||={{ $json.prompt_text }}||={{ $json.last_result }}"
                }
            },
            "id": "save-to-db",
            "name": "Save Prompt to DB",
            "type": "n8n-nodes-base.postgres",
            "typeVersion": 2.5,
            "position": [1760, 0],
            "credentials": {"postgres": PG_CRED},
            "continueOnFail": True
        }
    ],
    "connections": {
        "Manual Trigger": {"main": [[{"node": "Set Test Prompt", "type": "main", "index": 0}]]},
        "Set Test Prompt": {"main": [[{"node": "Prepare Query", "type": "main", "index": 0}]]},
        "Prepare Query": {"main": [[{"node": "Load Transcript", "type": "main", "index": 0}]]},
        "Load Transcript": {"main": [[{"node": "Check & Prepare", "type": "main", "index": 0}]]},
        "Check & Prepare": {"main": [[{"node": "GLM-4 Test Call", "type": "main", "index": 0}]]},
        "GLM-4 Test Call": {"main": [[{"node": "Show Result", "type": "main", "index": 0}]]},
        "Show Result": {"main": [[{"node": "Prepare Save", "type": "main", "index": 0}]]},
        "Prepare Save": {"main": [[{"node": "Save Prompt to DB", "type": "main", "index": 0}]]}
    },
    "settings": {"executionOrder": "v1", "timezone": "Europe/Moscow"},
    "staticData": None,
    "tags": [{"name": "MVP Auto-Summary"}]
}

out_path = os.path.join(os.path.dirname(__file__), '..', 'n8n-workflows', '05-prompt-tester.json')
with open(out_path, 'w', encoding='utf-8') as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

with open(out_path, encoding='utf-8') as f:
    check = json.load(f)

print(f"OK — {os.path.abspath(out_path)}")
print(f"Нод: {len(check['nodes'])} | Connections: {len(check['connections'])}")
