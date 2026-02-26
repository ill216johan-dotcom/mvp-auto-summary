#!/usr/bin/env python3
"""
setup_dify_datasets.py
======================
Создаёт в Dify.ai отдельные Knowledge Base для каждого клиента
и общий датасет для документации (оферта, WMS-инструкция и т.д.).

После создания — сохраняет mapping lead_id → dify_dataset_id в PostgreSQL.

Использование:
    python3 setup_dify_datasets.py --dify-url http://84.252.100.93:8080 --api-key YOUR_KEY
    python3 setup_dify_datasets.py  # Читает из .env или переменных окружения

Требования:
    pip install requests psycopg2-binary python-dotenv
"""

import os
import sys
import json
import argparse
import requests
import psycopg2
from pathlib import Path

# ── Try to load .env ──────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    env_path = Path(__file__).parent / ".env"
    if not env_path.exists():
        env_path = Path(__file__).parent.parent / "n8n-workflows" / ".env"
    load_dotenv(env_path)
    print(f"Loaded .env from {env_path}")
except ImportError:
    pass

# ── Config ────────────────────────────────────────────────────────────────────
DIFY_BASE_URL = os.getenv("DIFY_BASE_URL", "http://84.252.100.93:8080")
DIFY_API_KEY  = os.getenv("DIFY_API_KEY", "")

PG_HOST = os.getenv("POSTGRES_HOST", "localhost")
PG_PORT = os.getenv("POSTGRES_PORT", "5432")
PG_DB   = os.getenv("POSTGRES_DB", "n8n")
PG_USER = os.getenv("POSTGRES_USER", "n8n")
PG_PASS = os.getenv("POSTGRES_PASSWORD", "")

# Клиенты из таблицы lead_chat_mapping
CLIENTS = [
    {"lead_id": "4405", "lead_name": "ФФ-4405"},
    {"lead_id": "987",  "lead_name": "ФФ-987"},
    {"lead_id": "1381", "lead_name": "ФФ-1381"},
    {"lead_id": "2048", "lead_name": "ФФ-2048"},
    {"lead_id": "4550", "lead_name": "ФФ-4550"},
    {"lead_id": "506",  "lead_name": "ФФ-506"},
]

GENERAL_DATASET_NAME = "Общая документация ФФ Платформы"


def dify_headers():
    return {
        "Authorization": f"Bearer {DIFY_API_KEY}",
        "Content-Type": "application/json",
    }


def list_datasets(base_url: str) -> list[dict]:
    """Возвращает все существующие датасеты из Dify."""
    url = f"{base_url}/v1/datasets?limit=100"
    resp = requests.get(url, headers=dify_headers(), timeout=30)
    resp.raise_for_status()
    return resp.json().get("data", [])


def create_dataset(base_url: str, name: str, description: str = "") -> dict:
    """Создаёт новый Knowledge Base в Dify. Возвращает созданный объект."""
    url = f"{base_url}/v1/datasets"
    payload = {
        "name": name,
        "description": description,
        "permission": "only_me",          # Приватный датасет
        "indexing_technique": "high_quality",
    }
    resp = requests.post(url, headers=dify_headers(), json=payload, timeout=30)
    resp.raise_for_status()
    return resp.json()


def ensure_dataset(base_url: str, name: str, description: str, existing: list[dict]) -> dict:
    """Создаёт датасет если не существует, иначе возвращает существующий."""
    for ds in existing:
        if ds.get("name") == name:
            print(f"  [EXIST] '{name}' → id={ds['id']}")
            return ds
    ds = create_dataset(base_url, name, description)
    print(f"  [CREATE] '{name}' → id={ds['id']}")
    return ds


def save_dataset_id_to_db(conn, lead_id: str, dataset_id: str):
    """Сохраняет dify_dataset_id в таблицу lead_chat_mapping."""
    with conn.cursor() as cur:
        # Добавляем колонку если нет (idempotent)
        cur.execute("""
            ALTER TABLE lead_chat_mapping
            ADD COLUMN IF NOT EXISTS dify_dataset_id VARCHAR(200)
        """)
        cur.execute("""
            UPDATE lead_chat_mapping
               SET dify_dataset_id = %s
             WHERE lead_id = %s
        """, (dataset_id, lead_id))
        conn.commit()


