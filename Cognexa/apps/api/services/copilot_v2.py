"""
apps/api/services/copilot_v2.py


"""

from __future__ import annotations

import json
import logging
import time
from typing import AsyncGenerator, Optional
from uuid import UUID, uuid4

from sqlalchemy import select, text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.models.conversation import ConversationSession
from apps.api.schemas.copilot_v2 import (
    CopilotV2ChatRequest,
    CopilotV2ChatResponse,
    CitationItem,
    SessionSummary,
    SessionDetailResponse,
)
from apps.api.schemas.retrieval import RetrievalFilters
from apps.api.schemas.confidence import ConflictFlag
from apps.api.services.retrieval import run_triple_retrieval, RetrievalUnavailableError
from apps.api.services.context_assembler import assemble_context
from apps.api.services.prompt_engine import (
    build_messages,
    check_prompt_injection,
    PromptInjectionDetectedError,
)
from apps.api.services.llm_gateway import (
    stream_response,
    complete_response,
    LLMUnavailableError,
    _sse,
)

logger = logging.getLogger("indus_mind.copilot_v2")


# ─── Session management (async) ────────────────────────────────────────────

async def get_or_create_session(
    db: AsyncSession,
    user_id: str,
    session_id: Optional[str],
    plant_id: Optional[str],
) -> ConversationSession:
    if session_id:
        result = await db.execute(
            select(ConversationSession).where(
                ConversationSession.id == session_id,
                ConversationSession.user_id == user_id,
                ConversationSession.is_archived == False,
            )
        )
        session = result.scalar_one_or_none()
        if session is None:
            raise ValueError(f"Session {session_id} not found or does not belong to this user.")
        return session

    session = ConversationSession(user_id=user_id, plant_id=plant_id)
    db.add(session)
    await db.flush()
    return session


