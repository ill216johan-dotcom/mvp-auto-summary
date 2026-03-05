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

import psycopg2
from psycopg2 import pool

from app.core.logger import get_logger

log = get_logger("db")


class Database:
    """Thread-safe PostgreSQL connection pool with query methods."""

    def __init__(self, dsn: str, min_conn: int = 2, max_conn: int = 10) -> None:
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
                VALUES (%s, %s, %s, %s, %s, 'transcribing')
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
        """Get files currently in 'transcribing' status (for polling check)."""
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT id, filename, filepath, lead_id, created_at
                FROM processed_files
                WHERE status = 'transcribing'
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

    def is_digest_sent(self, target_date: date | None = None) -> bool:
        """Check if digest was already sent for the given date."""
        d = target_date or date.today()
        with self.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) > 0
                FROM processed_files
                WHERE COALESCE(file_date, created_at::date) = %s
                  AND status = 'completed'
                  AND summary_sent = true
                """,
                (d,),
            )
            return cur.fetchone()[0]

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
