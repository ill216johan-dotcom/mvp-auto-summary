"""
Bitrix24 Webhook Event Server.

Receives Bitrix24 events (OnVoximplantCallEnd) via HTTP POST
and triggers immediate call transcription.

Runs on port 8009 (configurable via WEBHOOK_PORT env var).
Bitrix sends POST form data when a call with recording ends.

Usage (standalone, for testing):
    python -m app.webhook_server

In production: started as a background thread from main.py.
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any

import requests

from app.core.logger import get_logger

log = get_logger("webhook_server")


class BitrixWebhookHandler(BaseHTTPRequestHandler):
    """HTTP handler for Bitrix24 webhook events."""

    # Injected by WebhookServer
    db: Any = None
    transcribe_url: str = ""
    bitrix_webhook_url: str = ""
    whisper_url: str = ""

    def log_message(self, format: str, *args) -> None:  # noqa: A002
        """Suppress default access log (use structlog instead)."""
        pass

    def do_GET(self) -> None:
        """Health check endpoint."""
        if self.path == "/health":
            self._respond(200, b"OK")
        else:
            self._respond(404, b"Not Found")

    def do_POST(self) -> None:
        """Handle incoming Bitrix24 event."""
        try:
            length = int(self.headers.get("Content-Length", 0))
            raw_body = self.rfile.read(length) if length else b""

            # Parse form-encoded POST body (Bitrix sends application/x-www-form-urlencoded)
            content_type = self.headers.get("Content-Type", "")
            if "json" in content_type:
                data = json.loads(raw_body.decode("utf-8", errors="replace"))
            else:
                data = dict(urllib.parse.parse_qsl(raw_body.decode("utf-8", errors="replace")))

            event_name = data.get("event", "").upper()
            log.info("webhook_received", event=event_name, path=self.path)

            if event_name == "ONVOXIMPLANTCALLEND":
                # Fire and forget in background thread
                threading.Thread(
                    target=self._handle_call_end,
                    args=(data,),
                    daemon=True,
                ).start()
                self._respond(200, b"OK")
            else:
                # Unknown event — accept and ignore
                self._respond(200, b"OK")

        except Exception as e:
            log.error("webhook_handler_error", error=str(e))
            self._respond(500, b"Internal Server Error")

    def _respond(self, status: int, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _handle_call_end(self, data: dict) -> None:
        """
        Process OnVoximplantCallEnd event.

        Bitrix event data structure:
        {
          "event": "ONVOXIMPLANTCALLEND",
          "data": {
            "CALL_ID": "externalCall.xxx",
            "CALL_DURATION": "120",
            "PHONE_NUMBER": "+79991234567",
            "CRM_ENTITY_TYPE": "LEAD",
            "CRM_ENTITY_ID": "12345",
            "CRM_ACTIVITY_ID": "67890",
            "RECORD_FILE_ID": "341880",   ← key field for download
            "CALL_RECORD_URL": "https://...",
          }
        }
        """
        try:
            event_data = data.get("data", data)  # Bitrix wraps in "data" key

            call_id = event_data.get("CALL_ID", "")
            record_file_id = event_data.get("RECORD_FILE_ID")
            record_url = event_data.get("CALL_RECORD_URL", "")
            phone_number = event_data.get("PHONE_NUMBER", "")
            crm_activity_id = event_data.get("CRM_ACTIVITY_ID")
            call_duration = event_data.get("CALL_DURATION", 0)

            log.info(
                "call_end_event",
                call_id=call_id,
                record_file_id=record_file_id,
                has_url=bool(record_url),
                phone=phone_number,
                activity_id=crm_activity_id,
                duration=call_duration,
            )

            # Skip calls without recording
            if not record_file_id and not record_url:
                log.info("call_end_no_recording", call_id=call_id)
                return

            # Find the call in DB by bitrix_call_id or crm_activity_id
            db = self.__class__.db
            if not db:
                log.error("call_end_no_db")
                return

            call_row = db.get_call_by_bitrix_ids(
                bitrix_call_id=call_id,
                bitrix_activity_id=int(crm_activity_id) if crm_activity_id else None,
            )

            if not call_row:
                log.warning("call_end_not_in_db", call_id=call_id, activity_id=crm_activity_id)
                # Update by call_id directly if exists, otherwise log and skip
                return

            call_db_id = call_row["id"]

            # Update record info in DB
            db.update_call_record_info(
                call_id=call_db_id,
                record_file_id=int(record_file_id) if record_file_id else None,
                record_url=record_url or None,
            )

            # Immediately transcribe
            self._transcribe_call(
                call_db_id=call_db_id,
                record_file_id=int(record_file_id) if record_file_id else None,
                record_url=record_url,
            )

        except Exception as e:
            log.error("call_end_handler_error", error=str(e))

    def _transcribe_call(
        self,
        call_db_id: int,
        record_file_id: int | None,
        record_url: str,
    ) -> None:
        """Download recording and send to Whisper for transcription."""
        from app.integrations.bitrix24 import Bitrix24Client

        db = self.__class__.db
        transcribe_url = self.__class__.transcribe_url
        webhook_url = self.__class__.bitrix_webhook_url

        audio_data: bytes | None = None
        suffix = ".mp3"

        # --- Method 1: Bitrix Disk API ---
        if record_file_id and webhook_url:
            try:
                client = Bitrix24Client(webhook_url)
                download_url = client.get_disk_download_url(record_file_id)
                client.close()
                if download_url:
                    resp = requests.get(download_url, timeout=60)
                    resp.raise_for_status()
                    ct = resp.headers.get("Content-Type", "")
                    if "text/html" not in ct:
                        audio_data = resp.content
                        if "wav" in ct:
                            suffix = ".wav"
                        log.info("webhook_disk_download_ok",
                                 call_id=call_db_id, file_id=record_file_id, size=len(audio_data))
            except Exception as e:
                log.warning("webhook_disk_download_failed", call_id=call_db_id, error=str(e))

        # --- Method 2: Direct URL fallback ---
        if audio_data is None and record_url:
            try:
                resp = requests.get(record_url, timeout=30)
                if resp.status_code == 200:
                    ct = resp.headers.get("Content-Type", "")
                    if "text/html" not in ct:
                        audio_data = resp.content
                        if "wav" in ct:
                            suffix = ".wav"
            except Exception as e:
                log.warning("webhook_url_download_failed", call_id=call_db_id, error=str(e))

        if not audio_data:
            log.warning("webhook_no_audio", call_id=call_db_id)
            db.update_call_transcript(call_db_id, "", "failed")
            return

        # --- Save to temp and send to Whisper ---
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp_path = tmp.name
                tmp.write(audio_data)

            # Use whisper_url directly for /v1/audio/transcriptions
            whisper_url = self.__class__.whisper_url or transcribe_url
            asr_url = whisper_url.rstrip("/") + "/v1/audio/transcriptions"
            mime = "audio/mpeg" if suffix == ".mp3" else f"audio/{suffix[1:]}"
            with open(tmp_path, "rb") as f:
                resp = requests.post(
                    asr_url,
                    files={"file": (f"audio{suffix}", f, mime)},
                    data={"language": "ru"},
                    timeout=900,  # 15 мин — CPU Whisper медленный
                )
            resp.raise_for_status()

            result = resp.json()
            transcript = (
                result.get("text") or result.get("result") or result.get("transcript") or ""
            )

            db.update_call_transcript(call_db_id, transcript, "done")
            log.info("webhook_transcribe_done", call_id=call_db_id, chars=len(transcript))

        except Exception as e:
            log.error("webhook_transcribe_error", call_id=call_db_id, error=str(e))
            db.update_call_transcript(call_db_id, "", "failed")
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except Exception:
                    pass


class WebhookServer:
    """Manages the HTTP webhook server lifecycle."""

    def __init__(
        self,
        db: Any,
        transcribe_url: str,
        bitrix_webhook_url: str,
        port: int = 8009,
        whisper_url: str = "",
    ) -> None:
        self.port = port
        self._server: HTTPServer | None = None
        self._thread: threading.Thread | None = None

        # Inject dependencies into handler class
        BitrixWebhookHandler.db = db
        BitrixWebhookHandler.transcribe_url = transcribe_url
        BitrixWebhookHandler.bitrix_webhook_url = bitrix_webhook_url
        BitrixWebhookHandler.whisper_url = whisper_url

    def start(self) -> None:
        """Start webhook server in a background daemon thread."""
        self._server = HTTPServer(("0.0.0.0", self.port), BitrixWebhookHandler)
        self._thread = threading.Thread(
            target=self._server.serve_forever,
            name="webhook-server",
            daemon=True,
        )
        self._thread.start()
        log.info("webhook_server_started", port=self.port,
                 url=f"http://84.252.100.93:{self.port}/bitrix/event")

    def stop(self) -> None:
        """Stop the webhook server."""
        if self._server:
            self._server.shutdown()
            log.info("webhook_server_stopped")
