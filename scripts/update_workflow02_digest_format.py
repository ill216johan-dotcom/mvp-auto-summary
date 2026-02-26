#!/usr/bin/env python3
"""
Обновляет GLM-4 промпт в Workflow 02 (Daily Digest) на формат по кураторам.
Запускать на сервере: python3 /tmp/update_workflow02_digest_format.py
"""

import subprocess
import json
import sys

CONTAINER = "mvp-auto-summary-postgres-1"
DB_USER = "n8n"
DB_NAME = "n8n"

NEW_SYSTEM_PROMPT = (
    "Ты аналитик отдела кураторов фулфилмент-компании. Тебе дают транскрипты созвонов кураторов с клиентами за день.\n\n"
    "КУРАТОРЫ ОТДЕЛА (определи кто вёл каждый созвон по тексту):\n"
    "- Евгений (основной куратор)\n"
    "- Кристина (основной куратор)\n"
    "- Анна (основной куратор)\n"
    "- Галина (куратор-консультант, мелкие вопросы)\n"
    "- Дарья (куратор-консультант, мелкие вопросы)\n"
    "- Станислав (куратор-продакт, руководитель)\n"
    "- Андрей (куратор-продакт, руководитель)\n\n"
    "Сформируй отчёт СТРОГО по следующему формату (без отступлений):\n\n"
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


def run_psql(query):
    result = subprocess.run(
        ["docker", "exec", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME, "-t", "-A", "-c", query],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(f"❌ Ошибка psql: {result.stderr}")
        sys.exit(1)
    return result.stdout.strip()


def main():
    print("🔍 Ищу активный Workflow 02...")

    # Ищем самый свежий workflow 02
    rows = run_psql(
        "SELECT id, name, active, \"updatedAt\" FROM workflow_entity "
        "WHERE name LIKE '%02%' OR name LIKE '%Daily%' OR name LIKE '%Digest%' "
        "ORDER BY \"updatedAt\" DESC LIMIT 5;"
    )

    if not rows:
        print("❌ Workflow 02 не найден! Проверь названия через n8n UI.")
        sys.exit(1)

    print(f"Найдены workflows:\n{rows}\n")

    # Берём первый (самый свежий)
    wf_id = rows.split("\n")[0].split("|")[0].strip()
    print(f"✅ Используем workflow ID: {wf_id}")

    # Читаем nodes
    nodes_raw = run_psql(
        f"SELECT nodes::text FROM workflow_entity WHERE id = '{wf_id}';"
    )

    if not nodes_raw:
        print(f"❌ Nodes не найдены для ID {wf_id}")
        sys.exit(1)

    nodes = json.loads(nodes_raw)
    print(f"📋 Нод в workflow: {len(nodes)}")

    # Находим ноду GLM-4 Summarize
    glm_node = None
    for node in nodes:
        if node.get("name") == "GLM-4 Summarize":
            glm_node = node
            break

    if not glm_node:
        print("❌ Нода 'GLM-4 Summarize' не найдена!")
        print("Доступные ноды:", [n.get("name") for n in nodes])
        sys.exit(1)

    print(f"✅ Нашёл ноду: {glm_node['name']}")

    # Формируем новый jsonBody
    new_json_body = json.dumps({
        "model": "glm-4.7-flash",
        "messages": [
            {
                "role": "system",
                "content": NEW_SYSTEM_PROMPT
            },
            {
                "role": "user",
                "content": "={{ $json.combined }}"
            }
        ],
        "temperature": 0.2,
        "max_tokens": 1500,
        "stream": False,
        "thinking": {"type": "disabled"}
    }, ensure_ascii=False)

    # n8n использует expression {{ }}, поэтому jsonBody это строка-выражение
    # Правильный формат: ={{ JSON.stringify({ ... content: $json.combined ... }) }}
    system_prompt_escaped = json.dumps(NEW_SYSTEM_PROMPT, ensure_ascii=False)
    new_body = (
        "={{ JSON.stringify({ "
        "model: 'glm-4.7-flash', "
        "messages: [ "
        "{ role: 'system', content: " + system_prompt_escaped + " }, "
        "{ role: 'user', content: $json.combined } "
        "], "
        "temperature: 0.2, max_tokens: 1500, stream: false, thinking: { type: 'disabled' } "
        "}) }}"
    )

    glm_node["parameters"]["jsonBody"] = new_body
    print("✅ GLM промпт обновлён")

    # Сохраняем обратно в PostgreSQL
    nodes_json = json.dumps(nodes, ensure_ascii=False).replace("'", "''")
    update_sql = f"UPDATE workflow_entity SET nodes = '{nodes_json}'::json, \"updatedAt\" = NOW() WHERE id = '{wf_id}';"

    result = subprocess.run(
        ["docker", "exec", "-i", CONTAINER, "psql", "-U", DB_USER, "-d", DB_NAME],
        input=update_sql, text=True, capture_output=True
    )

    if result.returncode != 0:
        print(f"❌ Ошибка обновления: {result.stderr}")
        sys.exit(1)

    print(f"✅ Workflow {wf_id} обновлён в PostgreSQL!")
    print("\n📌 Что изменилось:")
    print("  - GLM промпт теперь требует отчёт по кураторам")
    print("  - Список кураторов: Евгений, Кристина, Анна, Галина, Дарья, Станислав, Андрей")
    print("  - Формат: 👤 Имя → созвонов N, решённых/открытых вопросов N")
    print("\n⚠️  Важно: перезагрузи workflow в n8n UI чтобы изменения вступили в силу!")
    print("  n8n → Workflow 02 → сохрани (Ctrl+S) или деактивируй/активируй")


if __name__ == "__main__":
    main()
