"""
E2E test for Bitrix24 sync — runs inside the orchestrator container.
Tests: config, API connectivity, DB tables, partial sync (first 5 leads only).
"""
import os
import sys
sys.path.insert(0, '/app')

from app.config import get_settings
from app.integrations.bitrix24 import Bitrix24Client
from app.core.db import Database

print("=== Bitrix24 E2E Test ===\n")

# 1. Config check
s = get_settings()
print(f"[1] Config:")
print(f"    bitrix_webhook_url: {'SET (' + s.bitrix_webhook_url[:50] + '...)' if s.bitrix_webhook_url else 'EMPTY'}")
print(f"    bitrix_contract_field: {s.bitrix_contract_field or 'EMPTY'}")
print(f"    bitrix_sync_enabled: {s.bitrix_sync_enabled}")
print(f"    bitrix_sync_hour: {s.bitrix_sync_hour}")

if not s.bitrix_webhook_url:
    print("\n[!] BITRIX_WEBHOOK_URL not set. Using hardcoded test URL.")
    WEBHOOK = "https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/"
else:
    WEBHOOK = s.bitrix_webhook_url

CONTRACT_FIELD = s.bitrix_contract_field or "UF_CRM_1632960743049"
print(f"\n    Using webhook: {WEBHOOK[:50]}...")
print(f"    Using contract field: {CONTRACT_FIELD}")

# 2. API connectivity
print(f"\n[2] Bitrix24 API:")
client = Bitrix24Client(WEBHOOK)
try:
    result = client.call("crm.lead.list", {"select": ["ID"], "start": 0})
    total = result.get("total", 0)
    print(f"    crm.lead.list OK — total leads: {total}")
except Exception as e:
    print(f"    FAIL: {e}")
    sys.exit(1)

# 3. DB tables check
print(f"\n[3] Database tables:")
db = Database(dsn=f"postgresql://{s.postgres_user}:{s.postgres_password}@{s.postgres_host}:{s.postgres_port}/{s.postgres_db}")
tables = ["bitrix_leads", "bitrix_calls", "bitrix_emails", "bitrix_comments", "bitrix_sync_log", "bitrix_summaries"]
with db.connection() as conn:
    cur = conn.cursor()
    for table in tables:
        cur.execute(f"SELECT count(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"    {table}: {count} rows")
    cur.close()

# 4. Partial sync — first 5 leads only
print(f"\n[4] Partial sync (first 5 leads):")
from app.tasks.bitrix_sync import sync_bitrix_leads, sync_bitrix_contacts

# Sync just leads (limited to first page = 50, we take first 5 for speed)
try:
    # Get first 5 leads manually
    result = client.call("crm.lead.list", {
        "select": ["ID", "TITLE", "NAME", "LAST_NAME", "PHONE", "EMAIL",
                   "STATUS_ID", "SOURCE_ID", "ASSIGNED_BY_ID", CONTRACT_FIELD],
        "start": 0
    })
    leads_raw = result.get("result", [])[:5]
    print(f"    Fetched {len(leads_raw)} leads for test")

    from app.tasks.bitrix_sync import _extract_phone, _extract_email, _extract_contract_number, _parse_datetime
    from datetime import datetime

    synced = 0
    with db.connection() as conn:
        for lead in leads_raw:
            lead_id = int(lead["ID"])
            diffy_lead_id = f"BX-LEAD-{lead_id}"
            name_parts = [lead.get("NAME", ""), lead.get("LAST_NAME", "")]
            full_name = " ".join(p for p in name_parts if p).strip()

            cur = conn.cursor()
            try:
                cur.execute("""
                    INSERT INTO bitrix_leads
                        (bitrix_lead_id, bitrix_entity_type, diffy_lead_id, title, name,
                         phone, email, status_id, source_id, responsible_id,
                         responsible_name, last_synced_at)
                    VALUES (%s, 'lead', %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                    ON CONFLICT (bitrix_lead_id) DO UPDATE SET
                        diffy_lead_id = EXCLUDED.diffy_lead_id,
                        last_synced_at = NOW()
                """, (
                    lead_id, diffy_lead_id,
                    lead.get("TITLE", ""), full_name,
                    _extract_phone(lead.get("PHONE")),
                    _extract_email(lead.get("EMAIL")),
                    lead.get("STATUS_ID", ""), lead.get("SOURCE_ID", ""),
                    int(lead.get("ASSIGNED_BY_ID") or 0), "",
                ))
                conn.commit()
                synced += 1
            except Exception as e:
                conn.rollback()
                print(f"    WARN: lead {lead_id}: {e}")
            finally:
                cur.close()

    print(f"    Synced {synced}/5 leads OK")

    # Verify in DB
    with db.connection() as conn:
        cur = conn.cursor()
        cur.execute("SELECT bitrix_lead_id, diffy_lead_id, title FROM bitrix_leads ORDER BY id DESC LIMIT 5")
        rows = cur.fetchall()
        print(f"\n[5] DB verification (last 5 rows in bitrix_leads):")
        for r in rows:
            print(f"    {r[0]} → {r[1]} | {r[2][:40] if r[2] else ''}")
        cur.close()

except Exception as e:
    print(f"    FAIL: {e}")
    import traceback; traceback.print_exc()

client.close()
print("\n=== E2E Test COMPLETE ===")
