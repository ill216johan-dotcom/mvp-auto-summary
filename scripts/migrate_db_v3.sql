-- ============================================================
-- MVP Auto-Summary: Database Migration v3 — Bitrix24 CRM Sync
-- Дата: 2026-03-09
-- Применить: docker exec mvp-autosummary-postgres-1 psql -U n8n -d n8n -f /scripts/migrate_db_v3.sql
-- ============================================================

-- 1. bitrix_leads: маппинг Bitrix сущностей → Diffy лидов
CREATE TABLE IF NOT EXISTS bitrix_leads (
    id                  SERIAL PRIMARY KEY,
    bitrix_lead_id      INTEGER NOT NULL UNIQUE,
    bitrix_entity_type  VARCHAR(20) NOT NULL DEFAULT 'lead',
    diffy_lead_id       VARCHAR(50),
    title               VARCHAR(500),
    name                VARCHAR(200),
    phone               VARCHAR(100),
    email               VARCHAR(200),
    status_id           VARCHAR(50),
    source_id           VARCHAR(50),
    responsible_id      INTEGER,
    responsible_name    VARCHAR(200),
    contract_number     VARCHAR(100),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    last_synced_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bitrix_leads_diffy_lead_id ON bitrix_leads(diffy_lead_id);
CREATE INDEX IF NOT EXISTS idx_bitrix_leads_contract_number ON bitrix_leads(contract_number);

-- 2. bitrix_calls: звонки из CRM
CREATE TABLE IF NOT EXISTS bitrix_calls (
    id                  SERIAL PRIMARY KEY,
    bitrix_activity_id  INTEGER NOT NULL UNIQUE,
    bitrix_call_id      VARCHAR(100),
    bitrix_lead_id      INTEGER,
    diffy_lead_id       VARCHAR(50),
    direction           INTEGER,
    phone_number        VARCHAR(100),
    call_duration       INTEGER,
    call_date           TIMESTAMPTZ,
    responsible_id      INTEGER,
    responsible_name    VARCHAR(200),
    record_url          TEXT,
    transcript_text     TEXT,
    transcript_status   VARCHAR(20) DEFAULT 'pending',
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bitrix_calls_diffy_lead_id ON bitrix_calls(diffy_lead_id);
CREATE INDEX IF NOT EXISTS idx_bitrix_calls_transcript_status ON bitrix_calls(transcript_status);
CREATE INDEX IF NOT EXISTS idx_bitrix_calls_call_date ON bitrix_calls(call_date);

-- 3. bitrix_emails: письма из CRM (с полным текстом)
CREATE TABLE IF NOT EXISTS bitrix_emails (
    id                  SERIAL PRIMARY KEY,
    bitrix_activity_id  INTEGER NOT NULL UNIQUE,
    bitrix_lead_id      INTEGER,
    diffy_lead_id       VARCHAR(50),
    direction           INTEGER,
    subject             VARCHAR(1000),
    email_body          TEXT,
    email_from          VARCHAR(500),
    email_to            VARCHAR(500),
    email_date          TIMESTAMPTZ,
    responsible_id      INTEGER,
    responsible_name    VARCHAR(200),
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bitrix_emails_diffy_lead_id ON bitrix_emails(diffy_lead_id);
CREATE INDEX IF NOT EXISTS idx_bitrix_emails_email_date ON bitrix_emails(email_date);

-- 4. bitrix_comments: комментарии сотрудников из таймлайна
CREATE TABLE IF NOT EXISTS bitrix_comments (
    id                  SERIAL PRIMARY KEY,
    bitrix_comment_id   INTEGER NOT NULL UNIQUE,
    bitrix_lead_id      INTEGER,
    diffy_lead_id       VARCHAR(50),
    comment_text        TEXT,
    author_id           INTEGER,
    author_name         VARCHAR(200),
    comment_date        TIMESTAMPTZ,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_bitrix_comments_diffy_lead_id ON bitrix_comments(diffy_lead_id);
CREATE INDEX IF NOT EXISTS idx_bitrix_comments_comment_date ON bitrix_comments(comment_date);

-- 5. bitrix_sync_log: журнал синхронизаций
CREATE TABLE IF NOT EXISTS bitrix_sync_log (
    id                  SERIAL PRIMARY KEY,
    sync_type           VARCHAR(30) DEFAULT 'full',
    status              VARCHAR(20) DEFAULT 'started',
    leads_synced        INTEGER DEFAULT 0,
    calls_synced        INTEGER DEFAULT 0,
    emails_synced       INTEGER DEFAULT 0,
    comments_synced     INTEGER DEFAULT 0,
    error_message       TEXT,
    started_at          TIMESTAMPTZ DEFAULT NOW(),
    completed_at        TIMESTAMPTZ
);

-- 6. bitrix_summaries: ежедневные саммари по лидам Битрикса
CREATE TABLE IF NOT EXISTS bitrix_summaries (
    id                  SERIAL PRIMARY KEY,
    diffy_lead_id       VARCHAR(50) NOT NULL,
    summary_date        DATE NOT NULL,
    calls_count         INTEGER DEFAULT 0,
    emails_count        INTEGER DEFAULT 0,
    comments_count      INTEGER DEFAULT 0,
    summary_text        TEXT,
    dify_doc_id         VARCHAR(200),
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(diffy_lead_id, summary_date)
);

CREATE INDEX IF NOT EXISTS idx_bitrix_summaries_diffy_lead_id ON bitrix_summaries(diffy_lead_id);
CREATE INDEX IF NOT EXISTS idx_bitrix_summaries_summary_date ON bitrix_summaries(summary_date);

SELECT 'Migration v3 completed — Bitrix24 tables created' AS result;
