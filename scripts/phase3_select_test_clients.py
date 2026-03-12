#!/usr/bin/env python3
"""
Phase 3: Select test clients and prepare for test run.

Selects 2 contacts + 2 leads with most activity history for testing.
"""
import sys
import os
from datetime import date

# Add app to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from app.core.db import Database
from app.core.config import settings


def print_section(title: str):
    print(f"\n{'='*70}")
    print(f"  {title}")
    print(f"{'='*70}")


def select_test_contacts(db: Database, limit: int = 10) -> list[dict]:
    """Select contacts with most activity history."""
    with db.cursor() as cur:
        cur.execute("""
            SELECT
                bl.diffy_lead_id,
                bl.name as contact_name,
                bl.contract_number,
                bl.bitrix_lead_id,
                COUNT(DISTINCT bc.id) as calls_count,
                COUNT(DISTINCT be.id) as emails_count,
                COUNT(DISTINCT bco.id) as comments_count,
                COUNT(DISTINCT bs.id) as existing_summaries,
                (COUNT(DISTINCT bc.id) + COUNT(DISTINCT be.id) + COUNT(DISTINCT bco.id)) as total_activities
            FROM bitrix_leads bl
            LEFT JOIN bitrix_calls bc ON bl.diffy_lead_id = bc.diffy_lead_id
            LEFT JOIN bitrix_emails be ON bl.diffy_lead_id = be.diffy_lead_id
            LEFT JOIN bitrix_comments bco ON bl.diffy_lead_id = bco.diffy_lead_id
            LEFT JOIN bitrix_summaries bs ON bl.diffy_lead_id = bs.diffy_lead_id
            WHERE bl.bitrix_entity_type = 'contact'
              AND bl.contract_number IS NOT NULL
            GROUP BY bl.diffy_lead_id, bl.name, bl.contract_number, bl.bitrix_lead_id
            ORDER BY total_activities DESC
            LIMIT %s
        """, (limit,))

        return [
            {
                "diffy_lead_id": row[0],
                "name": row[1],
                "contract_number": row[2],
                "bitrix_lead_id": row[3],
                "calls_count": row[4] or 0,
                "emails_count": row[5] or 0,
                "comments_count": row[6] or 0,
                "existing_summaries": row[7] or 0,
                "total_activities": row[8],
                "type": "contact"
            }
            for row in cur.fetchall()
        ]


def select_test_leads(db: Database, limit: int = 10) -> list[dict]:
    """Select leads with ФФ-number and most activity history."""
    with db.cursor() as cur:
        cur.execute("""
            SELECT
                bl.diffy_lead_id,
                bl.title,
                bl.contract_number,
                bl.bitrix_lead_id,
                COUNT(DISTINCT bc.id) as calls_count,
                COUNT(DISTINCT be.id) as emails_count,
                COUNT(DISTINCT bco.id) as comments_count,
                COUNT(DISTINCT bs.id) as existing_summaries,
                (COUNT(DISTINCT bc.id) + COUNT(DISTINCT be.id) + COUNT(DISTINCT bco.id)) as total_activities
            FROM bitrix_leads bl
            LEFT JOIN bitrix_calls bc ON bl.diffy_lead_id = bc.diffy_lead_id
            LEFT JOIN bitrix_emails be ON bl.diffy_lead_id = be.diffy_lead_id
            LEFT JOIN bitrix_comments bco ON bl.diffy_lead_id = bco.diffy_lead_id
            LEFT JOIN bitrix_summaries bs ON bl.diffy_lead_id = bs.diffy_lead_id
            WHERE bl.bitrix_entity_type = 'lead'
              AND bl.contract_number IS NOT NULL
            GROUP BY bl.diffy_lead_id, bl.title, bl.contract_number, bl.bitrix_lead_id
            ORDER BY total_activities DESC
            LIMIT %s
        """, (limit,))

        return [
            {
                "diffy_lead_id": row[0],
                "title": row[1],
                "contract_number": row[2],
                "bitrix_lead_id": row[3],
                "calls_count": row[4] or 0,
                "emails_count": row[5] or 0,
                "comments_count": row[6] or 0,
                "existing_summaries": row[7] or 0,
                "total_activities": row[8],
                "type": "lead"
            }
            for row in cur.fetchall()
        ]


