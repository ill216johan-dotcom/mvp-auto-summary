"""
Bitrix24 REST API client for CRM data synchronization.

Handles leads, contacts, activities (calls/emails), timeline comments,
call recordings, and user data via webhook authentication.
"""
from __future__ import annotations

import logging
import time
from typing import Any

import requests

log = logging.getLogger("bitrix24")


class Bitrix24Client:
    """Bitrix24 REST API client with pagination, batch, and retry support."""

    def __init__(self, webhook_url: str) -> None:
        self.webhook_url = webhook_url.rstrip("/")
        self._session = requests.Session()
        self._user_cache: dict[int, str] = {}

    def call(self, method: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
        """Make a single API call. Retries on 429 rate limit."""
        url = f"{self.webhook_url}/{method}"
        for attempt in range(3):
            try:
                resp = self._session.post(url, json=params or {}, timeout=30)
                if resp.status_code == 429:
                    wait = int(resp.headers.get("Retry-After", 5))
                    log.warning("bitrix_rate_limit", method=method, wait=wait)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                data = resp.json()
                if "error" in data:
                    raise RuntimeError(f"Bitrix24 error: {data.get('error_description', data['error'])}")
                return data
            except requests.RequestException as e:
                if attempt == 2:
                    raise
                log.warning("bitrix_retry", method=method, attempt=attempt, error=str(e))
                time.sleep(2 ** attempt)
        raise RuntimeError(f"Bitrix24 rate limit exceeded after 3 retries for method: {method}")

    def call_list(self, method: str, params: dict[str, Any] | None = None) -> list[dict]:
        """Auto-paginate through all pages. Returns all records."""
        params = dict(params or {})
        params.setdefault("start", 0)
        all_results: list[dict] = []
        while True:
            data = self.call(method, params)
            result = data.get("result", [])
            if isinstance(result, list):
                all_results.extend(result)
            elif isinstance(result, dict):
                # Some methods return dict with nested list
                for v in result.values():
                    if isinstance(v, list):
                        all_results.extend(v)
                        break
            next_page = data.get("next")
            if next_page is None:
                break
            params["start"] = next_page
            log.debug("bitrix_paginate", method=method, start=next_page, total_so_far=len(all_results))
        return all_results

    def call_batch(self, commands: dict[str, dict]) -> dict[str, Any]:
        """Execute up to 50 API calls in a single batch request."""
        cmd = {k: {"method": v["method"], "params": v.get("params", {})} for k, v in commands.items()}
        data = self.call("batch", {"cmd": cmd, "halt": 0})
        return data.get("result", {})

    def get_leads(
        self,
        filter: dict | None = None,
        select: list[str] | None = None,
    ) -> list[dict]:
        """Get all CRM Leads with auto-pagination."""
        params: dict[str, Any] = {}
        if filter:
            params["filter"] = filter
        if select:
            params["select"] = select
        return self.call_list("crm.lead.list", params)

    def get_contacts(
        self,
        filter: dict | None = None,
        select: list[str] | None = None,
    ) -> list[dict]:
        """Get all CRM Contacts with auto-pagination."""
        params: dict[str, Any] = {}
        if filter:
            params["filter"] = filter
        if select:
            params["select"] = select
        return self.call_list("crm.contact.list", params)

    def get_activities(
        self,
        owner_type_id: int,
        owner_id: int,
        type_id: int | None = None,
    ) -> list[dict]:
        """Get activities (calls/emails) for a lead or contact.

        owner_type_id: 1=Lead, 3=Contact
        type_id: 1=Call, 4=Email (None = all types)
        """
        params: dict[str, Any] = {
            "filter": {
                "OWNER_TYPE_ID": owner_type_id,
                "OWNER_ID": owner_id,
            },
            "select": [
                "ID", "TYPE_ID", "SUBJECT", "DESCRIPTION", "START_TIME",
                "DIRECTION", "RESPONSIBLE_ID", "SETTINGS", "COMMUNICATIONS",
            ],
        }
        if type_id is not None:
            params["filter"]["TYPE_ID"] = type_id
        return self.call_list("crm.activity.list", params)

    def get_call_history(self, filter: dict | None = None) -> list[dict]:
        """Get call recordings from VoxImplant statistics."""
        params: dict[str, Any] = {
            "select": ["ID", "CALL_ID", "CRM_ENTITY_TYPE", "CRM_ENTITY_ID",
                       "CALL_DURATION", "CALL_START_DATE", "CALL_TYPE",
                       "PORTAL_USER_ID", "PHONE_NUMBER", "CALL_RECORD_URL", "SRC_URL",
                       "RECORD_FILE_ID"],
        }
        if filter:
            params["filter"] = filter
        return self.call_list("voximplant.statistic.get", params)

    def get_disk_download_url(self, file_id: int) -> str | None:
        """
        Get a temporary download URL for a file stored in Bitrix24 Disk.
        Requires 'disk' scope in the webhook.
        Returns the DOWNLOAD_URL string, or None if not found.
        """
        try:
            data = self.call("disk.file.get", {"id": file_id})
            result = data.get("result", {})
            return result.get("DOWNLOAD_URL")
        except Exception as e:
            log.warning("bitrix_disk_file_get_failed", file_id=file_id, error=str(e))
            return None

    def get_timeline_comments(self, entity_type: str, entity_id: int) -> list[dict]:
        """Get timeline comments for a lead or contact.

        entity_type: 'lead' or 'contact'
        """
        entity_type_map = {"lead": "CRM_LEAD", "contact": "CRM_CONTACT"}
        params = {
            "filter": {
                "ENTITY_TYPE": entity_type_map.get(entity_type, entity_type.upper()),
                "ENTITY_ID": entity_id,
            }
        }
        return self.call_list("crm.timeline.comment.list", params)

    def get_users(self, user_ids: list[int]) -> dict[int, str]:
        """Fetch user names by IDs. Uses in-memory cache."""
        uncached = [uid for uid in user_ids if uid not in self._user_cache]
        if uncached:
            # Batch fetch in chunks of 50
            for i in range(0, len(uncached), 50):
                chunk = uncached[i:i+50]
                try:
                    users = self.call_list("user.get", {"filter": {"ID": chunk}})
                    for u in users:
                        uid = int(u.get("ID", 0))
                        name = f"{u.get('NAME', '')} {u.get('LAST_NAME', '')}".strip()
                        self._user_cache[uid] = name or f"User#{uid}"
                except Exception as e:
                    log.warning("bitrix_users_fetch_failed", error=str(e))
        return {uid: self._user_cache.get(uid, f"User#{uid}") for uid in user_ids}

    def get_lead_fields(self) -> dict[str, Any]:
        """Get all lead field definitions including UF_* custom fields."""
        data = self.call("crm.lead.fields")
        return data.get("result", {})

    def get_contact_fields(self) -> dict[str, Any]:
        """Get all contact field definitions including UF_* custom fields."""
        data = self.call("crm.contact.fields")
        return data.get("result", {})

    def close(self) -> None:
        """Close the underlying HTTP session."""
        self._session.close()
