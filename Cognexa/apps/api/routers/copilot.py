"""
apps/api/routers/copilot.py

Phase 4 section notes:
  1. Phase 4 routes use AsyncSession (get_async_db) — the async engine
     apps/api/db.py sets up specifically for the Phase 4 copilot service,
     which is written against AsyncSession throughout.
  2. current_user.id is a String — type hints reflect that.
  3. Phase 4 service imports come from apps.api.services.copilot_v2
     (not apps.api.services.rag, which is the Phase 1 basic RAG service).
  4. Phase 1 stubs (/chat, /history) replaced with real Phase 1 implementation
     delegation — they call rag_svc and the existing Conversation/Message models.

Phase 1 routes preserved exactly (still sync Session / get_db, unchanged).
"""

import json
import logging
import math
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from apps.api.db import get_db
from apps.api.routers.auth import get_current_user
from apps.api.models import Conversation, Message, User, Document
from apps.api.schemas import (
    ConversationCreate, ConversationResponse, ConversationListResponse,
    MessageCreate, MessageResponse,
)
from apps.api.services import rag as rag_svc
from apps.api.weaviate_client import get_weaviate_client

logger = logging.getLogger("indusmind.routers.copilot")

router = APIRouter(prefix="/copilot", tags=["Copilot"])


# ════════════════════════════════════════════════════════════════════════════
#  PHASE 1 ROUTES — preserved exactly
# ════════════════════════════════════════════════════════════════════════════

@router.post("/conversations", response_model=ConversationResponse, status_code=201)
def create_conversation(
    payload: ConversationCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    if payload.document_id:
        doc = db.query(Document).filter(Document.id == payload.document_id).first()
        if not doc:
            raise HTTPException(404, "Document not found")

    convo = Conversation(
        title=payload.title or "New Conversation",
        user_id=current_user.id,
        document_id=payload.document_id,
    )
    db.add(convo)
    db.commit()
    db.refresh(convo)
    return convo


@router.get("/conversations", response_model=ConversationListResponse)
def list_conversations(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    query = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
    )
    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    return ConversationListResponse(items=items, total=total)


@router.get("/conversations/{conversation_id}", response_model=ConversationResponse)
def get_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not convo:
        raise HTTPException(404, "Conversation not found")
    return convo


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete_conversation(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not convo:
        raise HTTPException(404, "Conversation not found")
    db.delete(convo)
    db.commit()


@router.post("/conversations/{conversation_id}/messages", response_model=MessageResponse)
async def send_message(
    conversation_id: str,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not convo:
        raise HTTPException(404, "Conversation not found")

    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
    )
    db.add(user_msg)
    db.commit()

    history = [
        {"role": m.role, "content": m.content}
        for m in convo.messages[:-1]
    ]

    try:
        wv_client = get_weaviate_client()
        result = await rag_svc.generate_answer(
            question=payload.content,
            weaviate_client=wv_client,
            history=history,
            document_id=convo.document_id,
        )
    except Exception as e:
        logger.error(f"RAG error: {e}")
        result = {
            "content": "I encountered an error generating a response. Please try again.",
            "sources": [],
            "confidence": 0.0,
            "tokens_used": 0,
        }

    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=result["content"],
        sources=result["sources"],
        confidence=result["confidence"],
        tokens_used=result["tokens_used"],
    )
    db.add(assistant_msg)

    if len(convo.messages) <= 2 and convo.title in ("New Conversation", None):
        convo.title = payload.content[:60] + ("…" if len(payload.content) > 60 else "")

    db.commit()
    db.refresh(assistant_msg)
    return assistant_msg


@router.post("/conversations/{conversation_id}/messages/stream")
async def stream_message(
    conversation_id: str,
    payload: MessageCreate,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    convo = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id,
    ).first()
    if not convo:
        raise HTTPException(404, "Conversation not found")

    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
    )
    db.add(user_msg)
    db.commit()

    history = [
        {"role": m.role, "content": m.content}
        for m in convo.messages[:-1]
    ]

    async def event_stream():
        full_content = ""
        sources = []
        confidence = 0.0
        wv_client = get_weaviate_client()

        async for chunk in rag_svc.generate_answer_stream(
            question=payload.content,
            weaviate_client=wv_client,
            history=history,
            document_id=convo.document_id,
        ):
            yield chunk
            try:
                data = json.loads(chunk.replace("data: ", "").strip())
                if data.get("type") == "chunk":
                    full_content += data.get("content", "")
                elif data.get("type") == "done":
                    sources = data.get("sources", [])
                    confidence = data.get("confidence", 0.0)
            except Exception:
                pass

        try:
            from apps.api.db import SessionLocal
            with SessionLocal() as save_db:
                assistant_msg = Message(
                    conversation_id=conversation_id,
                    role="assistant",
                    content=full_content,
                    sources=sources,
                    confidence=confidence,
                    tokens_used=len(full_content) // 4,
                )
                save_db.add(assistant_msg)
                c = save_db.query(Conversation).filter(Conversation.id == conversation_id).first()
                if c and c.title in ("New Conversation", None):
                    c.title = payload.content[:60]
                save_db.commit()
        except Exception as e:
            logger.error(f"Failed to persist streamed message: {e}")

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


