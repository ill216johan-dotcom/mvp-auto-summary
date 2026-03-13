"""
Test script for End-to-End verification of Bitrix sync and transcription
on 4 specific clients: 2 contacts and 2 leads.

Clients:
- Contact 5723 (ФФ-4405)
- Contact 5669 (ФФ-2511)
- Lead 24800 (BX-LEAD-24800)
- Lead 24850 (BX-LEAD-24850)

Run inside container:
docker exec mvp-auto-summary-orchestrator-1 python /app/scripts/run_test_4_clients.py
"""
import sys
import os
from datetime import datetime

sys.path.insert(0, "/app")

from app.config import get_settings
from app.core.db import Database
from app.core.llm import LLMClient
from app.core.dify_api import DifyClient
from app.integrations.bitrix24 import Bitrix24Client
from app.tasks.bitrix_sync import sync_calls, sync_emails, sync_comments, _enrich_call_record_urls
from app.tasks.bitrix_summary import transcribe_pending_calls, generate_bitrix_summaries

TEST_LEADS = [
    {"bitrix_lead_id": 5723, "diffy_lead_id": "ФФ-4405", "bitrix_entity_type": "contact"},
    {"bitrix_lead_id": 5669, "diffy_lead_id": "ФФ-2511", "bitrix_entity_type": "contact"},
    {"bitrix_lead_id": 24800, "diffy_lead_id": "BX-LEAD-24800", "bitrix_entity_type": "lead"},
    {"bitrix_lead_id": 24850, "diffy_lead_id": "BX-LEAD-24850", "bitrix_entity_type": "lead"},
]

def main():
    print("=== TEST RUN: 4 CLIENTS ===")
    settings = get_settings()
    db = Database(settings.database_dsn)
    llm = LLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
    dify = DifyClient(settings.dify_api_key, settings.dify_base_url)
    bitrix_client = Bitrix24Client(settings.bitrix_webhook_url)

    try:
        # 1. Clean up old data for these 4 clients
        print("\n--- 1. CLEANUP ---")
        with db.connection() as conn:
            cur = conn.cursor()
            diffy_ids = tuple(l['diffy_lead_id'] for l in TEST_LEADS)
            
            cur.execute("DELETE FROM bitrix_summaries WHERE diffy_lead_id IN %s", (diffy_ids,))
            print(f"Deleted {cur.rowcount} old summaries")
            
            cur.execute("UPDATE bitrix_leads SET dify_dataset_id = NULL WHERE diffy_lead_id IN %s", (diffy_ids,))
            print("Reset dify_dataset_id mappings")
            
            # Reset transcript status so we re-transcribe
            cur.execute("""
                UPDATE bitrix_calls 
                SET transcript_status = 'pending', transcript_text = NULL 
                WHERE diffy_lead_id IN %s AND record_file_id IS NOT NULL
            """, (diffy_ids,))
            print(f"Reset {cur.rowcount} calls back to pending for transcription")
            
            conn.commit()

        # 2. Sync activities
        print("\n--- 2. SYNC ACTIVITIES ---")
        with db.connection() as conn:
            print("Syncing calls...")
            call_res = sync_calls(bitrix_client, conn, TEST_LEADS)
            print(f"  Result: {call_res}")
            
            print("Syncing emails...")
            email_res = sync_emails(bitrix_client, conn, TEST_LEADS)
            print(f"  Result: {email_res}")
            
            print("Syncing comments...")
            comm_res = sync_comments(bitrix_client, conn, TEST_LEADS)
            print(f"  Result: {comm_res}")

        # 3. Transcribe pending calls
        print("\n--- 3. TRANSCRIBE CALLS (Whisper) ---")
        print("This will take a while if there are many recordings (CPU Whisper)")
        # Run loop to process all pending
        total_transcribed = 0
        while True:
            t_res = transcribe_pending_calls(
                db=db,
                transcribe_url=settings.transcribe_url,
                limit=10,
                bitrix_webhook_url=settings.bitrix_webhook_url,
                whisper_url=settings.whisper_url
            )
            total_transcribed += t_res.get('transcribed', 0)
            if t_res.get('transcribed', 0) == 0 and t_res.get('no_source', 0) == 0:
                # nothing left to process
                break
            
        print(f"Total transcribed: {total_transcribed}")

        # 4. Generate Summaries & Push to Dify
        print("\n--- 4. GENERATE SUMMARIES & DIFY PUSH ---")
        # We temporarily mock get_bitrix_leads_for_sync to only return our 4 leads
        original_get_leads = db.get_bitrix_leads_for_sync
        
        def mock_get_leads():
            with db.connection() as conn:
                cur = conn.cursor(cursor_factory=__import__('psycopg2').extras.RealDictCursor)
                cur.execute("SELECT * FROM bitrix_leads WHERE diffy_lead_id IN %s", (diffy_ids,))
                return cur.fetchall()
                
        db.get_bitrix_leads_for_sync = mock_get_leads
        
        sum_res = generate_bitrix_summaries(db, llm, dify)
        print(f"Summary result: {sum_res}")

        # Restore original function
        db.get_bitrix_leads_for_sync = original_get_leads

        print("\n=== TEST COMPLETED SUCCESSFULLY ===")
        print("Please check Dify datasets to verify the result.")

    except Exception as e:
        print(f"\n❌ TEST FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        bitrix_client.close()
        db.close()

if __name__ == "__main__":
    main()
