"""
Recording Scanner — replaces n8n WF01 (01-new-recording.json).

Original WF01 flow (705 lines of JSON):
  1. Cron every 5 min
  2. `find /recordings -name "*.webm" ...` (Execute Command node)
  3. Parse filename → extract LEAD_ID (JS Code node)
  4. Check processed_files for duplicates (Postgres node)
  5. INSERT with status='transcribing' (Postgres node)
  6. curl to whisper:9000 (Execute Command node)
  7. Parse result, mark completed/error

Improvements over n8n WF01:
  - os.walk() instead of shell `find` (cross-platform, no subprocess)
  - No fixed retry count — check_pending() rechecks every cycle
  - Proper LEAD_ID regex extraction
  - POST to transcribe service (HTTP, not curl)
  - Eliminates race condition (files in 'transcribing' checked indefinitely)
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime

import httpx

from app.core.db import Database
from app.core.logger import get_logger

log = get_logger("scan_recordings")

# Audio file extensions supported by Whisper / transcribe service
AUDIO_EXTENSIONS = (".webm", ".mp4", ".mp3", ".ogg", ".wav", ".m4a")


class RecordingScanner:
    """Scans recordings directory and manages transcription pipeline."""

    def __init__(
        self,
        db: Database,
        transcribe_url: str,
        recordings_dir: str,
    ) -> None:
        self.db = db
        self.transcribe_url = transcribe_url.rstrip("/")
        self.recordings_dir = recordings_dir

    def scan(self) -> int:
        """
        Scan /recordings for new audio files and start transcription.

        Returns number of new files found and submitted.
        """
        new_count = 0

        if not os.path.isdir(self.recordings_dir):
            log.warning("recordings_dir_missing", path=self.recordings_dir)
            return 0

        for root, _dirs, files in os.walk(self.recordings_dir):
            for filename in files:
                if not filename.lower().endswith(AUDIO_EXTENSIONS):
                    continue

                # Skip already processed files (idempotency check)
                if self.db.is_file_processed(filename):
                    continue

                filepath = os.path.join(root, filename)
                lead_id = self._extract_lead_id(filename)
                file_date = self._extract_date(filename, filepath)
                file_size = self._safe_file_size(filepath)

                # Insert into DB with status='transcribing'
                row_id = self.db.insert_recording(
                    filename=filename,
                    filepath=filepath,
                    lead_id=lead_id,
                    file_date=file_date,
                    file_size=file_size,
                )

                if row_id is not None:
                    # Submit to transcribe service (non-blocking)
                    self._start_transcription(filepath, filename)
                    new_count += 1

        if new_count > 0:
            log.info("scan_complete", new_files=new_count)
        else:
            log.debug("scan_complete", new_files=0)

        return new_count

    def check_pending(self) -> int:
        """
        Check transcription status for files in 'transcribing' state.

        This replaces n8n's fixed 10-retry polling loop.
        Instead, it runs every scan cycle and rechecks indefinitely
        until the transcribe service returns a result.

        Returns number of files that completed.
        """
        pending = self.db.get_transcribing_files()
        if not pending:
            return 0

        completed = 0
        for record in pending:
            try:
                result = httpx.post(
                    f"{self.transcribe_url}/check",
                    json={"filename": record["filename"]},
                    timeout=15.0,
                ).json()

                transcript = result.get("transcript")
                status = result.get("status", "")

                if transcript:
                    self.db.update_recording_status(
                        record["filename"], "completed", transcript=transcript
                    )
                    log.info(
                        "transcription_completed",
                        filename=record["filename"],
                        lead_id=record["lead_id"],
                        chars=len(transcript),
                    )
                    completed += 1
                elif status == "error":
                    self.db.update_recording_status(
                        record["filename"],
                        "error",
                        error_message="transcribe service returned error",
                    )
                    log.warning(
                        "transcription_error",
                        filename=record["filename"],
                    )
                # else: still processing — will recheck on next cycle

            except Exception as e:
                log.error(
                    "check_pending_error",
                    filename=record["filename"],
                    error=str(e),
                )

        if completed:
            log.info("check_pending_done", completed=completed, still_pending=len(pending) - completed)
        return completed

    # ── Private helpers ──────────────────────────────────────

    def _start_transcription(self, filepath: str, filename: str) -> None:
        """POST to transcribe service to start STT (non-blocking on server side)."""
        try:
            response = httpx.post(
                self.transcribe_url,
                json={"filepath": filepath, "filename": filename},
                timeout=15.0,
            )
            log.info(
                "transcription_started",
                filename=filename,
                status_code=response.status_code,
            )
        except Exception as e:
            log.error("transcription_start_failed", filename=filename, error=str(e))

    @staticmethod
    def _extract_lead_id(filename: str) -> str | None:
        """
        Extract LEAD_ID from filename.

        Supported formats (from n8n WF01 JS Code node):
          101_2026-02-20_10-30.mp3  → 101
          101_разговор.mp3          → 101
          101-клиент.wav            → 101
          101.wav                   → 101
          LEAD-4405-conf_...        → 4405
        """
        # Try LEAD-{ID} pattern first (from Jibri)
        match = re.search(r"LEAD[_-]?(\d{3,5})", filename, re.IGNORECASE)
        if match:
            return match.group(1)

        # Fallback: digits at start of filename
        match = re.match(r"^(\d+)[_\-.]", filename)
        if match:
            return match.group(1)

        return None

    @staticmethod
    def _extract_date(filename: str, filepath: str) -> date:
        """
        Extract date from filename (YYYY-MM-DD pattern) or fall back to file mtime.
        Source: n8n WF01 "Parse Filenames" JS Code node.
        """
        match = re.search(r"(\d{4}-\d{2}-\d{2})", filename)
        if match:
            try:
                return datetime.strptime(match.group(1), "%Y-%m-%d").date()
            except ValueError:
                pass

        # Fallback: file modification time
        try:
            mtime = os.path.getmtime(filepath)
            return datetime.fromtimestamp(mtime).date()
        except OSError:
            return date.today()

    @staticmethod
    def _safe_file_size(filepath: str) -> int | None:
        """Get file size, return None if not accessible."""
        try:
            return os.path.getsize(filepath)
        except OSError:
            return None
