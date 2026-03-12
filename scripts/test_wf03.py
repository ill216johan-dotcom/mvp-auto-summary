#!/usr/bin/env python3
"""Simulate WF03: Individual Summaries → GLM-4 → Dify"""
from __future__ import annotations

import json
import os
import urllib.request
from collections import defaultdict
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
    glm_api_key = env(env_values, "GLM4_API_KEY")
    glm_base_url = env(env_values, "GLM4_BASE_URL", "https://api.z.ai/api/anthropic")
    glm_model = env(env_values, "GLM4_MODEL", "claude-3-5-haiku-20241022")
    dify_api_key = env(env_values, "DIFY_API_KEY")
    dify_base_url = env(env_values, "DIFY_BASE_URL", "http://localhost")
    summaries_dir = env(
        env_values,
        "SUMMARIES_DIR",
        str(Path(__file__).resolve().parents[1] / "summaries"),
    )

    conn = psycopg2.connect(
        host=db_host,
        port=db_port,
        dbname=db_name,
        user=db_user,
        password=db_pass,
    )
    cur = conn.cursor()

    # Step 1: Load today's calls
    cur.execute(
        """
        SELECT pf.id, pf.filename, pf.lead_id, pf.transcript_text
        FROM processed_files pf
        WHERE pf.status = 'completed'
        AND DATE(COALESCE(pf.file_date, pf.completed_at, pf.created_at)) = CURRENT_DATE
        AND pf.transcript_text IS NOT NULL
        AND (pf.dify_doc_id IS NULL OR pf.dify_doc_id = '')
        ORDER BY pf.lead_id, pf.id LIMIT 20
        """
    )
    calls = cur.fetchall()
    print(f"Found {len(calls)} calls to process")

    if not calls:
        print("No calls found. Exiting.")
        return

    # Step 2: Dataset map
    cur.execute("SELECT lead_id, dify_dataset_id FROM lead_chat_mapping WHERE active = true")
    ds_map = {row[0]: row[1] for row in cur.fetchall()}

    # Step 3: Group by lead
    grouped = defaultdict(list)
    for call_id, filename, lead_id, text in calls:
        grouped[lead_id].append({"id": call_id, "filename": filename, "text": text})

    today = date.today().isoformat()

    for lead_id, lead_calls in grouped.items():
        print(f"\n=== Processing LEAD-{lead_id} ({len(lead_calls)} calls) ===")
        dataset_id = ds_map.get(lead_id, "")

        if not glm_api_key:
            print("GLM4_API_KEY missing in env or .env")
            return

        # Step 4: LLM
        combined = "\n\n".join(
            [
                f"--- Звонок {i + 1} ({c['filename']}) ---\n{c['text']}"
                for i, c in enumerate(lead_calls)
            ]
        )
        prompt = (
            "Ты бизнес-аналитик. Проанализируй транскрипцию(и) созвона с клиентом.\n"
            "Выдай:\n1) Краткое резюме (2-3 предл.)\n2) Участники звонка\n"
            "3) Ключевые договорённости\n4) Action Items с дедлайнами (если есть)\n"
            "5) Риски/проблемы\n6) Тон клиента (позитивный/нейтральный/негативный)\n"
            "Формат: Markdown. Не более 1500 слов."
        )

        glm_payload = json.dumps(
            {
                "model": glm_model,
                "system": prompt,
                "messages": [{"role": "user", "content": combined}],
                "max_tokens": 2000,
            }
        ).encode()

        req = urllib.request.Request(
            f"{glm_base_url}/v1/messages",
            data=glm_payload,
            headers={
                "x-api-key": glm_api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
        )

        try:
            resp = urllib.request.urlopen(req, timeout=120)
            glm_data = json.loads(resp.read())
            print("API response keys:", list(glm_data.keys()))
            if "choices" in glm_data:
                summary = glm_data["choices"][0]["message"]["content"].strip()
            elif "content" in glm_data:
                texts = [b["text"] for b in glm_data["content"] if b.get("type") == "text"]
                summary = "\n".join(texts).strip()
            else:
                print(f"Unknown response format: {str(glm_data)[:500]}")
                continue
            print(f"Summary: {len(summary)} chars")
            print(summary[:300] + "...")
        except Exception as e:
            print(f"LLM ERROR: {e}")
            continue

        # Step 5: Write MD
        filename_md = f"LEAD-{lead_id}_call_{today}.md"
        md_dir = Path(summaries_dir) / today
        md_dir.mkdir(parents=True, exist_ok=True)
        (md_dir / filename_md).write_text(summary, encoding="utf-8")
        print(f"MD file: {md_dir}/{filename_md}")

        # Step 6: Dify push
        doc_id = ""
        if dataset_id:
            if not dify_api_key:
                print("DIFY_API_KEY missing in env or .env")
                return

            doc_name = f"[{today}] LEAD-{lead_id} — Созвоны ({len(lead_calls)} звонок)"
            dify_payload = json.dumps(
                {
                    "name": doc_name,
                    "text": summary,
                    "indexing_technique": "high_quality",
                    "process_rule": {"mode": "automatic"},
                }
            ).encode()
            dify_req = urllib.request.Request(
                f"{dify_base_url}/v1/datasets/{dataset_id}/document/create-by-text",
                data=dify_payload,
                headers={
                    "Authorization": f"Bearer {dify_api_key}",
                    "Content-Type": "application/json",
                },
            )
            try:
                dify_resp = urllib.request.urlopen(dify_req, timeout=60)
                dify_data = json.loads(dify_resp.read())
                doc_id = dify_data.get("document", {}).get("id", "")
                print(f"Dify doc: {doc_id}")
            except Exception as e:
                print(f"Dify ERROR: {e}")

        # Step 7: Save to DB
        call_ids = [c["id"] for c in lead_calls]
        cur.execute(
            "INSERT INTO client_summaries (lead_id, source_type, summary_text, summary_date) VALUES (%s, %s, %s, %s) RETURNING id",
            (lead_id, "call", summary, today),
        )
        sid = cur.fetchone()[0]
        for cid in call_ids:
            cur.execute(
                "UPDATE processed_files SET dify_doc_id=%s, summary_text=%s WHERE id=%s",
                (doc_id, summary, cid),
            )
        conn.commit()
        print(f"DB saved: summary_id={sid}")
        print(f"LEAD-{lead_id} DONE!")

    conn.close()
    print("\n=== WF03 COMPLETE ===")


if __name__ == "__main__":
    main()