def save_general_dataset_id_to_db(conn, dataset_id: str):
    """Сохраняет ID общего датасета в таблицу системных настроек."""
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_settings (
                key   VARCHAR(100) PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TIMESTAMP DEFAULT NOW()
            )
        """)
        cur.execute("""
            INSERT INTO system_settings (key, value)
            VALUES ('dify_general_dataset_id', %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value, updated_at = NOW()
        """, (dataset_id,))
        conn.commit()


def print_env_block(mapping: dict, general_id: str):
    """Выводит блок переменных окружения для .env и n8n."""
    print("\n" + "="*60)
    print("Добавь эти переменные в n8n (Settings → Variables):")
    print("="*60)
    print(f"DIFY_GENERAL_DATASET_ID={general_id}")
    for lead_id, ds_id in mapping.items():
        print(f"DIFY_DATASET_{lead_id}={ds_id}")
    print("="*60)
    print("\nИли сохрани в .env для дальнейшего использования.")


def main():
    parser = argparse.ArgumentParser(description="Setup Dify datasets for each client")
    parser.add_argument("--dify-url", default=DIFY_BASE_URL, help="Dify base URL")
    parser.add_argument("--api-key",  default=DIFY_API_KEY,  help="Dify API key")
    parser.add_argument("--pg-host",  default=PG_HOST)
    parser.add_argument("--pg-port",  default=PG_PORT)
    parser.add_argument("--pg-db",    default=PG_DB)
    parser.add_argument("--pg-user",  default=PG_USER)
    parser.add_argument("--pg-pass",  default=PG_PASS)
    parser.add_argument("--no-db",    action="store_true", help="Не сохранять в PostgreSQL")
    parser.add_argument("--dry-run",  action="store_true", help="Только показать план, не создавать")
    args = parser.parse_args()

    global DIFY_API_KEY

    base_url = args.dify_url.rstrip("/")
    api_key  = args.api_key

    if not api_key:
        print("ERROR: DIFY_API_KEY не задан. Используй --api-key или переменную окружения.")
        sys.exit(1)

    DIFY_API_KEY = api_key

    print(f"\n[Dify] Подключаемся к {base_url} ...")

    # Загружаем существующие датасеты
    try:
        existing = list_datasets(base_url)
        print(f"[Dify] Найдено существующих датасетов: {len(existing)}")
    except Exception as e:
        print(f"ERROR: Не удалось получить список датасетов: {e}")
        sys.exit(1)

    if args.dry_run:
        print("\n[DRY RUN] Будут созданы:")
        print(f"  - '{GENERAL_DATASET_NAME}'")
        for c in CLIENTS:
            print(f"  - 'LEAD-{c['lead_id']} {c['lead_name']}'")
        return

    # ── Создаём общий датасет ──────────────────────────────────────────────
    print(f"\n[1/2] Общая документация:")
    general_ds = ensure_dataset(
        base_url,
        GENERAL_DATASET_NAME,
        "Оферта, инструкция по WMS, регламенты, политики ФФ Платформы. Доступна всем кураторам.",
        existing,
    )
    general_id = general_ds["id"]

    # ── Создаём датасеты для каждого клиента ──────────────────────────────
    print(f"\n[2/2] Клиентские датасеты:")
    lead_dataset_map = {}  # lead_id → dataset_id

    for client in CLIENTS:
        lead_id   = client["lead_id"]
        lead_name = client["lead_name"]
        ds_name   = f"LEAD-{lead_id} {lead_name}"
        desc      = (
            f"Индивидуальные данные клиента {lead_name}: "
            f"транскрипты созвонов, история Telegram-чата, ежедневные саммари, заметки."
        )
        ds = ensure_dataset(base_url, ds_name, desc, existing)
        lead_dataset_map[lead_id] = ds["id"]

    # ── Сохраняем в PostgreSQL ──────────────────────────────────────────────
    if not args.no_db:
        print("\n[DB] Сохраняем dataset IDs в PostgreSQL ...")
        try:
            conn = psycopg2.connect(
                host=args.pg_host,
                port=args.pg_port,
                dbname=args.pg_db,
                user=args.pg_user,
                password=args.pg_pass,
            )
            for lead_id, ds_id in lead_dataset_map.items():
                save_dataset_id_to_db(conn, lead_id, ds_id)
                print(f"  LEAD-{lead_id} → {ds_id}")
            save_general_dataset_id_to_db(conn, general_id)
            print(f"  general → {general_id}")
            conn.close()
            print("[DB] Сохранено успешно.")
        except Exception as e:
            print(f"[DB] WARN: Не удалось сохранить в PostgreSQL: {e}")
            print("[DB] Dataset IDs только в выводе ниже.")

    # ── Итог ───────────────────────────────────────────────────────────────
    result = {
        "general": {"name": GENERAL_DATASET_NAME, "id": general_id},
        "clients": [
            {"lead_id": lid, "dataset_id": did}
            for lid, did in lead_dataset_map.items()
        ],
    }
    print("\n[RESULT] Итоговый mapping:")
    print(json.dumps(result, ensure_ascii=False, indent=2))

    print_env_block(lead_dataset_map, general_id)
    print("\nГотово! Теперь обнови WF03 в n8n чтобы пушить в нужный датасет по lead_id.")


if __name__ == "__main__":
    main()
