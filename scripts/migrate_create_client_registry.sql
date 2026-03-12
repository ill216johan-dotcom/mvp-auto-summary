-- ============================================================================
-- Migration: Create Unified Client Registry
-- Date: 2026-03-12
-- Author: Claude (Sonnet 4.6)
--
-- Purpose: Single source of truth for client identity across all systems
-- Links: Bitrix IDs + Telegram IDs + Jitsi IDs + Dify datasets
--
-- Phases:
-- 1. Create table structure
-- 2. Populate from existing data (bitrix_leads, lead_chat_mapping, processed_files)
-- 3. Create indexes for performance
-- ============================================================================

-- Step 1: Create client_registry table
CREATE TABLE IF NOT EXISTS client_registry (
    id SERIAL PRIMARY KEY,

    -- Bitrix24 IDs
    bitrix_lead_id INTEGER,
    bitrix_contact_id INTEGER,
    diffy_lead_id VARCHAR(100) UNIQUE,  -- ФФ-4405, BX-LEAD-12345, BX-CONTACT-67890

    -- Legacy IDs (Jitsi, Telegram)
    telegram_lead_id VARCHAR(50),  -- 4405 (число)
    legacy_lead_id VARCHAR(100),  -- LEAD-ID from Jitsi filenames

    -- Client info
    legal_name VARCHAR(500),  -- ООО "Омникс"
    contract_numbers TEXT[],  -- ['ФФ-4405', 'ФФ-2577']
    active_contract VARCHAR(100),  -- ФФ-4405 (текущий)

    -- Contact info
    phone VARCHAR(100),
    email VARCHAR(200),

    -- Dify mapping
    dify_dataset_id VARCHAR(200) UNIQUE,

    -- Metadata
    source_system VARCHAR(50),  -- 'bitrix', 'telegram', 'jitsi', 'merged'
    data_quality VARCHAR(20),  -- 'high', 'medium', 'low'
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW(),

    -- Notes
    notes TEXT
);

-- Step 2: Create indexes for performance
CREATE INDEX IF NOT EXISTS idx_client_registry_diffy ON client_registry(diffy_lead_id);
CREATE INDEX IF NOT EXISTS idx_client_registry_telegram ON client_registry(telegram_lead_id);
CREATE INDEX IF NOT EXISTS idx_client_registry_legacy ON client_registry(legacy_lead_id);
CREATE INDEX IF NOT EXISTS idx_client_registry_contracts ON client_registry USING GIN(contract_numbers);
CREATE INDEX IF NOT EXISTS idx_client_registry_legal ON client_registry(legal_name);
CREATE INDEX IF NOT EXISTS idx_client_registry_dataset ON client_registry(dify_dataset_id);

-- Full-text search on legal name
CREATE INDEX IF NOT EXISTS idx_client_registry_name_fts ON client_registry
USING GIN(to_tsvector('russian', legal_name));

-- Step 3: Populate from bitrix_leads (PRIMARY SOURCE)
INSERT INTO client_registry (
    bitrix_lead_id,
    bitrix_contact_id,
    diffy_lead_id,
    legal_name,
    contract_numbers,
    active_contract,
    phone,
    email,
    dify_dataset_id,
    source_system,
    data_quality
)
SELECT
    bl.bitrix_lead_id,
    CASE WHEN bl.bitrix_entity_type = 'contact' THEN bl.bitrix_lead_id ELSE NULL END,
    bl.diffy_lead_id,
    COALESCE(bl.name, bl.title, 'Unknown'),
    CASE WHEN bl.contract_number IS NOT NULL THEN ARRAY[bl.contract_number] ELSE NULL END,
    bl.contract_number,
    bl.phone,
    bl.email,
    bl.dify_dataset_id,
    'bitrix',
    CASE
        WHEN bl.contract_number IS NOT NULL THEN 'high'
        WHEN bl.name IS NOT NULL THEN 'medium'
        ELSE 'low'
    END
FROM bitrix_leads bl
ON CONFLICT (diffy_lead_id) DO NOTHING;

-- Step 4: Link Telegram IDs from lead_chat_mapping
UPDATE client_registry cr
SET
    telegram_lead_id = lcm.lead_id,
    updated_at = NOW(),
    notes = COALESCE(cr.notes, '') || ' Linked from Telegram chat mapping.'
FROM lead_chat_mapping lcm
WHERE cr.diffy_lead_id = lcm.lead_id
  AND lcm.active = true
  AND cr.telegram_lead_id IS NULL;

-- Step 5: Extract contract numbers from lead titles (for leads without explicit contract)
UPDATE client_registry
SET
    contract_numbers = CASE
        WHEN contract_numbers IS NULL THEN ARRAY[substring(diffy_lead_id from 'ФФ-[0-9]+')]
        ELSE contract_numbers
    END,
    active_contract = COALESCE(active_contract, substring(diffy_lead_id from 'ФФ-[0-9]+')),
    updated_at = NOW()
WHERE diffy_lead_id ~ 'ФФ-[0-9]+'
  AND contract_numbers IS NULL;

-- Step 6: Create trigger for updated_at
CREATE OR REPLACE FUNCTION update_client_registry_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS client_registry_updated_at ON client_registry;
CREATE TRIGGER client_registry_updated_at
    BEFORE UPDATE ON client_registry
    FOR EACH ROW
    EXECUTE FUNCTION update_client_registry_updated_at();

-- Step 7: Verify results
SELECT
    'Total clients' as description,
    COUNT(*) as count
FROM client_registry

UNION ALL

SELECT
    'With contract numbers',
    COUNT(*)
FROM client_registry
WHERE contract_numbers IS NOT NULL

UNION ALL

SELECT
    'With Dify datasets',
    COUNT(*)
FROM client_registry
WHERE dify_dataset_id IS NOT NULL

UNION ALL

SELECT
    'With Telegram links',
    COUNT(*)
FROM client_registry
WHERE telegram_lead_id IS NOT NULL

UNION ALL

SELECT
    'High quality',
    COUNT(*)
FROM client_registry
WHERE data_quality = 'high';

-- ============================================================================
-- Example queries for Phase 3 (test run)
-- ============================================================================

-- Find ФФ-4405 client (contact with most history)
-- SELECT * FROM client_registry WHERE diffy_lead_id = 'ФФ-4405';

-- Find test candidates (contacts with contracts)
-- SELECT diffy_lead_id, legal_name, array_length(contract_numbers, 1) as contracts_count
-- FROM client_registry
-- WHERE bitrix_contact_id IS NOT NULL
--   AND contract_numbers IS NOT NULL
-- ORDER BY array_length(contract_numbers, 1) DESC
-- LIMIT 10;

-- Find test candidates (leads with ФФ-number)
-- SELECT diffy_lead_id, legal_name, active_contract
-- FROM client_registry
-- WHERE bitrix_lead_id IS NOT NULL
--   AND bitrix_contact_id IS NULL
--   AND active_contract IS NOT NULL
-- LIMIT 10;
