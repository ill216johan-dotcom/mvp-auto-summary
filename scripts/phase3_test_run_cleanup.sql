-- ============================================================================
-- Phase 3: Test Run Preparation - Clean Slate
-- Date: 2026-03-12
-- Author: Claude (Sonnet 4.6)
--
-- Purpose: Prepare for test run with ONLY 2 leads + 2 contacts
-- Steps:
-- 1. Backup current state (manual - user should run pg_dump before this!)
-- 2. Delete ALL summaries and clear dataset mappings
-- 3. Manually delete Dify datasets via API/UI
-- 4. Test with selected clients only
-- ============================================================================

-- ⚠️  WARNING: This will DELETE all summaries!
-- Make sure to backup first:
-- docker exec mvp-auto-summary-postgres-1 pg_dump -U n8n n8n > backup_before_test_$(date +%Y%m%d).sql

-- ============================================================================
-- STEP 1: Delete all Bitrix summaries
-- ============================================================================

DELETE FROM bitrix_summaries;

-- Verify
-- SELECT COUNT(*) as summaries_remaining FROM bitrix_summaries;
-- Expected: 0

-- ============================================================================
-- STEP 2: Clear all dataset mappings
-- ============================================================================

-- Clear Bitrix dataset mappings
UPDATE bitrix_leads SET dify_dataset_id = NULL;

-- Clear Telegram dataset mappings (for cleanliness)
UPDATE lead_chat_mapping SET dify_dataset_id = NULL;

-- Clear client registry dataset mappings
UPDATE client_registry SET dify_dataset_id = NULL;

-- Verify
-- SELECT COUNT(*) as datasets_in_leads FROM bitrix_leads WHERE dify_dataset_id IS NOT NULL;
-- SELECT COUNT(*) as datasets_in_mapping FROM lead_chat_mapping WHERE dify_dataset_id IS NOT NULL;
-- Expected: 0 for both

-- ============================================================================
-- STEP 3: Select test clients (2 leads + 2 contacts)
-- ============================================================================

-- Test Contacts (choose 2 with most history)
-- Criteria: Has contract, has activities, different from leads

-- Find contacts with most activities
SELECT
    bl.diffy_lead_id,
    bl.name as contact_name,
    bl.contract_number,
    COUNT(DISTINCT bc.id) as calls_count,
    COUNT(DISTINCT be.id) as emails_count,
    COUNT(DISTINCT bco.id) as comments_count,
    (COUNT(DISTINCT bc.id) + COUNT(DISTINCT be.id) + COUNT(DISTINCT bco.id)) as total_activities
FROM bitrix_leads bl
LEFT JOIN bitrix_calls bc ON bl.diffy_lead_id = bc.diffy_lead_id
LEFT JOIN bitrix_emails be ON bl.diffy_lead_id = be.diffy_lead_id
LEFT JOIN bitrix_comments bco ON bl.diffy_lead_id = bco.diffy_lead_id
WHERE bl.bitrix_entity_type = 'contact'
  AND bl.contract_number IS NOT NULL
GROUP BY bl.diffy_lead_id, bl.name, bl.contract_number
ORDER BY total_activities DESC
LIMIT 10;

-- Test Leads (choose 2 with ФФ-number)
-- Criteria: Has ФФ in title, has activities

-- Find leads with ФФ-number and most activities
SELECT
    bl.diffy_lead_id,
    bl.title,
    bl.contract_number,
    COUNT(DISTINCT bc.id) as calls_count,
    COUNT(DISTINCT be.id) as emails_count,
    COUNT(DISTINCT bco.id) as comments_count,
    (COUNT(DISTINCT bc.id) + COUNT(DISTINCT be.id) + COUNT(DISTINCT bco.id)) as total_activities
FROM bitrix_leads bl
LEFT JOIN bitrix_calls bc ON bl.diffy_lead_id = bc.diffy_lead_id
LEFT JOIN bitrix_emails be ON bl.diffy_lead_id = be.diffy_lead_id
LEFT JOIN bitrix_comments bco ON bl.diffy_lead_id = bco.diffy_lead_id
WHERE bl.bitrix_entity_type = 'lead'
  AND bl.contract_number IS NOT NULL
GROUP BY bl.diffy_lead_id, bl.title, bl.contract_number
ORDER BY total_activities DESC
LIMIT 10;

