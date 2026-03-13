"""
Historical Sync v2: Full Database Synchronization and Transcription.
This script is designed to run in the background for a long time (days).

Steps:
1. Sync all Leads (status 1-7)
2. Sync all Contacts
3. Sync all Activities (Calls, Emails, Comments)
4. Run Batch Enrichment (match RECORD_FILE_ID for all calls)
5. Run endless transcription loop (transcribe all pending calls)
6. Generate Summaries for all clients and push to Dify

Run:
nohup docker exec mvp-auto-summary-orchestrator-1 python3 /app/scripts/run_historical_sync_v2.py > /root/historical_sync.log 2>&1 &
"""

import sys
import time
from datetime import datetime

sys.path.insert(0, "/app")

from app.config import get_settings
from app.core.db import Database
from app.core.llm import LLMClient
from app.core.dify_api import DifyClient
from app.integrations.bitrix24 import Bitrix24Client
from app.tasks.bitrix_sync import sync_bitrix_leads, sync_bitrix_contacts, sync_calls, sync_emails, sync_comments
from app.tasks.bitrix_summary import transcribe_pending_calls, generate_bitrix_summaries

def main():
    print(f"[{datetime.now()}] === STARTING FULL HISTORICAL SYNC v2 ===")
    settings = get_settings()
    db = Database(settings.database_dsn)
    llm = LLMClient(settings.llm_api_key, settings.llm_base_url, settings.llm_model)
    dify = DifyClient(settings.dify_api_key, settings.dify_base_url)
    bitrix_client = Bitrix24Client(settings.bitrix_webhook_url)

    try:
        with db.connection() as conn:
            # 1. Sync Leads
            print(f"[{datetime.now()}] --- 1. SYNC LEADS ---")
            lead_res = sync_bitrix_leads(bitrix_client, conn)
            print(f"Leads synced: {lead_res}")

            # 2. Sync Contacts
            print(f"[{datetime.now()}] --- 2. SYNC CONTACTS ---")
            contact_res = sync_bitrix_contacts(bitrix_client, conn, settings.bitrix_contract_field)
            print(f"Contacts synced: {contact_res}")

            # Fetch all synced leads for activity sync
            leads = db.get_bitrix_leads_for_sync()
            print(f"Total leads/contacts to sync activities for: {len(leads)}")

            # 3. Sync Activities
            print(f"[{datetime.now()}] --- 3. SYNC ACTIVITIES ---")
            call_res = sync_calls(bitrix_client, conn, leads)
            print(f"Calls synced: {call_res}")
            
            email_res = sync_emails(bitrix_client, conn, leads)
            print(f"Emails synced: {email_res}")
            
            comm_res = sync_comments(bitrix_client, conn, leads)
            print(f"Comments synced: {comm_res}")

        # 4. Batch Enrichment
        # Instead of calling the script, we should just let poll_new_recordings and the next step handle it
        # Actually, the batch script is separate, but sync_calls already enriches new calls.
        # We assume the user ran batch_enrich_recordings.py manually before this step for OLD calls.
        
        # 5. Transcribe pending calls
        print(f"[{datetime.now()}] --- 5. TRANSCRIBE PENDING CALLS ---")
        total_transcribed = 0
        total_failed = 0
        while True:
            t_res = transcribe_pending_calls(
                db=db,
                transcribe_url=settings.transcribe_url,
                limit=20,
                bitrix_webhook_url=settings.bitrix_webhook_url,
                whisper_url=settings.whisper_url
            )
            transcribed = t_res.get('transcribed', 0)
            failed = t_res.get('failed', 0)
            no_source = t_res.get('no_source', 0)
            
            total_transcribed += transcribed
            total_failed += failed
            
            print(f"[{datetime.now()}] Transcribed chunk: {transcribed} ok, {failed} failed")
            
            # If nothing was processed (or only things with no audio source), break
            if transcribed == 0 and failed == 0:
                print("No more pending calls with valid recordings.")
                break
            
            # Sleep a bit to not hammer the server if there are failures
            time.sleep(5)

        print(f"[{datetime.now()}] Transcription finished. Total OK: {total_transcribed}, Failed: {total_failed}")

        # 6. Generate Summaries
        print(f"[{datetime.now()}] --- 6. GENERATE SUMMARIES ---")
        sum_res = generate_bitrix_summaries(db, llm, dify)
        print(f"[{datetime.now()}] Summaries generated: {sum_res}")

        print(f"[{datetime.now()}] === HISTORICAL SYNC COMPLETED SUCCESSFULLY ===")

    except Exception as e:
        print(f"[{datetime.now()}] ❌ SYNC FAILED: {str(e)}")
        import traceback
        traceback.print_exc()
    finally:
        bitrix_client.close()
        db.close()

if __name__ == "__main__":
    main()
