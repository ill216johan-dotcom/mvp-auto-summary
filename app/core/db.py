# pyright: reportMissingModuleSource=false
"""
PostgreSQL database layer with connection pooling.

Replaces:
- Scattered psycopg2.connect() calls in every script
- n8n Postgres nodes (executeQuery)
- Direct DB manipulation scripts

All SQL queries used across WF01-WF06 are consolidated here.
"""
from __future__ import annotations

from contextlib import contextmanager
from datetime import date
from typing import Any


from app.core.logger import get_logger

log = get_logger("db")


class Database:
    """Thread-safe PostgreSQL connection pool with query methods."""

    def __init__(self, dsn: str, min_conn: int = 2, max_conn: int = 10) -> None:
        from psycopg2 import pool

        self._pool = pool.ThreadedConnectionPool(min_conn, max_conn, dsn)
        log.info("db_pool_created", min_conn=min_conn, max_conn=max_conn)

    @contextmanager
    def connection(self):
        """Get a connection from the pool (auto-commit on success, rollback on error)."""
        conn = self._pool.getconn()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            self._pool.putconn(conn)

    @contextmanager
    def cursor(self):
        """Get a cursor (auto-managed connection)."""
        with self.connection() as conn:
            cur = conn.cursor()
            try:
                yield cur
            finally:
                cur.close()

    def close(self) -> None:
        """Close all connections in the pool."""
        self._pool.closeall()
        log.info("db_pool_closed")

    # ══════════════════════════════════════════════════════════
    # WF01: Recording scanning & transcription tracking
    # ══════════════════════════════════════════════════════════

    def is_file_processed(self, filename: str) -> bool:
        """Check if a file is already in processed_files (idempotency)."""
        with self.cursor() as cur:
            cur.execute(
                "SELECT COUNT(*) FROM processed_files WHERE filename = %s",
                (filename,),
            )
            count = cur.fetchone()[0]
            return count > 0

    def insert_recording(
        self,
        filename: str,
        filepath: str,
        lead_id: str | None,
        file_date: date | None,
        file_size: int | None = None,
    ) -> int | None:
        """
        Insert a new recording into processed_files with status='transcribing'.
        Returns the new row ID, or None if already exists.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO processed_files
                    (filename, filepath, lead_id, file_date, file_size_bytes, status)
                VALUES (%s, %s, %s, %s, %s, 'queued')
                ON CONFLICT (filename) DO NOTHING
                RETURNING id
                """,
                (filename, filepath, lead_id, file_date, file_size),
            )
            row = cur.fetchone()
            if row:
                log.info("recording_inserted", filename=filename, lead_id=lead_id, id=row[0])
                return row[0]
            return None

    def get_transcribing_files(self) -> list[dict[str, Any]]:
        """Get files currently in queued/transcribing status (for polling check)."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT id, filename, filepath, lead_id, created_at
                FROM processed_files
                WHERE status IN ('queued', 'transcribing')
                ORDER BY created_at
                """
            )
            return [
                {"id": r[0], "filename": r[1], "filepath": r[2], "lead_id": r[3], "created_at": r[4]}
                for r in cur.fetchall()
            ]

    def update_recording_status(
        self,
        filename: str,
        status: str,
        transcript: str | None = None,
        error_message: str | None = None,
    ) -> None:
        """Update recording status after transcription attempt."""
        with self.cursor() as cur:
            if transcript is not None:
                cur.execute(
                    """
                    UPDATE processed_files
                    SET status = %s,
                        transcript_text = %s,
                        completed_at = NOW()
                    WHERE filename = %s
                    """,
                    (status, transcript, filename),
                )
            elif error_message is not None:
                cur.execute(
                    """
                    UPDATE processed_files
                    SET status = %s,
                        error_message = %s,
                        retry_count = retry_count + 1
                    WHERE filename = %s
                    """,
                    (status, error_message, filename),
                )
            else:
                cur.execute(
                    "UPDATE processed_files SET status = %s WHERE filename = %s",
                    (status, filename),
                )

    # ══════════════════════════════════════════════════════════
    # WF02: Daily Digest
    # ══════════════════════════════════════════════════════════

    def get_todays_transcripts(self, target_date: date | None = None) -> list[dict[str, Any]]:
        """
        Load today's completed transcripts with lead info.
        Source: test_wf02.py Step 1 query.
        """
        d = target_date or date.today()
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT pf.lead_id, pf.transcript_text, pf.filename,
                       lcm.lead_name, lcm.curators
                FROM processed_files pf
                LEFT JOIN lead_chat_mapping lcm ON lcm.lead_id = pf.lead_id
                WHERE pf.transcript_text IS NOT NULL
                  AND COALESCE(pf.file_date, pf.created_at::date) = %s
                ORDER BY pf.lead_id
                """,
                (d,),
            )
            return [
                {
                    "lead_id": r[0], "transcript_text": r[1], "filename": r[2],
                    "lead_name": r[3], "curators": r[4],
                }
                for r in cur.fetchall()
            ]

    def get_todays_summaries(self, target_date: date | None = None) -> list[dict[str, Any]]:
        """
        Load today's client summaries with lead info.
        Source: test_wf02.py Step 1 second query.
        """
        d = target_date or date.today()
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT cs.lead_id, cs.source_type, cs.summary_text, lcm.lead_name
                FROM client_summaries cs
                LEFT JOIN lead_chat_mapping lcm ON lcm.lead_id = cs.lead_id
                WHERE cs.summary_date = %s
                ORDER BY cs.lead_id
                """,
                (d,),
            )
            return [
                {"lead_id": r[0], "source_type": r[1], "summary_text": r[2], "lead_name": r[3]}
                for r in cur.fetchall()
            ]

    def get_bot_chats(self) -> list[str]:
        """Get all registered Telegram chat IDs for digest delivery."""
        with self.cursor() as cur:
            cur.execute("SELECT chat_id FROM bot_chats")
            return [str(r[0]) for r in cur.fetchall()]

    def mark_summary_sent(self, target_date: date | None = None) -> None:
        """Mark all transcripts for the date as summary_sent=true."""
        d = target_date or date.today()
        with self.cursor() as cur:
            cur.execute(
                """
                UPDATE processed_files
                SET summary_sent = true
                WHERE COALESCE(file_date, created_at::date) = %s
                  AND status = 'completed'
                """,
                (d,),
            )

    # ══════════════════════════════════════════════════════════
    # WF03: Individual Summaries
    # ══════════════════════════════════════════════════════════

    def get_unprocessed_calls(self, target_date: date | None = None) -> list[dict[str, Any]]:
        """
        Get completed calls that haven't been summarized yet.
        Source: test_wf03.py Step 1 query.
        """
        d = target_date or date.today()
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT pf.id, pf.filename, pf.lead_id, pf.transcript_text
                FROM processed_files pf
                WHERE pf.status = 'completed'
                  AND DATE(COALESCE(pf.file_date, pf.completed_at, pf.created_at)) = %s
                  AND pf.transcript_text IS NOT NULL
                  AND (pf.dify_doc_id IS NULL OR pf.dify_doc_id = '')
                ORDER BY pf.lead_id, pf.id
                LIMIT 50
                """,
                (d,),
            )
            return [
                {"id": r[0], "filename": r[1], "lead_id": r[2], "transcript_text": r[3]}
                for r in cur.fetchall()
            ]

    def get_unprocessed_chats(self, target_date: date | None = None) -> list[dict[str, Any]]:
        """Get chat messages that haven't been summarized today."""
        d = target_date or date.today()
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT cm.lead_id
                FROM chat_messages cm
                WHERE DATE(cm.message_date) = %s
                  AND cm.lead_id NOT IN (
                      SELECT lead_id FROM client_summaries
                      WHERE summary_date = %s AND source_type = 'chat'
                  )
                """,
                (d, d),
            )
            return [{"lead_id": r[0]} for r in cur.fetchall()]

    def get_chat_messages_for_lead(
        self, lead_id: str, target_date: date | None = None
    ) -> list[dict[str, Any]]:
        """Get all chat messages for a lead on a given date."""
        d = target_date or date.today()
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT id, chat_title, sender, message_text, message_date
                FROM chat_messages
                WHERE lead_id = %s AND DATE(message_date) = %s
                ORDER BY message_date
                """,
                (lead_id, d),
            )
            return [
                {
                    "id": r[0], "chat_title": r[1], "sender": r[2],
                    "text": r[3], "date": r[4],
                }
                for r in cur.fetchall()
            ]

    def get_dataset_map(self) -> dict[str, str]:
        """
        Get lead_id → dify_dataset_id mapping.
        Source: test_wf03.py Step 2.
        """
        with self.cursor() as cur:
            cur.execute(
                "SELECT lead_id, dify_dataset_id FROM lead_chat_mapping WHERE active = true"
            )
            return {row[0]: row[1] for row in cur.fetchall() if row[1]}

    def save_client_summary(
        self,
        lead_id: str,
        source_type: str,
        summary_text: str,
        summary_date: date,
        file_path: str | None = None,
    ) -> int:
        """
        Insert a row into client_summaries and return the new ID.
        Source: test_wf03.py Step 7.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO client_summaries
                    (lead_id, source_type, summary_text, summary_date, file_path)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (lead_id, source_type, summary_text, summary_date, file_path),
            )
            return cur.fetchone()[0]

    def update_dify_doc_id(
        self,
        file_ids: list[int],
        dify_doc_id: str,
        summary_text: str,
    ) -> None:
        """Update processed_files with Dify document ID after push."""
        if not file_ids:
            return
        with self.cursor() as cur:
            for fid in file_ids:
                cur.execute(
                    """
                    UPDATE processed_files
                    SET dify_doc_id = %s, summary_text = %s
                    WHERE id = %s
                    """,
                    (dify_doc_id, summary_text, fid),
                )

    # ══════════════════════════════════════════════════════════
    # WF06: Deadline Extractor
    # ══════════════════════════════════════════════════════════

    def get_untasked_transcripts(self, limit: int = 5) -> list[dict[str, Any]]:
        """
        Get transcripts where tasks haven't been extracted yet.
        Source: 06-deadline-extractor.json "Load Unprocessed Transcripts" node.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT id, lead_id, transcript_text, filename
                FROM processed_files
                WHERE status = 'completed'
                  AND COALESCE(tasks_extracted, false) = false
                  AND transcript_text IS NOT NULL
                LIMIT %s
                """,
                (limit,),
            )
            return [
                {"id": r[0], "lead_id": r[1], "transcript_text": r[2], "filename": r[3]}
                for r in cur.fetchall()
            ]

    def save_extracted_tasks(
        self,
        lead_id: str | None,
        source_file: str,
        tasks: list[dict[str, str]],
    ) -> int:
        """
        Save extracted tasks to extracted_tasks table.
        Source: 06-deadline-extractor.json "Save Task to DB" node.
        Returns number of tasks saved.
        """
        saved = 0
        with self.cursor() as cur:
            for task in tasks:
                cur.execute(
                    """
                    INSERT INTO extracted_tasks
                        (lead_id, source_file, task_desc, assignee, deadline, context)
                    VALUES (%s, %s, %s, %s, %s, %s)
                    """,
                    (
                        lead_id,
                        source_file,
                        task.get("task", ""),
                        task.get("assignee", ""),
                        task.get("deadline", ""),
                        task.get("context", ""),
                    ),
                )
                saved += 1
        return saved

    def mark_tasks_extracted(self, file_id: int) -> None:
        """Mark a processed_file as having its tasks extracted."""
        with self.cursor() as cur:
            cur.execute(
                "UPDATE processed_files SET tasks_extracted = true WHERE id = %s",
                (file_id,),
            )

    # ══════════════════════════════════════════════════════════
    # WF04: Telegram Bot / Status
    # ══════════════════════════════════════════════════════════

    def get_lead_info(self) -> list[dict[str, Any]]:
        """Get all leads with metadata for /status command."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT lead_id, lead_name, curators, chat_id, dify_dataset_id, active
                FROM lead_chat_mapping
                ORDER BY lead_id
                """
            )
            return [
                {
                    "lead_id": r[0], "lead_name": r[1], "curators": r[2],
                    "chat_id": r[3], "dify_dataset_id": r[4], "active": r[5],
                }
                for r in cur.fetchall()
            ]

    def get_system_status(self) -> dict[str, Any]:
        """Aggregate system stats for /status command."""
        stats: dict[str, Any] = {}
        with self.cursor() as cur:
            # Total files
            cur.execute("SELECT COUNT(*) FROM processed_files")
            stats["total_files"] = cur.fetchone()[0]

            # By status
            cur.execute(
                "SELECT status, COUNT(*) FROM processed_files GROUP BY status ORDER BY status"
            )
            stats["by_status"] = {r[0]: r[1] for r in cur.fetchall()}

            # Today's files
            cur.execute(
                """
                SELECT COUNT(*) FROM processed_files
                WHERE COALESCE(file_date, created_at::date) = CURRENT_DATE
                """
            )
            stats["today_files"] = cur.fetchone()[0]

            # Total summaries
            cur.execute("SELECT COUNT(*) FROM client_summaries")
            stats["total_summaries"] = cur.fetchone()[0]

            # Total tasks
            cur.execute("SELECT COUNT(*) FROM extracted_tasks")
            stats["total_tasks"] = cur.fetchone()[0]

            # Chat messages
            cur.execute("SELECT COUNT(*) FROM chat_messages")
            stats["total_chat_messages"] = cur.fetchone()[0]

        return stats

    # ══════════════════════════════════════════════════════════
    # Prompts
    # ══════════════════════════════════════════════════════════

    def get_prompt(self, name: str) -> str | None:
        """
        Get active prompt text by name.
        Prompt names: call_summary_prompt, chat_summary_prompt,
                      digest_prompt, report_prompt
        """
        with self.cursor() as cur:
            cur.execute(
                "SELECT prompt_text FROM prompts WHERE name = %s AND is_active = true",
                (name,),
            )
            row = cur.fetchone()
            return row[0] if row else None

    # ══════════════════════════════════════════════════════════
    # Bitrix24 CRM sync
    # ══════════════════════════════════════════════════════════

    def save_bitrix_lead(self, data: dict) -> None:
        """Upsert a Bitrix lead/contact into bitrix_leads."""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bitrix_leads
                    (bitrix_lead_id, bitrix_entity_type, diffy_lead_id, title, name,
                     phone, email, status_id, source_id, responsible_id, responsible_name,
                     contract_number, last_synced_at)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (bitrix_lead_id) DO UPDATE SET
                    diffy_lead_id    = EXCLUDED.diffy_lead_id,
                    title            = EXCLUDED.title,
                    name             = EXCLUDED.name,
                    phone            = EXCLUDED.phone,
                    email            = EXCLUDED.email,
                    status_id        = EXCLUDED.status_id,
                    responsible_id   = EXCLUDED.responsible_id,
                    responsible_name = EXCLUDED.responsible_name,
                    contract_number  = EXCLUDED.contract_number,
                    last_synced_at   = NOW()
                """,
                (
                    data["bitrix_lead_id"], data.get("bitrix_entity_type", "lead"),
                    data.get("diffy_lead_id"), data.get("title"), data.get("name"),
                    data.get("phone"), data.get("email"), data.get("status_id"),
                    data.get("source_id"), data.get("responsible_id"),
                    data.get("responsible_name"), data.get("contract_number"),
                ),
            )

    def save_bitrix_call(self, data: dict) -> bool:
        """Insert a call record. Returns True if inserted (not duplicate)."""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bitrix_calls
                    (bitrix_activity_id, bitrix_call_id, bitrix_lead_id, diffy_lead_id,
                     direction, phone_number, call_duration, call_date,
                     responsible_id, responsible_name, record_url, transcript_status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (bitrix_activity_id) DO NOTHING
                RETURNING id
                """,
                (
                    data["bitrix_activity_id"], data.get("bitrix_call_id"),
                    data.get("bitrix_lead_id"), data.get("diffy_lead_id"),
                    data.get("direction"), data.get("phone_number"),
                    data.get("call_duration"), data.get("call_date"),
                    data.get("responsible_id"), data.get("responsible_name"),
                    data.get("record_url"),
                    data.get("transcript_status", "no_record"),
                ),
            )
            return cur.fetchone() is not None

    def save_bitrix_email(self, data: dict) -> bool:
        """Insert an email record. Returns True if inserted."""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bitrix_emails
                    (bitrix_activity_id, bitrix_lead_id, diffy_lead_id,
                     direction, subject, email_body, email_from, email_to,
                     email_date, responsible_id, responsible_name)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (bitrix_activity_id) DO NOTHING
                RETURNING id
                """,
                (
                    data["bitrix_activity_id"], data.get("bitrix_lead_id"),
                    data.get("diffy_lead_id"), data.get("direction"),
                    data.get("subject"), data.get("email_body"),
                    data.get("email_from"), data.get("email_to"),
                    data.get("email_date"), data.get("responsible_id"),
                    data.get("responsible_name"),
                ),
            )
            return cur.fetchone() is not None

    def save_bitrix_comment(self, data: dict) -> bool:
        """Insert a timeline comment. Returns True if inserted."""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bitrix_comments
                    (bitrix_comment_id, bitrix_lead_id, diffy_lead_id,
                     comment_text, author_id, author_name, comment_date)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (bitrix_comment_id) DO NOTHING
                RETURNING id
                """,
                (
                    data["bitrix_comment_id"], data.get("bitrix_lead_id"),
                    data.get("diffy_lead_id"), data.get("comment_text"),
                    data.get("author_id"), data.get("author_name"),
                    data.get("comment_date"),
                ),
            )
            return cur.fetchone() is not None

    def get_bitrix_leads_for_sync(self) -> list[dict[str, Any]]:
        """Get all synced Bitrix leads/contacts for activity sync."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT bitrix_lead_id, bitrix_entity_type, diffy_lead_id,
                       title, name, contract_number
                FROM bitrix_leads
                ORDER BY bitrix_lead_id
                """
            )
            return [
                {
                    "bitrix_lead_id": r[0], "bitrix_entity_type": r[1],
                    "diffy_lead_id": r[2], "title": r[3], "name": r[4],
                    "contract_number": r[5],
                }
                for r in cur.fetchall()
            ]

    def get_calls_pending_transcription(self) -> list[dict[str, Any]]:
        """Get calls with record_url that haven't been transcribed yet."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT id, bitrix_activity_id, diffy_lead_id, record_url
                FROM bitrix_calls
                WHERE transcript_status = 'pending'
                  AND record_url IS NOT NULL
                ORDER BY call_date DESC
                LIMIT 20
                """
            )
            return [
                {
                    "id": r[0], "bitrix_activity_id": r[1],
                    "diffy_lead_id": r[2], "record_url": r[3],
                }
                for r in cur.fetchall()
            ]

    def update_call_transcript(
        self, call_id: int, transcript_text: str, status: str
    ) -> None:
        """Update transcript text and status for a call."""
        with self.cursor() as cur:
            cur.execute(
                """
                UPDATE bitrix_calls
                SET transcript_text = %s, transcript_status = %s
                WHERE id = %s
                """,
                (transcript_text, status, call_id),
            )

    def get_bitrix_data_for_summary(
        self, diffy_lead_id: str, target_date
    ) -> dict[str, Any]:
        """Get calls, emails, comments for a lead on a given date (for summary generation)."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT id, direction, call_duration, call_date,
                       responsible_name, transcript_text
                FROM bitrix_calls
                WHERE diffy_lead_id = %s
                  AND DATE(call_date) = %s
                ORDER BY call_date
                """,
                (diffy_lead_id, target_date),
            )
            calls = [
                {
                    "id": r[0], "direction": r[1], "duration": r[2],
                    "date": r[3], "responsible": r[4], "transcript": r[5],
                }
                for r in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT id, direction, subject, email_body, email_from, email_to, email_date
                FROM bitrix_emails
                WHERE diffy_lead_id = %s
                  AND DATE(email_date) = %s
                ORDER BY email_date
                """,
                (diffy_lead_id, target_date),
            )
            emails = [
                {
                    "id": r[0], "direction": r[1], "subject": r[2],
                    "body": r[3], "from": r[4], "to": r[5], "date": r[6],
                }
                for r in cur.fetchall()
            ]

            cur.execute(
                """
                SELECT id, comment_text, author_name, comment_date
                FROM bitrix_comments
                WHERE diffy_lead_id = %s
                  AND DATE(comment_date) = %s
                ORDER BY comment_date
                """,
                (diffy_lead_id, target_date),
            )
            comments = [
                {
                    "id": r[0], "text": r[1],
                    "author": r[2], "date": r[3],
                }
                for r in cur.fetchall()
            ]

            return {"calls": calls, "emails": emails, "comments": comments}

    def save_bitrix_summary(self, data: dict) -> None:
        """Upsert a daily summary for a Bitrix lead."""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bitrix_summaries
                    (diffy_lead_id, summary_date, calls_count, emails_count,
                     comments_count, summary_text, dify_doc_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (diffy_lead_id, summary_date) DO UPDATE SET
                    calls_count   = EXCLUDED.calls_count,
                    emails_count  = EXCLUDED.emails_count,
                    comments_count = EXCLUDED.comments_count,
                    summary_text  = EXCLUDED.summary_text,
                    dify_doc_id   = EXCLUDED.dify_doc_id
                """,
                (
                    data["diffy_lead_id"], data["summary_date"],
                    data.get("calls_count", 0), data.get("emails_count", 0),
                    data.get("comments_count", 0), data.get("summary_text"),
                    data.get("dify_doc_id"),
                ),
            )

    def start_bitrix_sync_log(self, sync_type: str = "full") -> int:
        """Insert a sync log entry. Returns log row ID."""
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO bitrix_sync_log (sync_type, status)
                VALUES (%s, 'started')
                RETURNING id
                """,
                (sync_type,),
            )
            row = cur.fetchone()
            return row[0] if row else 0

    def finish_bitrix_sync_log(
        self,
        log_id: int,
        status: str,
        leads_synced: int = 0,
        calls_synced: int = 0,
        emails_synced: int = 0,
        comments_synced: int = 0,
        error_message: str | None = None,
    ) -> None:
        """Update sync log with final counts and status."""
        with self.cursor() as cur:
            cur.execute(
                """
                UPDATE bitrix_sync_log SET
                    status           = %s,
                    leads_synced     = %s,
                    calls_synced     = %s,
                    emails_synced    = %s,
                    comments_synced  = %s,
                    error_message    = %s,
                    completed_at     = NOW()
                WHERE id = %s
                """,
                (
                    status, leads_synced, calls_synced,
                    emails_synced, comments_synced, error_message, log_id,
                ),
            )

    def get_bitrix_activity_dates(self, diffy_lead_id: str) -> list:
        """
        Return all unique dates that have ANY activity (call/email/comment)
        for a given lead. Used for historical summary generation.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT DISTINCT activity_date FROM (
                    SELECT DATE(call_date)    AS activity_date FROM bitrix_calls
                     WHERE diffy_lead_id = %s AND call_date IS NOT NULL
                    UNION
                    SELECT DATE(email_date)   AS activity_date FROM bitrix_emails
                     WHERE diffy_lead_id = %s AND email_date IS NOT NULL
                    UNION
                    SELECT DATE(comment_date) AS activity_date FROM bitrix_comments
                     WHERE diffy_lead_id = %s AND comment_date IS NOT NULL
                ) t
                ORDER BY activity_date
                """,
                (diffy_lead_id, diffy_lead_id, diffy_lead_id),
            )
            return [row[0] for row in cur.fetchall()]

    def get_bitrix_dataset_map(self) -> dict[str, str]:
        """
        Get diffy_lead_id → dify_dataset_id mapping from bitrix_leads table.
        Used for Bitrix24 CRM data (NOT for Telegram chats).
        """
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT diffy_lead_id, dify_dataset_id
                FROM bitrix_leads
                WHERE dify_dataset_id IS NOT NULL
                """
            )
            return {row[0]: row[1] for row in cur.fetchall()}

    def save_bitrix_dataset_mapping(self, diffy_lead_id: str, dataset_id: str) -> None:
        """
        Update dify_dataset_id in bitrix_leads table.
        Used when auto-creating Dify datasets for Bitrix leads/contacts.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                UPDATE bitrix_leads
                SET dify_dataset_id = %s
                WHERE diffy_lead_id = %s
                """,
                (dataset_id, diffy_lead_id),
            )

    # ══════════════════════════════════════════════════════════
    # Legacy: Telegram chat mapping (deprecated for Bitrix)
    # ══════════════════════════════════════════════════════════

    def get_telegram_dataset_map(self) -> dict[str, str]:
        """
        Get lead_id → dify_dataset_id mapping from lead_chat_mapping.
        DEPRECATED for Bitrix - use get_bitrix_dataset_map() instead.
        Kept for legacy Telegram chat support.
        """
        with self.cursor() as cur:
            cur.execute(
                "SELECT lead_id, dify_dataset_id FROM lead_chat_mapping WHERE active = true"
            )
            return {row[0]: row[1] for row in cur.fetchall() if row[1]}

    def save_dataset_mapping(self, lead_id: str, dataset_id: str) -> None:
        """
        Upsert a lead_id → dify_dataset_id mapping in lead_chat_mapping.
        DEPRECATED for Bitrix - use save_bitrix_dataset_mapping() instead.
        Kept for legacy Telegram chat support.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                INSERT INTO lead_chat_mapping (lead_id, dify_dataset_id, active)
                VALUES (%s, %s, true)
                ON CONFLICT (lead_id) DO UPDATE SET
                    dify_dataset_id = EXCLUDED.dify_dataset_id,
                    active          = true
                """,
                (lead_id, dataset_id),
            )

    # ══════════════════════════════════════════════════════════
    # Client Registry (Unified Client Identity)
    # ══════════════════════════════════════════════════════════

    def find_dataset_for_contract(self, contract_number: str) -> str | None:
        """
        Find Dify dataset ID by contract number (e.g., 'ФФ-4405').
        Used by Jitsi/Telegram workflows to add data to existing Bitrix datasets.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT dify_dataset_id
                FROM client_registry
                WHERE %s = ANY(contract_numbers)
                  OR active_contract = %s
                LIMIT 1
                """,
                (contract_number, contract_number),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def find_dataset_by_name(self, legal_name: str) -> str | None:
        """
        Find Dify dataset ID by legal name (fuzzy match).
        Used for cross-referencing clients by company name.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT dify_dataset_id
                FROM client_registry
                WHERE legal_name ILIKE %s
                LIMIT 1
                """,
                (f"%{legal_name}%",),
            )
            row = cur.fetchone()
            return row[0] if row else None

    def get_client_info(self, diffy_lead_id: str) -> dict[str, Any] | None:
        """
        Get complete client information from registry.
        Returns all known IDs, contracts, contact info, and Dify dataset.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id, bitrix_lead_id, bitrix_contact_id, diffy_lead_id,
                    telegram_lead_id, legacy_lead_id,
                    legal_name, contract_numbers, active_contract,
                    phone, email, dify_dataset_id,
                    source_system, data_quality, notes
                FROM client_registry
                WHERE diffy_lead_id = %s
                """,
                (diffy_lead_id,),
            )
            row = cur.fetchone()
            if not row:
                return None

            return {
                "id": row[0],
                "bitrix_lead_id": row[1],
                "bitrix_contact_id": row[2],
                "diffy_lead_id": row[3],
                "telegram_lead_id": row[4],
                "legacy_lead_id": row[5],
                "legal_name": row[6],
                "contract_numbers": row[7],
                "active_contract": row[8],
                "phone": row[9],
                "email": row[10],
                "dify_dataset_id": row[11],
                "source_system": row[12],
                "data_quality": row[13],
                "notes": row[14],
            }

    def link_telegram_to_client(self, telegram_lead_id: int, diffy_lead_id: str) -> bool:
        """
        Link Telegram lead ID to Bitrix client in registry.
        Used when Telegram chat data needs to be added to existing Bitrix dataset.
        """
        with self.cursor() as cur:
            cur.execute(
                """
                UPDATE client_registry
                SET telegram_lead_id = %s, updated_at = NOW()
                WHERE diffy_lead_id = %s
                """,
                (str(telegram_lead_id), diffy_lead_id),
            )
            return cur.rowcount > 0

    def get_or_create_dataset_for_recording(self, lead_id: str, dify) -> str | None:
        """
        Find existing Dify dataset or create new one for Jitsi recording.
        Priority:
        1. Match by contract number (extracted from lead_id)
        2. Match by legal name (from processed_files metadata)
        3. Create new dataset

        Returns dataset_id or None on failure.
        """
        # Try contract number match
        import re
        contract_match = re.search(r'ФФ-(\d+)', lead_id, re.IGNORECASE)
        if contract_match:
            contract = f'ФФ-{contract_match.group(1)}'
            dataset_id = self.find_dataset_for_contract(contract)
            if dataset_id:
                log.info("dataset_found_by_contract", lead_id=lead_id, contract=contract, dataset_id=dataset_id)
                return dataset_id

        # Try legal name match (would need name lookup)
        # For now, create new dataset
        try:
            dataset_id = dify.create_dataset(lead_id)
            if dataset_id:
                log.info("dataset_created_for_recording", lead_id=lead_id, dataset_id=dataset_id)
                return dataset_id
        except Exception as e:
            log.warning("dataset_create_failed", lead_id=lead_id, error=str(e))

        return None

