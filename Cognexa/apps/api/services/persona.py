"""
apps/api/services/persona.py

Phase 6 — AI Shadow Engineer.

Captures expert-authored tacit knowledge, embeds + indexes it into its
own Weaviate collection (see weaviate_client.py::ensure_expert_knowledge_schema),
and retrieves it for persona-aware copilot answers.

KEY REUSE DECISION: get_persona_chunks() returns results already adapted
into RetrievedChunk (the same type Phase 4's retrieval pipeline produces)
so services/copilot_v2.py can splice them into retrieval_result.chunks
BEFORE calling assemble_context() — meaning the existing citation
formatting, confidence engine, and reranker all handle persona-authored
content automatically, with zero changes to any of those files. See
services/copilot_v2.py's two call sites for the (~3-line) splice.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select, func as sa_func
from sqlalchemy.ext.asyncio import AsyncSession
from weaviate.classes.query import Filter, MetadataQuery

from apps.api.models import ExpertKnowledgeEntry, User
from apps.api.schemas.retrieval import RetrievedChunk
from apps.api.services.embedder import embed_texts
from apps.api.weaviate_client import get_weaviate_client, EXPERT_KNOWLEDGE_CLASS

logger = logging.getLogger("indus_mind.persona")

# Persona-authored content is first-hand expert testimony, not a formal
# reviewed document — trust_score is deliberately high (experts are
# trusted by definition) but not automatically 1.0/superseded-proof the
# way a freshly-ingested procedure would be; this value feeds into the
# same confidence-engine math Phase 4 already uses for every other chunk.
PERSONA_CHUNK_TRUST_SCORE = 0.9


async def capture_entry(
    db: AsyncSession,
    author_user_id: str,
    title: str,
    content: str,
    asset_id: Optional[str],
    tags: Optional[list[str]],
) -> ExpertKnowledgeEntry:
    """Creates the Postgres row, embeds the content, and indexes it into Weaviate."""
    entry = ExpertKnowledgeEntry(
        author_user_id=author_user_id,
        asset_id=asset_id,
        title=title,
        content=content,
        tags=tags or [],
    )
    db.add(entry)
    await db.flush()  # assigns entry.id without committing yet

    weaviate_id = str(uuid4())
    try:
        vector = embed_texts([content])[0]
        client = get_weaviate_client()
        collection = client.collections.get(EXPERT_KNOWLEDGE_CLASS)
        collection.data.insert(
            uuid=weaviate_id,
            vector=vector,
            properties={
                "entry_id": entry.id,
                "author_user_id": author_user_id,
                "asset_id": asset_id or "",
                "title": title,
                "content": content,
                "tags": tags or [],
            },
        )
        entry.weaviate_id = weaviate_id
    except Exception as exc:  # noqa: BLE001
        # Postgres row is still useful on its own (visible via list_entries),
        # even if indexing failed — don't roll back the capture just
        # because the embedding/Weaviate step failed. Retrying indexing
        # for entries with weaviate_id=None can be added as a small
        # follow-up job if this turns out to happen often in practice.
        logger.warning("Failed to index expert knowledge entry into Weaviate: %s", exc)

    await db.commit()
    await db.refresh(entry)
    return entry


async def list_entries(
    db: AsyncSession,
    author_user_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    include_inactive: bool = False,
) -> list[ExpertKnowledgeEntry]:
    query = select(ExpertKnowledgeEntry)
    if author_user_id:
        query = query.where(ExpertKnowledgeEntry.author_user_id == author_user_id)
    if asset_id:
        query = query.where(ExpertKnowledgeEntry.asset_id == asset_id)
    if not include_inactive:
        query = query.where(ExpertKnowledgeEntry.is_active.is_(True))
    query = query.order_by(ExpertKnowledgeEntry.created_at.desc())
    result = await db.execute(query)
    return list(result.scalars().all())


async def deactivate_entry(db: AsyncSession, entry_id: str, requesting_user_id: str, is_admin: bool) -> ExpertKnowledgeEntry:
    result = await db.execute(select(ExpertKnowledgeEntry).where(ExpertKnowledgeEntry.id == entry_id))
    entry = result.scalar_one_or_none()
    if entry is None:
        raise ValueError(f"Expert knowledge entry {entry_id} not found.")
    if entry.author_user_id != requesting_user_id and not is_admin:
        raise PermissionError("Only the author or an admin can remove this entry.")

    entry.is_active = False
    await db.commit()

    if entry.weaviate_id:
        try:
            client = get_weaviate_client()
            client.collections.get(EXPERT_KNOWLEDGE_CLASS).data.delete_by_id(entry.weaviate_id)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Failed to remove entry %s from Weaviate: %s", entry_id, exc)

    await db.refresh(entry)
    return entry


async def list_experts(db: AsyncSession) -> list[tuple[str, str, int]]:
    """
    Returns (user_id, full_name, entry_count) for every user with at
    least one active expert-knowledge entry — the "persona selector"
    dropdown's data source.
    """
    result = await db.execute(
        select(User.id, User.full_name, sa_func.count(ExpertKnowledgeEntry.id))
        .join(ExpertKnowledgeEntry, ExpertKnowledgeEntry.author_user_id == User.id)
        .where(ExpertKnowledgeEntry.is_active.is_(True))
        .group_by(User.id, User.full_name)
    )
    return [(uid, name, count) for uid, name, count in result.all()]


async def get_persona_chunks(
    query: str,
    persona_user_id: str,
    asset_id: Optional[str] = None,
    top_k: int = 5,
) -> list[RetrievedChunk]:
    """
    Vector search restricted to a single expert's ExpertKnowledge entries.
    Returns results already adapted into RetrievedChunk so the caller
    (services/copilot_v2.py) can splice them directly into
    retrieval_result.chunks before assemble_context() — see this module's
    docstring.
    """
    vector = embed_texts([query])[0]
    client = get_weaviate_client()
    collection = client.collections.get(EXPERT_KNOWLEDGE_CLASS)

    filters = Filter.by_property("author_user_id").equal(persona_user_id)
    if asset_id:
        filters = filters & Filter.by_property("asset_id").equal(asset_id)

    response = collection.query.near_vector(
        near_vector=vector,
        limit=top_k,
        filters=filters,
        return_metadata=MetadataQuery(distance=True),
    )

    chunks: list[RetrievedChunk] = []
    for rank, obj in enumerate(response.objects, start=1):
        props = obj.properties
        distance = float(obj.metadata.distance) if obj.metadata.distance is not None else 1.0
        similarity = max(0.0, 1.0 - (distance / 2.0))

        chunk = RetrievedChunk(
            chunk_id=UUID(props["entry_id"]) if _is_uuid(props.get("entry_id")) else uuid4(),
            document_id=UUID(props["entry_id"]) if _is_uuid(props.get("entry_id")) else uuid4(),
            document_title=f"{props.get('title', 'Expert note')} (persona knowledge)",
            content=props.get("content", ""),
            chunk_type="persona_knowledge",
            trust_score=PERSONA_CHUNK_TRUST_SCORE,
            asset_ids=[UUID(props["asset_id"])] if _is_uuid(props.get("asset_id")) else [],
        )
        chunk.source_ranks["vector"] = rank
        chunk.source_scores["vector"] = similarity
        chunks.append(chunk)

    return chunks


def _is_uuid(value: Optional[str]) -> bool:
    if not value:
        return False
    try:
        UUID(value)
        return True
    except ValueError:
        return False
