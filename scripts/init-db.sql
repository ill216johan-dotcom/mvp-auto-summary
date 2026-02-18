-- ============================================================
-- MVP Auto-Summary: PostgreSQL initialization
-- Runs automatically on first docker-compose up
-- ============================================================

-- Table: processed_files
-- Tracks all recordings to ensure idempotent processing
-- (no double transcription, no missed files)
CREATE TABLE IF NOT EXISTS processed_files (
    id              SERIAL PRIMARY KEY,
    filename        VARCHAR(500) NOT NULL UNIQUE,
    filepath        VARCHAR(1000) NOT NULL,
    lead_id         VARCHAR(100),
    file_date       DATE,
    file_size_bytes BIGINT,

    -- Processing status
    status          VARCHAR(50) NOT NULL DEFAULT 'new',
    -- Possible values: new, converting, uploading, transcribing, saving, completed, error

    -- Yandex SpeechKit
    s3_key          VARCHAR(500),
    operation_id    VARCHAR(200),
    transcript_text TEXT,

    -- open-notebook
    notebook_id     VARCHAR(200),
    source_id       VARCHAR(200),

    -- Summary (from GLM-4)
    summary_text    TEXT,
    summary_sent    BOOLEAN DEFAULT FALSE,

    -- Error tracking
    error_message   TEXT,
    retry_count     INTEGER DEFAULT 0,

    -- Timestamps
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ
);

-- Indexes for common queries
CREATE INDEX IF NOT EXISTS idx_processed_files_status ON processed_files(status);
CREATE INDEX IF NOT EXISTS idx_processed_files_lead_id ON processed_files(lead_id);
CREATE INDEX IF NOT EXISTS idx_processed_files_file_date ON processed_files(file_date);
CREATE INDEX IF NOT EXISTS idx_processed_files_created_at ON processed_files(created_at);

-- Function: auto-update updated_at on row change
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ language 'plpgsql';

CREATE OR REPLACE TRIGGER update_processed_files_updated_at
    BEFORE UPDATE ON processed_files
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ============================================================
-- View: today's processing summary (for daily digest workflow)
-- ============================================================
CREATE OR REPLACE VIEW v_today_completed AS
SELECT
    id,
    filename,
    lead_id,
    transcript_text,
    summary_text,
    summary_sent,
    notebook_id,
    source_id,
    completed_at
FROM processed_files
WHERE file_date = CURRENT_DATE
  AND status = 'completed'
ORDER BY completed_at;

-- ============================================================
-- View: stuck/error files (for monitoring)
-- ============================================================
CREATE OR REPLACE VIEW v_stuck_files AS
SELECT
    id,
    filename,
    lead_id,
    status,
    error_message,
    retry_count,
    created_at,
    updated_at
FROM processed_files
WHERE status = 'error'
   OR (status NOT IN ('completed', 'error', 'new') AND updated_at < NOW() - INTERVAL '1 hour')
ORDER BY updated_at;