def print_client_list(clients: list[dict], title: str):
    """Pretty print client list."""
    print(f"\n{title}:")
    print(f"{'#':<4} {'Contract':<15} {'Name/Title':<30} {'Calls':<7} {'Emails':<7} {'Comments':<7} {'Summaries':<7} {'Total':<7}")
    print("-" * 100)

    for i, client in enumerate(clients, 1):
        name = client.get('name') or client.get('title', 'Unknown')
        print(f"{i:<4} {client['contract_number']:<15} {name:<30} "
              f"{client['calls_count']:<7} {client['emails_count']:<7} "
              f"{client['comments_count']:<7} {client['existing_summaries']:<7} "
              f"{client['total_activities']:<7}")


def generate_cleanup_instructions(test_clients: list[dict]) -> str:
    """Generate SQL commands for cleanup."""
    diffy_ids = ", ".join([f"'{c['diffy_lead_id']}'" for c in test_clients])

    cleanup_sql = f"""
-- ============================================================================
-- Cleanup Instructions for Test Run
-- Test Clients: {len(test_clients)} total
-- {", ".join([c['diffy_lead_id'] for c in test_clients])}
-- ============================================================================

-- Step 1: Delete summaries for test clients only
DELETE FROM bitrix_summaries
WHERE diffy_lead_id IN ({diffy_ids});

-- Step 2: Clear dataset mappings for test clients
UPDATE bitrix_leads
SET dify_dataset_id = NULL
WHERE diffy_lead_id IN ({diffy_ids});

-- Step 3: Verify cleanup complete
SELECT
    diffy_lead_id,
    COUNT(*) as summaries_remaining
FROM bitrix_summaries
WHERE diffy_lead_id IN ({diffy_ids})
GROUP BY diffy_lead_id;
-- Expected: 0 rows (no summaries remaining)

-- Step 4: Manually delete corresponding Dify datasets
-- Via Dify UI: https://dify-ff.duckdns.org
-- Knowledge > Datasets > Delete each dataset for: {", ".join([c['contract_number'] for c in test_clients if c.get('contract_number')])}
"""
    return cleanup_sql


def main():
    db = Database(settings.db_dsn)

    print_section("PHASE 3: TEST CLIENT SELECTION")

    # Select candidates
    contacts = select_test_contacts(db, limit=10)
    leads = select_test_leads(db, limit=10)

    # Display options
    print_client_list(contacts[:10], "Top 10 Contacts (by activity)")
    print_client_list(leads[:10], "Top 10 Leads (by activity)")

    # Select test clients
    print_section("SELECTED TEST CLIENTS")

    # Select 2 contacts with most activity
    test_contacts = contacts[:2]
    print_client_list(test_contacts, "✅ Selected Contacts (2)")

    # Select 2 leads with most activity
    test_leads = leads[:2]
    print_client_list(test_leads, "✅ Selected Leads (2)")

    # Combine
    all_test_clients = test_contacts + test_leads

    print_section("SELECTION SUMMARY")
    print(f"Total test clients: {len(all_test_clients)}")
    print(f"  - Contacts: {len(test_contacts)}")
    print(f"  - Leads: {len(test_leads)}")
    print(f"\nTotal activities to process:")
    for client in all_test_clients:
        print(f"  {client['diffy_lead_id']}: {client['total_activities']} activities "
              f"({client['calls_count']} calls, {client['emails_count']} emails, "
              f"{client['comments_count']} comments)")

    # Generate cleanup script
    print_section("CLEANUP INSTRUCTIONS")
    cleanup_sql = generate_cleanup_instructions(all_test_clients)

    # Save to file
    cleanup_file = os.path.join(os.path.dirname(__file__), f"phase3_cleanup_test_{date.today().isoformat()}.sql")
    with open(cleanup_file, 'w', encoding='utf-8') as f:
        f.write(cleanup_sql)

    print(f"\n✅ Cleanup SQL saved to: {cleanup_file}")
    print("\nNext steps:")
    print("1. Review selected clients above")
    print("2. Backup database: docker exec mvp-auto-summary-postgres-1 pg_dump -U n8n n8n > backup.sql")
    print(f"3. Run cleanup: {cleanup_file}")
    print("4. Manually delete Dify datasets via UI")
    print("5. Run sync for test clients only")
    print("6. Verify results")

    print("\n" + "="*70 + "\n")


if __name__ == "__main__":
    main()
