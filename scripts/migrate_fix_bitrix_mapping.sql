-- ============================================================================
-- Migration: Fix Bitrix dataset mapping
-- Date: 2026-03-12
-- Author: Claude (Sonnet 4.6)
--
-- Problem:
--   Bitrix data was using lead_chat_mapping instead of bitrix_leads.dify_dataset_id
--   This caused duplicates and incorrect RAG mappings
--
-- Solution:
--   1. Add dify_dataset_id column to bitrix_leads (if not exists)
--   2. Migrate existing mappings from lead_chat_mapping to bitrix_leads
--   3. Clean up incorrect Bitrix entries from lead_chat_mapping
-- ============================================================================

-- Step 1: Add dify_dataset_id column if it doesn't exist
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_name = 'bitrix_leads' AND column_name = 'dify_dataset_id'
    ) THEN
        ALTER TABLE bitrix_leads ADD COLUMN dify_dataset_id VARCHAR(200);
        CREATE INDEX idx_bitrix_leads_dify_dataset ON bitrix_leads(dify_dataset_id);
        RAISE NOTICE 'Added dify_dataset_id column to bitrix_leads';
    ELSE
        RAISE NOTICE 'dify_dataset_id column already exists in bitrix_leads';
    END IF;
END $$;

-- Step 2: Migrate existing mappings from lead_chat_mapping to bitrix_leads
-- Only for Bitrix-style lead_ids (ФФ-XXXX, BX-LEAD-XXXX, BX-CONTACT-XXXX)
UPDATE bitrix_leads bl
SET dify_dataset_id = lcm.dify_dataset_id
FROM lead_chat_mapping lcm
WHERE bl.diffy_lead_id = lcm.lead_id
  AND lcm.dify_dataset_id IS NOT NULL
  AND bl.dify_dataset_id IS NULL
  AND (
      lcm.lead_id LIKE 'ФФ-%' OR
      lcm.lead_id LIKE 'FF-%' OR
      lcm.lead_id LIKE 'BX-LEAD-%' OR
      lcm.lead_id LIKE 'BX-CONTACT-%'
  );

-- Show migration results
SELECT
    'Migrated datasets' as description,
    COUNT(*) as count
FROM bitrix_leads
WHERE dify_dataset_id IS NOT NULL;

-- Step 3: Remove incorrect Bitrix entries from lead_chat_mapping
-- (keep only Telegram-style numeric lead_ids)
DELETE FROM lead_chat_mapping
WHERE (
    lead_id LIKE 'ФФ-%' OR
    lead_id LIKE 'FF-%' OR
    lead_id LIKE 'BX-LEAD-%' OR
    lead_id LIKE 'BX-CONTACT-%'
);

-- Show cleanup results
SELECT
    'Remaining Telegram mappings' as description,
    COUNT(*) as count
FROM lead_chat_mapping
WHERE active = true;

-- ============================================================================
-- Verification queries (run after migration to check)
-- ============================================================================

-- Check how many Bitrix leads now have datasets
-- SELECT
--     bitrix_entity_type,
--     COUNT(*) as total_leads,
--     COUNT(dify_dataset_id) as with_dataset,
--     ROUND(100.0 * COUNT(dify_dataset_id) / COUNT(*), 2) as coverage_percent
-- FROM bitrix_leads
-- GROUP BY bitrix_entity_type;

-- Check for duplicates (should be 0)
-- SELECT dify_dataset_id, COUNT(*) as cnt
-- FROM bitrix_leads
-- WHERE dify_dataset_id IS NOT NULL
-- GROUP BY dify_dataset_id
-- HAVING COUNT(*) > 1;

-- Verify no Bitrix IDs remain in lead_chat_mapping
-- SELECT COUNT(*) FROM lead_chat_mapping
-- WHERE lead_id LIKE 'ФФ-%' OR lead_id LIKE 'BX-%';
