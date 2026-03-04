"""
LLM client for Claude via z.ai Anthropic Messages API.

This is the SINGLE, CORRECT implementation replacing:
- n8n HTTP Request nodes (some using wrong OpenAI format)
- test_wf02.py inline urllib calls
- test_wf03.py inline urllib calls
- generate_individual_summary.py requests calls (using old GLM-4 endpoint)

Protocol: Anthropic Messages API
  - Header: x-api-key (NOT Authorization: Bearer)
  - Header: anthropic-version: 2023-06-01
  - Endpoint: {base_url}/v1/messages
  - Request body: { model, system, messages, max_tokens }
"""
from __future__ import annotations

import httpx
from tenacity import (
    retry,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

from app.core.logger import get_logger

log = get_logger("llm")


class LLMClient:
    """Anthropic Messages API client with retry and connection reuse."""

    def __init__(self, api_key: str, base_url: str, model: str) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self._client = httpx.Client(
            timeout=httpx.Timeout(connect=10.0, read=180.0, write=10.0, pool=10.0),
            limits=httpx.Limits(max_connections=5, max_keepalive_connections=2),
        )

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=2, min=3, max=60),
        retry=retry_if_exception_type((httpx.HTTPStatusError, httpx.ConnectError, httpx.ReadTimeout)),
        reraise=True,
    )
    def generate(
        self,
        system_prompt: str,
        user_content: str,
        max_tokens: int = 2000,
    ) -> str:
        """
        Generate text using Claude via Anthropic Messages API.

        Args:
            system_prompt: System-level instruction.
            user_content: User message content (transcript, chat history, etc.).
            max_tokens: Maximum tokens in response.

        Returns:
            Generated text content.

        Raises:
            httpx.HTTPStatusError: On non-2xx response (after retries).
            LLMError: On unexpected response format.
        """
        url = f"{self.base_url}/v1/messages"

        response = self._client.post(
            url,
            headers={
                "x-api-key": self.api_key,
                "anthropic-version": "2023-06-01",
                "Content-Type": "application/json",
            },
            json={
                "model": self.model,
                "system": system_prompt,
                "messages": [{"role": "user", "content": user_content}],
                "max_tokens": max_tokens,
            },
        )
        response.raise_for_status()
        data = response.json()

        # Extract text from Anthropic response format
        content_blocks = data.get("content", [])
        texts = [
            block["text"]
            for block in content_blocks
            if isinstance(block, dict) and block.get("type") == "text"
        ]
        result = "\n".join(texts).strip()

        if not result:
            # Fallback: try OpenAI format (in case provider changes)
            choices = data.get("choices", [])
            if choices:
                result = (choices[0].get("message", {}).get("content", "") or "").strip()

        if not result:
            log.warning("empty_llm_response", model=self.model, response_keys=list(data.keys()))
            raise LLMError("LLM returned empty response")

        log.debug(
            "llm_generated",
            model=self.model,
            input_chars=len(user_content),
            output_chars=len(result),
        )
        return result

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()


class LLMError(Exception):
    """LLM-specific errors."""
