"""
apps/api/agents/memory.py

Phase 5 — short-term execution memory.

REUSES the existing Phase 2 Redis connection pool (apps/api/redis_client.py)
instead of standing up a second cache. Memory here is explicitly SHORT-TERM
and EXECUTION-SCOPED:

    - Conversation (messages exchanged during this execution / chat turn)
    - Intermediate results (partial tool/retrieval outputs during a run)
    - Tool outputs
    - Current goal
    - Execution state (the full AgentState snapshot, for resume/inspection)

Long-term organizational memory (cross-execution knowledge persistence,
decay scoring, gap detection) is explicitly OUT OF SCOPE for Phase 5 and
reserved for Phase 6's Temporal Memory Engine — this module must not grow
into that.

Every key is namespaced under `agent:mem:{execution_id}:*` and expires
automatically (default 24h) so short-term memory never silently becomes
long-term storage by accident.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

from apps.api.redis_client import get_redis

logger = logging.getLogger("indusmind.agents.memory")

_DEFAULT_TTL_SECONDS = 60 * 60 * 24  # 24h — short-term by construction
_KEY_PREFIX = "agent:mem"


def _key(execution_id: str, field: str) -> str:
    return f"{_KEY_PREFIX}:{execution_id}:{field}"


class ExecutionMemory:
    """
    Thin, execution-scoped key/value + list store on top of Redis.

    Falls back to an in-process dict if Redis is unreachable, so a single
    agent run degrades gracefully instead of failing outright (Redis being
    down should not stop an in-flight LangGraph execution — it only means
    the run can't be inspected/resumed by another process).
    """

    def __init__(self, execution_id: str, ttl_seconds: int = _DEFAULT_TTL_SECONDS):
        self.execution_id = execution_id
        self.ttl_seconds = ttl_seconds
        self._local_fallback: dict[str, Any] = {}
        self._redis_ok = True

    # ── generic state snapshot ──────────────────────────────────────────

    def save_state(self, state: dict) -> None:
        payload = json.dumps(state, default=str)
        self._set(_key(self.execution_id, "state"), payload)

    def load_state(self) -> Optional[dict]:
        raw = self._get(_key(self.execution_id, "state"))
        return json.loads(raw) if raw else None

    # ── goal ─────────────────────────────────────────────────────────────

    def set_goal(self, goal: str) -> None:
        self._set(_key(self.execution_id, "goal"), goal)

    def get_goal(self) -> Optional[str]:
        return self._get(_key(self.execution_id, "goal"))

    # ── conversation ─────────────────────────────────────────────────────

    def append_message(self, role: str, content: str) -> None:
        self._rpush(_key(self.execution_id, "conversation"), json.dumps({"role": role, "content": content}))

    def get_conversation(self) -> list[dict]:
        raw_items = self._lrange(_key(self.execution_id, "conversation"))
        return [json.loads(item) for item in raw_items]

    # ── intermediate / tool results ─────────────────────────────────────

    def record_tool_output(self, tool_name: str, output: Any) -> None:
        self._rpush(
            _key(self.execution_id, "tool_outputs"),
            json.dumps({"tool": tool_name, "output": output}, default=str),
        )

    def get_tool_outputs(self) -> list[dict]:
        raw_items = self._lrange(_key(self.execution_id, "tool_outputs"))
        return [json.loads(item) for item in raw_items]

    def record_intermediate(self, label: str, value: Any) -> None:
        self._rpush(
            _key(self.execution_id, "intermediate"),
            json.dumps({"label": label, "value": value}, default=str),
        )

    def get_intermediate(self) -> list[dict]:
        raw_items = self._lrange(_key(self.execution_id, "intermediate"))
        return [json.loads(item) for item in raw_items]

    # ── lifecycle ────────────────────────────────────────────────────────

    def clear(self) -> None:
        for field in ("state", "goal", "conversation", "tool_outputs", "intermediate"):
            self._delete(_key(self.execution_id, field))

    # ── low-level Redis helpers (with local fallback) ───────────────────

    def _set(self, key: str, value: str) -> None:
        try:
            get_redis().set(key, value, ex=self.ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent_memory_redis_unavailable op=set key=%s error=%s", key, exc)
            self._local_fallback[key] = value

    def _get(self, key: str) -> Optional[str]:
        try:
            value = get_redis().get(key)
            return value.decode() if isinstance(value, bytes) else value
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent_memory_redis_unavailable op=get key=%s error=%s", key, exc)
            return self._local_fallback.get(key)

    def _rpush(self, key: str, value: str) -> None:
        try:
            r = get_redis()
            r.rpush(key, value)
            r.expire(key, self.ttl_seconds)
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent_memory_redis_unavailable op=rpush key=%s error=%s", key, exc)
            self._local_fallback.setdefault(key, []).append(value)

    def _lrange(self, key: str) -> list[str]:
        try:
            items = get_redis().lrange(key, 0, -1)
            return [item.decode() if isinstance(item, bytes) else item for item in items]
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent_memory_redis_unavailable op=lrange key=%s error=%s", key, exc)
            return self._local_fallback.get(key, [])

    def _delete(self, key: str) -> None:
        try:
            get_redis().delete(key)
        except Exception as exc:  # noqa: BLE001
            logger.warning("agent_memory_redis_unavailable op=delete key=%s error=%s", key, exc)
            self._local_fallback.pop(key, None)