# ════════════════════════════════════════════════════════════════════════════
#  PHASE 4 ADDITIONS — FIX: AsyncSession → Session, user_id → str
# ════════════════════════════════════════════════════════════════════════════

from sqlalchemy.ext.asyncio import AsyncSession

from apps.api.db import get_async_db
from apps.api.schemas.copilot_v2 import (
    CopilotV2ChatRequest,
    CopilotV2ChatResponse,
    PinAssetRequest,
    FeedbackRequest,
    SessionDetailResponse,
    SessionSummary,
)
from apps.api.services.copilot_v2 import (
    handle_chat_stream,
    handle_chat_complete,
    get_or_create_session,
    pin_asset_to_session,
    list_sessions,
    get_session_detail,
    submit_feedback,
)
from apps.api.services.prompt_engine import PromptInjectionDetectedError
from apps.api.services.retrieval import RetrievalUnavailableError
from apps.api.services.llm_gateway import LLMUnavailableError


@router.post("/v2/chat")
async def chat_v2(
    body: CopilotV2ChatRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    user_id: str = str(current_user.id)

    if body.stream:
        async def _generate():
            try:
                async for event in handle_chat_stream(request=body, user_id=user_id, db=db):
                    yield event
            except Exception:
                logger.exception("FULL TRACEBACK")
                raise

        return StreamingResponse(
            _generate(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )
    else:
        try:
            return await handle_chat_complete(request=body, user_id=user_id, db=db)
        except PromptInjectionDetectedError as exc:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc))
        except RetrievalUnavailableError as exc:
            raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc))
        except LLMUnavailableError as exc:
            raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=str(exc))
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/v2/sessions", response_model=list[SessionSummary])
async def get_sessions(
    include_archived: bool = False,
    limit: int = 20,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    return await list_sessions(
        db=db,
        user_id=str(current_user.id),
        limit=min(limit, 50),
        include_archived=include_archived,
    )


@router.get("/v2/sessions/{session_id}", response_model=SessionDetailResponse)
async def get_session(
    session_id: str,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    try:
        return await get_session_detail(db=db, session_id=session_id, user_id=str(current_user.id))
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/v2/sessions/{session_id}/pin-asset")
async def pin_asset(
    session_id: str,
    body: PinAssetRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    try:
        session = await pin_asset_to_session(
            db=db,
            session_id=session_id,
            user_id=str(current_user.id),
            asset_id=body.asset_id,
            asset_tag=body.asset_tag,
        )
        return {
            "session_id": str(session.id),
            "pinned_asset_id": session.pinned_asset_id,
            "pinned_asset_tag": session.pinned_asset_tag,
        }
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc))


@router.post("/v2/feedback")
async def post_feedback(
    body: FeedbackRequest,
    db: AsyncSession = Depends(get_async_db),
    current_user=Depends(get_current_user),
):
    try:
        await submit_feedback(
            db=db,
            query_id=body.query_id,
            user_id=str(current_user.id),
            feedback=body.feedback,
        )
        return {"status": "recorded"}
    except Exception as exc:
        logger.warning("feedback_failed query_id=%s error=%s", body.query_id, str(exc))
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to record feedback.",
        )