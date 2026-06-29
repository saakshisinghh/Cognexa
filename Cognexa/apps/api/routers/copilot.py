"""
Copilot Router — Conversational RAG interface with streaming.
"""
from __future__ import annotations
import logging
import math
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from apps.api.db import get_db
from apps.api.models import Conversation, Message, User, Document
from apps.api.routers.auth import get_current_user
from apps.api.schemas import (
    ConversationCreate, ConversationResponse, ConversationListResponse,
    MessageCreate, MessageResponse
)
from apps.api.services import rag as rag_svc
from apps.api.weaviate_client import get_weaviate_client

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/copilot", tags=["Copilot"])


# ─── Conversations ────────────────────────────────────────────────────────────

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


# ─── Messages (Non-streaming) ─────────────────────────────────────────────────

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

    # Save user message
    user_msg = Message(
        conversation_id=conversation_id,
        role="user",
        content=payload.content,
    )
    db.add(user_msg)
    db.commit()

    # Build history
    history = [
        {"role": m.role, "content": m.content}
        for m in convo.messages[:-1]  # exclude the just-added user msg
    ]

    # RAG answer
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

    # Save assistant message
    assistant_msg = Message(
        conversation_id=conversation_id,
        role="assistant",
        content=result["content"],
        sources=result["sources"],
        confidence=result["confidence"],
        tokens_used=result["tokens_used"],
    )
    db.add(assistant_msg)

    # Update conversation title if first exchange
    if len(convo.messages) <= 2 and convo.title in ("New Conversation", None):
        convo.title = payload.content[:60] + ("…" if len(payload.content) > 60 else "")

    db.commit()
    db.refresh(assistant_msg)
    return assistant_msg


# ─── Streaming Chat ───────────────────────────────────────────────────────────

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

    # Save user message
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
            # Parse chunk to accumulate content
            try:
                import json
                data = json.loads(chunk.replace("data: ", "").strip())
                if data.get("type") == "chunk":
                    full_content += data.get("content", "")
                elif data.get("type") == "done":
                    sources = data.get("sources", [])
                    confidence = data.get("confidence", 0.0)
            except Exception:
                pass

        # Persist assistant message after stream completes
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
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
