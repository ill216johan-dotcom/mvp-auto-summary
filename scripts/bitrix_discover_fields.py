"""
Task 4: Discover UF_* contract field in Bitrix24.

Run inside Docker container (where network access to Bitrix is available):
  docker exec mvp-autosummary-app-1 python /scripts/bitrix_discover_fields.py

Output: recommended BITRIX_CONTRACT_FIELD value to set in .env
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, "/app")

from app.integrations.bitrix24 import Bitrix24Client

WEBHOOK = os.environ.get(
    "BITRIX_WEBHOOK_URL",
    "https://bitrix24.ff-platform.ru/rest/1/fhh009wpvmby0tn6/",
)
FF_PATTERNS = ("FF-", "ФФ-", "ФФ")


def main() -> None:
    print("=== Bitrix24 UF_* Field Discovery ===\n")
    client = Bitrix24Client(WEBHOOK)

    # Step 1: Get all lead field definitions
    print("Step 1: Fetching lead field definitions (crm.lead.fields)...")
    try:
        all_fields = client.get_lead_fields()
    except Exception as e:
        print(f"ERROR fetching lead fields: {e}")
        sys.exit(1)

    uf_fields = {k: v for k, v in all_fields.items() if k.startswith("UF_")}
    print(f"Found {len(uf_fields)} UF_* custom fields:\n")

    for field_name, meta in sorted(uf_fields.items()):
        title = meta.get("title") or meta.get("listLabel") or meta.get("formLabel") or ""
        ftype = meta.get("type", "")
        print(f"  {field_name:40s} ({ftype:15s}) {title}")

    # Step 2: Sample leads to find FF- values
    print("\nStep 2: Sampling first 50 leads for FF-/ФФ- values...")
    select_fields = ["ID", "TITLE"] + list(uf_fields.keys())
    try:
        data = client.call("crm.lead.list", {"select": select_fields, "start": 0})
        results = data.get("result", [])
    except Exception as e:
        print(f"ERROR fetching leads: {e}")
        sys.exit(1)

    print(f"Sampled {len(results)} leads.\n")

    # Find fields containing contract numbers
    candidates: dict[str, list[str]] = {}
    for lead in results:
        for field_name in uf_fields:
            val = lead.get(field_name)
            if val and isinstance(val, str):
                for pat in FF_PATTERNS:
                    if pat.upper() in val.upper():
                        candidates.setdefault(field_name, []).append(val)
                        break

    # Step 3: Report
    print("=== RESULTS ===\n")
    if candidates:
        print("✅ CONTRACT FIELD CANDIDATES (contain FF-/ФФ- pattern):\n")
        for field_name, examples in candidates.items():
            meta = uf_fields.get(field_name, {})
            title = meta.get("title", "")
            print(f"  Field:    {field_name}")
            print(f"  Label:    {title}")
            print(f"  Examples: {examples[:5]}\n")
            print(f"  ➡  Set in .env:  BITRIX_CONTRACT_FIELD={field_name}\n")
    else:
        print("⚠️  No FF-/ФФ- pattern found in first 50 leads.")
        print("   All non-empty UF_* values:\n")
        for lead in results[:10]:
            lead_id = lead.get("ID")
            for field_name in uf_fields:
                val = lead.get(field_name)
                if val and str(val).strip() not in ("", "0", "N", "false"):
                    print(f"  Lead {lead_id}: {field_name} = {str(val)[:80]!r}")

    # Step 4: Check contact fields too
    print("\nStep 3: Checking contact fields (crm.contact.fields) for UF_* ...")
    try:
        contact_fields = client.get_contact_fields()
        contact_uf = {k: v for k, v in contact_fields.items() if k.startswith("UF_")}
        print(f"Contact UF_* fields: {len(contact_uf)}")
        for k, v in sorted(contact_uf.items()):
            title = v.get("title") or ""
            print(f"  {k:40s} {title}")
    except Exception as e:
        print(f"WARNING: Could not fetch contact fields: {e}")


if __name__ == "__main__":
    main()
