"""
apps/api/services/llm_gateway.py


"""

from __future__ import annotations

import json
import logging
import time
from typing import AsyncGenerator
from uuid import UUID

import openai
from openai import AsyncOpenAI

from apps.api.config import settings  # existing Phase 1 config module

logger = logging.getLogger("indus_mind.llm_gateway")

_MODEL = settings.LLM_MODEL  # e.g. "llama3.2:3b"
_MAX_TOKENS = 2048
_TIMEOUT_SECONDS = 60
_STREAM_TIMEOUT_SECONDS = 90


def _get_client() -> AsyncOpenAI:
    """Lazily instantiated async client — one per process."""
    return AsyncOpenAI(
        api_key=settings.OPENAI_API_KEY,   # Ollama ignores the value, but the SDK requires non-empty
        base_url=settings.OPENAI_BASE_URL, # e.g. http://localhost:11434/v1
        timeout=_TIMEOUT_SECONDS,
    )


async def stream_response(
    messages: list[dict],
    query_id: UUID,
    citations_payload: list[dict],
    confidence_payload: dict,
    conflicts_payload: list[dict],
) -> AsyncGenerator[str, None]:
    """
    Calls the LLM with streaming enabled and yields SSE-formatted strings.

    Yields:
        Strings in SSE format: "data: {json}\\n\\n"
        (FastAPI's StreamingResponse handles the HTTP framing.)
    """
    client = _get_client()
    start = time.monotonic()
    token_count = 0

    logger.info("Stream started query_id=%s model=%s", query_id, _MODEL)

    try:
        stream = await client.chat.completions.create(
            model=_MODEL,
            max_tokens=_MAX_TOKENS,
            messages=messages,
            stream=True,
        )

        async for event in stream:
            if not event.choices:
                continue

            choice = event.choices[0]
            logger.info("Chunk received query_id=%s", query_id)

            if choice.delta and choice.delta.content:
                token_count += 1
                yield _sse({"type": "token", "content": choice.delta.content})

            if choice.finish_reason is not None:
                break

        logger.info(
            "Stream finished query_id=%s tokens=%d elapsed_ms=%.1f",
            query_id, token_count, (time.monotonic() - start) * 1000,
        )

    except Exception:
        logger.exception("LLM STREAM FAILED query_id=%s", query_id)
        raise

    # Emit metadata events after successful stream completion.
    yield _sse({"type": "citations",  "citations": citations_payload})
    yield _sse({"type": "confidence", **confidence_payload})
    yield _sse({"type": "conflicts",  "conflicts": conflicts_payload})
    yield _sse({"type": "done",       "query_id": str(query_id)})


async def complete_response(
    messages: list[dict],
) -> tuple[str, int, int]:
    """
    Non-streaming call — returns the complete answer text and token counts.

    Returns:
        (answer_text, input_tokens, output_tokens)

    Raises:
        LLMUnavailableError if the API call fails — caller handles this.
    """
    client = _get_client()

    try:
        response = await client.chat.completions.create(
            model=_MODEL,
            max_completion_tokens=_MAX_TOKENS,
            messages=messages,
        )
        answer = response.choices[0].message.content
        if answer is None:
            answer = ""
        return answer, response.usage.prompt_tokens, response.usage.completion_tokens

    except openai.APITimeoutError as exc:
        raise LLMUnavailableError("LLM API timed out.") from exc
    except openai.APIStatusError as exc:
        raise LLMUnavailableError(f"LLM API error {exc.status_code}.") from exc
    except Exception as exc:  # noqa: BLE001
        raise LLMUnavailableError(str(exc)) from exc


def _sse(payload: dict) -> str:
    """Format a dict as a single SSE data line."""
    return f"data: {json.dumps(payload)}\n\n"


class LLMUnavailableError(Exception):
    """Raised by complete_response() — caught by copilot_v2 service."""
    pass