async def pin_asset_to_session(
    db: AsyncSession,
    session_id: str,
    user_id: str,
    asset_id: Optional[str],
    asset_tag: Optional[str],
) -> ConversationSession:
    result = await db.execute(
        select(ConversationSession).where(
            ConversationSession.id == session_id,
            ConversationSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise ValueError(f"Session {session_id} not found.")
    session.pin_asset(asset_id=asset_id, asset_tag=asset_tag)
    await db.commit()
    await db.refresh(session)
    return session


async def list_sessions(
    db: AsyncSession,
    user_id: str,
    limit: int = 20,
    include_archived: bool = False,
) -> list[SessionSummary]:
    query = (
        select(ConversationSession)
        .where(ConversationSession.user_id == user_id)
        .order_by(ConversationSession.last_active_at.desc())
        .limit(limit)
    )
    if not include_archived:
        query = query.where(ConversationSession.is_archived == False)
    result = await db.execute(query)
    sessions = result.scalars().all()
    return [_to_summary(s) for s in sessions]


async def get_session_detail(
    db: AsyncSession,
    session_id: str,
    user_id: str,
) -> SessionDetailResponse:
    result = await db.execute(
        select(ConversationSession).where(
            ConversationSession.id == session_id,
            ConversationSession.user_id == user_id,
        )
    )
    session = result.scalar_one_or_none()
    if session is None:
        raise ValueError(f"Session {session_id} not found.")
    return SessionDetailResponse(
        session=_to_summary(session),
        recent_messages=session.recent_messages,
    )


def _to_summary(s: ConversationSession) -> SessionSummary:
    return SessionSummary(
        session_id=s.id,
        title=s.title,
        message_count=s.message_count,
        pinned_asset_tag=s.pinned_asset_tag,
        last_active_at=s.last_active_at.isoformat() if s.last_active_at else None,
        is_archived=s.is_archived,
    )


# ─── Main copilot orchestration ────────────────────────────────────────────

async def handle_chat_stream(
    request: CopilotV2ChatRequest,
    user_id: str,
    db: AsyncSession,
) -> AsyncGenerator[str, None]:
    query_id = uuid4()
    pipeline_start = time.monotonic()

    try:
        check_prompt_injection(request.query)
    except PromptInjectionDetectedError as exc:
        yield _sse({"type": "error", "message": str(exc), "query_id": str(query_id)})
        return

    try:
        session = await get_or_create_session(
            db=db, user_id=user_id,
            session_id=str(request.session_id) if request.session_id else None,
            plant_id=request.plant_id,
        )
    except ValueError as exc:
        yield _sse({"type": "error", "message": str(exc), "query_id": str(query_id)})
        return

    asset_id = request.asset_id or session.pinned_asset_id
    filters = RetrievalFilters(
        document_type=request.document_type,
        asset_id=asset_id,
        plant_id=request.plant_id or session.plant_id,
    )

    try:
        retrieval_result = await run_triple_retrieval(query=request.query, filters=filters)
    except RetrievalUnavailableError as exc:
        logger.error("retrieval_unavailable session_id=%s error=%s", session.id, str(exc))
        yield _sse({"type": "error", "message": "Document search is temporarily unavailable. Please retry.", "query_id": str(query_id)})
        return
    except Exception as exc:
        logger.exception("retrieval_unexpected session_id=%s", session.id)
        yield _sse({"type": "error", "message": "An error occurred while searching documents.", "query_id": str(query_id)})
        return

    context_str, citations = assemble_context(retrieval_result.chunks)

    stats = retrieval_result.source_stats
    graph_context_note: Optional[str] = None
    if stats.graph_count > 0 and stats.detected_asset_tags:
        graph_context_note = (
            f"{stats.graph_count} knowledge graph result(s) retrieved for asset(s): "
            f"{', '.join(stats.detected_asset_tags)}."
        )

    messages = build_messages(
        query=request.query,
        context_str=context_str,
        conversation_history=session.recent_messages,
        pinned_asset_tag=session.pinned_asset_tag,
        conflicts=retrieval_result.conflicts or [],
        graph_context_note=graph_context_note,
    )

    citations_payload = [c.model_dump(mode="json") for c in citations]
    confidence = retrieval_result.confidence
    confidence_payload = {
        "level": confidence.level.value if confidence else "low",
        "score": confidence.raw_score if confidence else 0.0,
        "explanation": confidence.explanation if confidence else "",
    }
    conflicts_payload = [f.model_dump(mode="json") for f in (retrieval_result.conflicts or [])]

    full_answer_parts: list[str] = []

    logger.info("Calling LLM query_id=%s", query_id)

    async for event in stream_response(
        messages=messages,
        query_id=query_id,
        citations_payload=citations_payload,
        confidence_payload=confidence_payload,
        conflicts_payload=conflicts_payload,
    ):
        logger.info("Forward SSE query_id=%s", query_id)
        if '"type": "token"' in event:
            try:
                payload = json.loads(event.removeprefix("data: ").strip())
                if payload.get("type") == "token":
                    full_answer_parts.append(payload.get("content", ""))
            except (json.JSONDecodeError, AttributeError):
                pass
        yield event

    full_answer = "".join(full_answer_parts)
    elapsed_ms = round((time.monotonic() - pipeline_start) * 1000)

    logger.info("Persist query query_id=%s", query_id)

    await _persist_query(
        db=db,
        query_id=query_id,
        session=session,
        user_id=user_id,
        query=request.query,
        answer=full_answer,
        citations=citations,
        retrieval_result=retrieval_result,
        elapsed_ms=elapsed_ms,
    )

    try:
        session.set_title_from_query(request.query)
        session.append_message("user", request.query)
        session.append_message("assistant", full_answer[:2000])
        await db.commit()
    except Exception as exc:
        # The answer was already streamed to the user (the "done" SSE event
        # was sent inside stream_response() above) — a failure saving the
        # session title/message history must not surface as a crash or a
        # spurious extra "error" event after a successful answer.
        logger.warning(
            "Failed to save session history session_id=%s query_id=%s error=%s",
            session.id, query_id, exc,
        )
        await db.rollback()


async def handle_chat_complete(
    request: CopilotV2ChatRequest,
    user_id: str,
    db: AsyncSession,
) -> CopilotV2ChatResponse:
    query_id = uuid4()
    pipeline_start = time.monotonic()

    check_prompt_injection(request.query)

    session = await get_or_create_session(
        db=db, user_id=user_id,
        session_id=str(request.session_id) if request.session_id else None,
        plant_id=request.plant_id,
    )

    asset_id = request.asset_id or session.pinned_asset_id
    filters = RetrievalFilters(
        document_type=request.document_type,
        asset_id=asset_id,
        plant_id=request.plant_id or session.plant_id,
    )

    retrieval_result = await run_triple_retrieval(query=request.query, filters=filters)
    context_str, citations = assemble_context(retrieval_result.chunks)

    stats = retrieval_result.source_stats
    graph_context_note = (
        f"{stats.graph_count} graph result(s) for {', '.join(stats.detected_asset_tags)}."
        if stats.graph_count > 0 and stats.detected_asset_tags else None
    )

    messages = build_messages(
        query=request.query,
        context_str=context_str,
        conversation_history=session.recent_messages,
        pinned_asset_tag=session.pinned_asset_tag,
        conflicts=retrieval_result.conflicts or [],
        graph_context_note=graph_context_note,
    )

    logger.info("Calling LLM query_id=%s", query_id)
    answer, _, _ = await complete_response(messages)
    elapsed_ms = round((time.monotonic() - pipeline_start) * 1000)

    logger.info("Persist query query_id=%s", query_id)

    await _persist_query(
        db=db, query_id=query_id, session=session, user_id=user_id,
        query=request.query, answer=answer, citations=citations,
        retrieval_result=retrieval_result, elapsed_ms=elapsed_ms,
    )

    try:
        session.set_title_from_query(request.query)
        session.append_message("user", request.query)
        session.append_message("assistant", answer[:2000])
        await db.commit()
    except Exception as exc:
        # The LLM answer was already generated successfully above — a
        # failure saving the session title/message history must not
        # prevent the (already-complete) answer from being returned to
        # the user as a 500. Log and continue; return the answer below
        # exactly as if the save had succeeded.
        logger.warning(
            "Failed to save session history session_id=%s query_id=%s error=%s",
            session.id, query_id, exc,
        )
        await db.rollback()

    confidence = retrieval_result.confidence
    return CopilotV2ChatResponse(
        query_id=query_id,
        session_id=session.id,
        answer=answer,
        citations=citations,
        confidence_level=confidence.level if confidence else "low",
        confidence_score=confidence.raw_score if confidence else 0.0,
        confidence_explanation=confidence.explanation if confidence else "",
        conflicts=retrieval_result.conflicts or [],
        has_conflict=bool(retrieval_result.conflicts),
        elapsed_ms=elapsed_ms,
    )


async def submit_feedback(
    db: AsyncSession,
    query_id: UUID,
    user_id: str,
    feedback: str,
) -> None:
    """
    FIX: Original referenced `QueryHistoryTable` which was never defined.
    Using raw SQL text() — same pattern as _persist_query — to safely update
    the feedback column without importing the Phase 1 ORM model.
    """
    await db.execute(
        sa_text("UPDATE query_history SET feedback = :feedback WHERE id = :id"),
        {"feedback": feedback, "id": str(query_id)},
    )
    await db.commit()


async def _persist_query(
    db: AsyncSession,
    query_id: UUID,
    session: ConversationSession,
    user_id: str,
    query: str,
    answer: str,
    citations: list[CitationItem],
    retrieval_result,
    elapsed_ms: int,
) -> None:
    """Persists the query/response/retrieval metadata to query_history."""
    confidence = retrieval_result.confidence
    conflicts = retrieval_result.conflicts or []
    stats = retrieval_result.source_stats

    try:
        async with db.begin_nested():  # SAVEPOINT — isolates this INSERT from the outer transaction
            await db.execute(sa_text("""
                INSERT INTO query_history (
                    id, user_id, query_text, response_text, retrieved_chunks,
                    session_id, confidence_level, confidence_score,
                    conflict_detected, conflict_count, conflicts_json,
                    retrieval_stats_json, elapsed_ms, created_at
                ) VALUES (
                    :id, :user_id, :query_text, :response_text, :retrieved_chunks::jsonb,
                    :session_id, :confidence_level, :confidence_score,
                    :conflict_detected, :conflict_count, :conflicts_json,
                    :retrieval_stats_json, :elapsed_ms, NOW()
                )
            """), {
                "id": str(query_id),
                "user_id": str(user_id),
                "query_text": query,
                "response_text": answer,
                "retrieved_chunks": json.dumps([str(c.chunk_id) for c in citations]),
                "session_id": str(session.id),
                "confidence_level": confidence.level.value if confidence else None,
                "confidence_score": float(confidence.raw_score) if confidence else None,
                "conflict_detected": bool(conflicts),
                "conflict_count": len(conflicts),
                "conflicts_json": json.dumps([c.model_dump(mode="json") for c in conflicts]),
                "retrieval_stats_json": json.dumps(stats.model_dump()),
                "elapsed_ms": elapsed_ms,
            })
    except Exception as exc:
        # SAVEPOINT already rolled back automatically by begin_nested()'s
        # __aexit__ on exception — the outer transaction (session title/
        # message updates, still pending in this same `db`) is NOT aborted
        # and the caller's subsequent `await db.commit()` will still work.
        # Without begin_nested(), a failed INSERT here would leave the
        # whole Postgres transaction in an aborted state, and the very
        # next statement on `db` (including the session commit) would also
        # fail — which is exactly what was happening before this fix.
        logger.warning(
            "Failed to persist query_history row query_id=%s error=%s",
            query_id, exc,
        )