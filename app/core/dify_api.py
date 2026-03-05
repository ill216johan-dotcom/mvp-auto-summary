"""
Dify Knowledge Base API client.

Handles per-client document push to Dify datasets.
Used by individual_summary.py (WF03) to push summaries into
per-LEAD Knowledge Bases for RAG.

API reference: https://docs.dify.ai/
"""
from __future__ import annotations

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from app.core.logger import get_logger

log = get_logger("dify")


class DifyClient:
    """Dify.ai Knowledge Base API client."""

    def __init__(self, api_key: str, base_url: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self._client = httpx.Client(timeout=60.0)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=2, max=30), reraise=True)
    def create_document_by_text(
        self,
        dataset_id: str,
        name: str,
        text: str,
        indexing_technique: str = "high_quality",
    ) -> str:
        """
        Create a document in a Dify dataset from plain text.

        Args:
            dataset_id: The Dify dataset UUID.
            name: Document title.
            text: Document content.
            indexing_technique: 'high_quality' or 'economy'.

        Returns:
            Document ID string (or empty string on failure).
        """
        if not self.api_key or not dataset_id:
            log.warning("dify_skip", reason="no api_key or dataset_id")
            return ""

        url = f"{self.base_url}/v1/datasets/{dataset_id}/document/create-by-text"
        payload = {
            "name": name,
            "text": text,
            "indexing_technique": indexing_technique,
            "process_rule": {"mode": "automatic"},
        }
        response = self._client.post(
            url,
            json=payload,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
        )
        response.raise_for_status()
        data = response.json()
        doc_id = data.get("document", {}).get("id", "")
        log.info("dify_doc_created", dataset_id=dataset_id, doc_id=doc_id, name=name)
        return doc_id

    def close(self) -> None:
        self._client.close()
