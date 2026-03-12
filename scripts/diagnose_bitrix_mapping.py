#!/usr/bin/env python3
"""
Diagnostic script: Check Bitrix dataset mapping state before migration.
Run this BEFORE applying migrate_fix_bitrix_mapping.sql
"""
import sys
import os

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.db import Database
from app.core.config import settings


def print_section(title: str):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}")


def main():
    db = Database(settings.db_dsn)

    print_section("BITRIX DATASET MAPPING DIAGNOSTICS")

    # Check 1: Does bitrix_leads have dify_dataset_id column?
    print_section("1. bitrix_leads table structure")
    with db.cursor() as cur:
        cur.execute("""
            SELECT column_name, data_type
            FROM information_schema.columns
            WHERE table_name = 'bitrix_leads'
            ORDER BY ordinal_position
        """)
        columns = cur.fetchall()
        has_dify_column = any(col[0] == 'dify_dataset_id' for col in columns)

        print(f"Has dify_dataset_id column: {'✅ YES' if has_dify_column else '❌ NO'}")
        if has_dify_column:
            print("\nColumns related to Dify:")
            for col_name, col_type in columns:
                if 'dify' in col_name.lower():
                    print(f"  - {col_name}: {col_type}")

    # Check 2: Bitrix leads with datasets
    print_section("2. Bitrix leads/contacts with datasets")
    with db.cursor() as cur:
        if has_dify_column:
            cur.execute("""
                SELECT
                    bitrix_entity_type,
                    COUNT(*) as total,
                    COUNT(dify_dataset_id) as with_dataset,
                    COUNT(contract_number) as with_contract
                FROM bitrix_leads
                GROUP BY bitrix_entity_type
            """)
            for row in cur.fetchall():
                entity_type, total, with_dataset, with_contract = row
                print(f"\n{entity_type.upper()}:")
                print(f"  Total: {total}")
                print(f"  With dify_dataset_id: {with_dataset} ({with_dataset*100//total if total else 0}%)")
                print(f"  With contract_number: {with_contract}")
        else:
            print("⚠️  Skipped - no dify_dataset_id column")

    # Check 3: lead_chat_mapping content
    print_section("3. lead_chat_mapping (should be Telegram ONLY)")
    with db.cursor() as cur:
        cur.execute("""
            SELECT
                COUNT(*) as total,
                COUNT(CASE WHEN lead_id LIKE 'ФФ-%' THEN 1 END) as ff_contracts,
                COUNT(CASE WHEN lead_id LIKE 'BX-LEAD-%' THEN 1 END) as bx_leads,
                COUNT(CASE WHEN lead_id LIKE 'BX-CONTACT-%' THEN 1 END) as bx_contacts,
                COUNT(CASE WHEN lead_id ~ '^[0-9]+$' THEN 1 END) as numeric_telegram
            FROM lead_chat_mapping
            WHERE active = true
        """)
        row = cur.fetchone()
        total, ff, bx_lead, bx_contact, numeric = row

        print(f"Total active mappings: {total}")
        print(f"  ФФ-XXXX (Bitrix contracts): {ff} ⚠️  WRONG TABLE")
        print(f"  BX-LEAD-XXXX (Bitrix leads): {bx_lead} ⚠️  WRONG TABLE")
        print(f"  BX-CONTACT-XXXX (Bitrix): {bx_contact} ⚠️  WRONG TABLE")
        print(f"  Numeric (Telegram): {numeric} ✅ CORRECT")

    # Check 4: Sample of problematic mappings
    if ff or bx_lead or bx_contact:
        print_section("4. Sample of Bitrix IDs in lead_chat_mapping (WRONG)")
        with db.cursor() as cur:
            cur.execute("""
                SELECT lead_id, lead_name, dify_dataset_id
                FROM lead_chat_mapping
                WHERE active = true
                  AND (
                      lead_id LIKE 'ФФ-%' OR
                      lead_id LIKE 'BX-LEAD-%' OR
                      lead_id LIKE 'BX-CONTACT-%'
                  )
                LIMIT 10
            """)
            for row in cur.fetchall():
                lead_id, lead_name, dataset_id = row
                print(f"  {lead_id} → {dataset_id}")
                if lead_name:
                    print(f"    Name: {lead_name}")

    # Check 5: Duplicates check
    print_section("5. Potential duplicates")
    with db.cursor() as cur:
        # Check for same dataset_id in both tables
        cur.execute("""
            SELECT COUNT(*)
            FROM bitrix_leads bl
            JOIN lead_chat_mapping lcm ON bl.dify_dataset_id = lcm.dify_dataset_id
            WHERE bl.dify_dataset_id IS NOT NULL
              AND lcm.active = true
        """)
        duplicates = cur.fetchone()[0]
        if duplicates > 0:
            print(f"⚠️  Found {duplicates} datasets referenced in BOTH tables")
            print("\nSample duplicates:")
            cur.execute("""
                SELECT bl.diffy_lead_id, lcm.lead_id, bl.dify_dataset_id
                FROM bitrix_leads bl
                JOIN lead_chat_mapping lcm ON bl.dify_dataset_id = lcm.dify_dataset_id
                WHERE bl.dify_dataset_id IS NOT NULL
                  AND lcm.active = true
                LIMIT 5
            """)
            for row in cur.fetchall():
                print(f"  bitrix_leads: {row[0]} | lead_chat_mapping: {row[1]} → {row[2]}")
        else:
            print("✅ No cross-table duplicates found")

    # Check 6: Recommendations
    print_section("6. RECOMMENDATIONS")
    if not has_dify_column:
        print("❌ CRITICAL: Run migration to add dify_dataset_id column to bitrix_leads")
        print("   → Execute: scripts/migrate_fix_bitrix_mapping.sql")
    elif ff or bx_lead or bx_contact:
        print(f"⚠️  WARNING: Found {ff + bx_lead + bx_contact} Bitrix entries in wrong table")
        print("   → Run migration to move them to bitrix_leads")
        print("   → Execute: scripts/migrate_fix_bitrix_mapping.sql")
    else:
        print("✅ Dataset mapping looks correct!")
        print("   No migration needed (or already applied)")

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    main()
