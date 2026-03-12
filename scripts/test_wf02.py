#!/usr/bin/env python3
"""Simulate WF02: Daily Digest → Telegram"""
from __future__ import annotations

import json
import os
import urllib.request
from datetime import date
from pathlib import Path

import psycopg2


def load_env() -> dict[str, str]:
    env_path = os.getenv("ENV_FILE")
    if env_path:
        path = Path(env_path)
    else:
        path = Path(__file__).resolve().parents[1] / ".env"

    values: dict[str, str] = {}
    if not path.exists():
        return values

    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def env(values: dict[str, str], key: str, default: str = "") -> str:
    return os.getenv(key) or values.get(key, default)


def main() -> None:
    env_values = load_env()
    db_pass = env(env_values, "POSTGRES_PASSWORD")
    if not db_pass:
        print("POSTGRES_PASSWORD missing in env or .env")
        return

    db_host = env(env_values, "POSTGRES_HOST", "localhost")
    db_port = env(env_values, "POSTGRES_PORT", "5432")
    db_name = env(env_values, "POSTGRES_DB", "n8n")
    db_user = env(env_values, "POSTGRES_USER", "n8n")
    tg_token = env(env_values, "TELEGRAM_BOT_TOKEN")
    tg_chat = env(env_values, "TELEGRAM_CHAT_ID")
    glm_api_key = env(env_values, "GLM4_API_KEY")
    summaries_url = env(env_values, "SUMMARIES_BASE_URL", "http://84.252.100.93:8181")

    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_pass,
    )
    cur = conn.cursor()

    # Step 1: Load today's data
    cur.execute(
        """
        SELECT pf.lead_id, pf.transcript_text, pf.filename, lcm.lead_name, lcm.curators
        FROM processed_files pf
        LEFT JOIN lead_chat_mapping lcm ON lcm.lead_id = pf.lead_id
        WHERE pf.transcript_text IS NOT NULL
        AND COALESCE(pf.file_date, pf.created_at::date) = CURRENT_DATE
        ORDER BY pf.lead_id
        """
    )
    transcripts = cur.fetchall()
    print(f"Transcripts today: {len(transcripts)}")

    cur.execute(
        """
        SELECT cs.lead_id, cs.source_type, cs.summary_text, lcm.lead_name
        FROM client_summaries cs
        LEFT JOIN lead_chat_mapping lcm ON lcm.lead_id = cs.lead_id
        WHERE cs.summary_date = CURRENT_DATE
        ORDER BY cs.lead_id
        """
    )
    summaries = cur.fetchall()
    print(f"Summaries today: {len(summaries)}")

    if not transcripts and not summaries:
        print("No data today. Sending empty message.")
        return

    # Step 2: Build context
    today = date.today().isoformat()
    lead_ids = list(set(t[0] for t in transcripts))

    context_parts = []
    for lead_id, text, filename, lead_name, curators in transcripts:
        context_parts.append(
            f"[LEAD-{lead_id} ({lead_name or '?'})]\nФайл: {filename}\nТекст: {text[:800]}"
        )

    for lead_id, src_type, summary, lead_name in summaries:
        context_parts.append(
            f"[LEAD-{lead_id} ({lead_name or '?'}) — Саммари ({src_type})]\n{summary[:800]}"
        )

    combined = "\n\n".join(context_parts)

    # Step 3: LLM digest
    if not glm_api_key:
        print("GLM4_API_KEY missing in env or .env")
        return

    prompt = (
        "Ты бизнес-аналитик. Сформируй ежедневный дайджест по стенограммам встреч.\n\n"
        "ФОРМАТ (строго HTML без Markdown):\n"
        "1) <b>Резюме дня</b> (3-5 предложений)\n"
        "2) <b>Ключевые договорённости</b> (буллеты)\n"
        "3) <b>Action items</b> (буллет, ответственный, срок)\n"
        "4) <b>Риски/блокеры</b> (или Нет)\n"
        "5) По каждому LEAD-ID: 1-2 ключевых пункта\n\n"
        "Максимум 3000 символов. Используй HTML-теги (<b>, <i>), НЕ Markdown."
    )

    payload = json.dumps(
        {
            "model": "claude-3-5-haiku-20241022",
            "system": prompt,
            "messages": [{"role": "user", "content": combined}],
            "max_tokens": 2000,
        }
    ).encode()

    req = urllib.request.Request(
        "https://api.z.ai/api/anthropic/v1/messages",
        data=payload,
        headers={
            "x-api-key": glm_api_key,
            "anthropic-version": "2023-06-01",
            "Content-Type": "application/json",
        },
    )

    try:
        resp = urllib.request.urlopen(req, timeout=120)
        data = json.loads(resp.read())
        digest = "\n".join([b["text"] for b in data["content"] if b.get("type") == "text"]).strip()
        print(f"Digest: {len(digest)} chars")
    except Exception as e:
        print(f"LLM ERROR: {e}")
        digest = "Ошибка генерации дайджеста."

    # Step 4: Build final message
    header = f"<b>📊 Дайджест за {today}</b>\nВстреч: {len(transcripts)} | Клиентов: {len(lead_ids)}"

    links = []
    for s in summaries:
        lead_id, src_type = s[0], s[1]
        link = f"{summaries_url}/{today}/LEAD-{lead_id}_{src_type}_{today}.md"
        links.append(f"• <a href=\"{link}\">LEAD-{lead_id} ({src_type})</a>")
    links_block = "\n".join(links) if links else ""

    message = f"{header}\n\n{digest}"
    if links_block:
        message += f"\n\n<b>📎 Саммари:</b>\n{links_block}"

    print(f"\n--- TELEGRAM MESSAGE ({len(message)} chars) ---")
    print(message[:1000])

    # Step 5: Send to Telegram
    if not tg_token or not tg_chat:
        print("ERROR: TELEGRAM_BOT_TOKEN or TELEGRAM_CHAT_ID missing")
        return

    tg_payload = json.dumps(
        {
            "chat_id": tg_chat,
            "text": message,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
    ).encode()

    tg_req = urllib.request.Request(
        f"https://api.telegram.org/bot{tg_token}/sendMessage",
        data=tg_payload,
        headers={"Content-Type": "application/json"},
    )

    try:
        tg_resp = urllib.request.urlopen(tg_req, timeout=30)
        tg_data = json.loads(tg_resp.read())
        if tg_data.get("ok"):
            msg_id = tg_data["result"]["message_id"]
            print(f"\n✅ Telegram sent! message_id={msg_id}")
        else:
            print(f"\n❌ Telegram error: {tg_data}")
    except Exception as e:
        print(f"\n❌ Telegram ERROR: {e}")

    # Step 6: Mark sent
    for t in transcripts:
        cur.execute(
            "UPDATE processed_files SET summary_sent=true WHERE lead_id=%s AND COALESCE(file_date, created_at::date) = CURRENT_DATE",
            (t[0],),
        )
    conn.commit()
    conn.close()
    print("\n=== WF02 COMPLETE ===")


if __name__ == "__main__":
    main()