-- ============================================================================
-- STEP 4: Manual Dify Dataset Cleanup
-- ============================================================================

-- After running this SQL script, manually delete Dify datasets:
-- Option 1: Via Dify UI
--   1. Open https://dify-ff.duckdns.org
--   2. Go to Knowledge > Datasets
--   3. Delete all Bitrix-related datasets (ФФ-*, BX-LEAD-*, BX-CONTACT-*)
--   4. Keep Telegram datasets if needed

-- Option 2: Via API (requires dataset API key)
-- curl -X GET 'https://dify-ff.duckdns.org/v1/datasets?page=1&limit=100' \
--   -H 'Authorization: Bearer dataset-YOUR_KEY'
-- # Extract IDs and delete each:
-- curl -X DELETE 'https://dify-ff.duckdns.org/v1/datasets/{dataset_id}' \
--   -H 'Authorization: Bearer dataset-YOUR_KEY'

-- ============================================================================
-- STEP 5: Verify Clean State
-- ============================================================================

-- Check all tables are clean
DO $$
DECLARE
    summaries_count INT;
    leads_datasets_count INT;
    mapping_datasets_count INT;
BEGIN
    SELECT COUNT(*) INTO summaries_count FROM bitrix_summaries;
    SELECT COUNT(*) INTO leads_datasets_count FROM bitrix_leads WHERE dify_dataset_id IS NOT NULL;
    SELECT COUNT(*) INTO mapping_datasets_count FROM lead_chat_mapping WHERE dify_dataset_id IS NOT NULL;

    RAISE NOTICE '=== Clean State Verification ===';
    RAISE NOTICE 'Summaries: % (expected: 0)', summaries_count;
    RAISE NOTICE 'Bitrix datasets: % (expected: 0)', leads_datasets_count;
    RAISE NOTICE 'Mapping datasets: % (expected: 0)', mapping_datasets_count;

    IF summaries_count = 0 AND leads_datasets_count = 0 AND mapping_datasets_count = 0 THEN
        RAISE NOTICE '✅ System is clean - ready for test run!';
    ELSE
        RAISE NOTICE '⚠️  WARNING: System is not completely clean!';
    END IF;
END $$;

-- ============================================================================
-- STEP 6: Prepare Test Run (example)
-- ============================================================================

-- After selecting test clients, update their dataset mappings after creation
-- Example (replace with actual diffy_lead_ids from STEP 3):

-- UPDATE bitrix_leads SET dify_dataset_id = 'new-dataset-uuid-1'
-- WHERE diffy_lead_id = 'ФФ-4405';

-- UPDATE bitrix_leads SET dify_dataset_id = 'new-dataset-uuid-2'
-- WHERE diffy_lead_id = 'ФФ-2577';

-- UPDATE bitrix_leads SET dify_dataset_id = 'new-dataset-uuid-3'
-- WHERE diffy_lead_id = 'BX-LEAD-47988';

-- UPDATE bitrix_leads SET dify_dataset_id = 'new-dataset-uuid-4'
-- WHERE diffy_lead_id = 'BX-LEAD-49000';

-- ============================================================================
-- Next Steps (After Test Selection)
-- ============================================================================

-- 1. Select test clients from queries above
-- 2. Create Dify datasets manually or let system create them
-- 3. Run bitrix sync for test clients only
-- 4. Verify:
--    - Summaries generated
--    - Documents uploaded to correct datasets
--    - No duplicate datasets created
--    - RAG search works by contract number

-- To run sync for test clients only, use Python:
-- from app.tasks.bitrix_summary import generate_bitrix_summaries
-- from app.core.db import Database
-- from app.core.llm import LLMClient
-- from app.core.dify_api import DifyClient
-- from app.core.config import settings
--
-- db = Database(settings.db_dsn)
-- llm = LLMClient(api_key=settings.llm_api_key, base_url=settings.llm_base_url, model=settings.llm_model)
-- dify = DifyClient(api_key=settings.dify_dataset_api_key, base_url=settings.dify_api_url)
--
-- # Temporarily limit to test clients (uncomment and modify)
-- # UPDATE bitrix_leads SET last_synced_at = NULL WHERE diffy_lead_id IN ('ФФ-4405', 'ФФ-2577', 'BX-LEAD-47988', 'BX-LEAD-49000');
#
-- stats = generate_bitrix_summaries(db, llm, dify, target_date=None)
-- print(stats)
