"""
RAG Pipeline Service — Retrieval-Augmented Generation.
Retrieves relevant chunks, assembles context, calls LLM, streams response.
"""
from __future__ import annotations
import logging
import time
import json
from typing import AsyncGenerator, List, Optional, Dict, Any

import httpx
from weaviate.classes.query import MetadataQuery, Filter

from apps.api.config import settings
from apps.api.services.embedder import embed_texts
from apps.api.weaviate_client import CHUNK_CLASS

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are INDUS MIND Copilot, an expert AI assistant for industrial enterprises.
You help engineers, operators, and managers understand technical documents, manuals, procedures, 
failure reports, and maintenance records.

Guidelines:
- Answer based ONLY on the provided context. If the answer is not in the context, say so clearly.
- Be precise and technical. Use correct industrial terminology.
- Cite the source document and page number when relevant.
- If multiple sources are relevant, synthesize them coherently.
- If asked about safety-critical information, always recommend verifying with official documentation.
- Format responses clearly with bullet points or numbered steps when listing procedures.
"""


def retrieve_chunks(
    query: str,
    weaviate_client,
    top_k: int = 8,
    document_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    min_score: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Retrieve the most relevant chunks from Weaviate for a query.
    Returns list of chunk dicts with text, score, and metadata.
    """
    query_vector = embed_texts([query])[0]
    collection = weaviate_client.collections.get(CHUNK_CLASS)

    filters = None
    if document_id:
        filters = Filter.by_property("document_id").equal(document_id)
    elif asset_id:
        filters = Filter.by_property("asset_id").equal(asset_id)

    try:
        response = collection.query.near_vector(
            near_vector=query_vector,
            limit=top_k,
            return_metadata=MetadataQuery(distance=True, score=True),
            filters=filters,
        )

        results = []
        for obj in response.objects:
            score = 1.0 - (obj.metadata.distance or 0.0)
            if score < min_score:
                continue
            results.append({
                "weaviate_id": str(obj.uuid),
                "document_id": obj.properties.get("document_id", ""),
                "asset_id": obj.properties.get("asset_id", ""),
                "chunk_index": obj.properties.get("chunk_index", 0),
                "text": obj.properties.get("text", ""),
                "page_number": obj.properties.get("page_number", 0),
                "source": obj.properties.get("source", ""),
                "score": round(score, 4),
            })

        return results

    except Exception as e:
        logger.error(f"Weaviate retrieval error: {e}")
        return []


def _build_context(chunks: List[Dict[str, Any]], max_tokens: int = 6000) -> tuple[str, List[Dict]]:
    """Assemble context string and sources list from retrieved chunks."""
    context_parts = []
    sources = []
    token_count = 0
    seen_sources: set[tuple] = set()

    for i, chunk in enumerate(chunks):
        chunk_tokens = len(chunk["text"]) // 4
        if token_count + chunk_tokens > max_tokens:
            break

        source_key = (chunk["document_id"], chunk["page_number"])
        if source_key not in seen_sources:
            seen_sources.add(source_key)
            sources.append({
                "document_id": chunk["document_id"],
                "page_number": chunk["page_number"],
                "source": chunk["source"],
                "score": chunk["score"],
            })

        context_parts.append(
            f"[Source {i+1} | Page {chunk['page_number']} | Score: {chunk['score']:.2f}]\n{chunk['text']}"
        )
        token_count += chunk_tokens

    return "\n\n---\n\n".join(context_parts), sources


def _build_messages(
    question: str,
    context: str,
    history: List[Dict[str, str]],
) -> List[Dict[str, str]]:
    """Build the messages array for the LLM API call."""
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]

    # Add conversation history (last 6 messages)
    for msg in history[-6:]:
        messages.append({"role": msg["role"], "content": msg["content"]})

    user_message = f"""Context from uploaded documents:
{context}

Question: {question}

Answer based on the context above. Cite sources when relevant."""

    messages.append({"role": "user", "content": user_message})
    return messages


async def generate_answer_stream(
    question: str,
    weaviate_client,
    history: List[Dict[str, str]] = None,
    document_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    top_k: int = 8,
) -> AsyncGenerator[str, None]:
    """
    Full RAG pipeline with streaming output.
    Yields SSE-formatted chunks.
    """
    history = history or []

    # 1. Retrieve
    chunks = retrieve_chunks(
        query=question,
        weaviate_client=weaviate_client,
        top_k=top_k,
        document_id=document_id,
        asset_id=asset_id,
    )

    if not chunks:
        yield f"data: {json.dumps({'type': 'error', 'content': 'No relevant documents found for your question.'})}\n\n"
        return

    # 2. Assemble context
    context, sources = _build_context(chunks)
    messages = _build_messages(question, context, history)

    # 3. Stream from LLM
    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            async with client.stream(
                "POST",
                f"{settings.OPENAI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.LLM_MODEL,
                    "messages": messages,
                    "stream": True,
                    "temperature": 0.2,
                    "max_tokens": 1500,
                },
            ) as response:
                response.raise_for_status()

                full_content = ""
                async for line in response.aiter_lines():
                    if not line.startswith("data: "):
                        continue
                    data_str = line[6:]
                    if data_str == "[DONE]":
                        break
                    try:
                        data = json.loads(data_str)
                        delta = data["choices"][0]["delta"].get("content", "")
                        if delta:
                            full_content += delta
                            yield f"data: {json.dumps({'type': 'chunk', 'content': delta})}\n\n"
                    except (json.JSONDecodeError, KeyError):
                        continue

                # Yield final metadata
                confidence = round(sum(c["score"] for c in chunks[:3]) / min(3, len(chunks)), 3)
                yield f"data: {json.dumps({'type': 'done', 'sources': sources, 'confidence': confidence})}\n\n"

    except httpx.HTTPStatusError as e:
        logger.error(f"LLM API HTTP error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': f'LLM service error: {e.response.status_code}'})}\n\n"
    except Exception as e:
        logger.error(f"LLM streaming error: {e}")
        yield f"data: {json.dumps({'type': 'error', 'content': 'Failed to generate response. Please try again.'})}\n\n"


async def generate_answer(
    question: str,
    weaviate_client,
    history: List[Dict[str, str]] = None,
    document_id: Optional[str] = None,
    asset_id: Optional[str] = None,
    top_k: int = 8,
) -> Dict[str, Any]:
    """
    Non-streaming RAG: returns full answer, sources, and confidence.
    """
    history = history or []

    chunks = retrieve_chunks(
        query=question,
        weaviate_client=weaviate_client,
        top_k=top_k,
        document_id=document_id,
        asset_id=asset_id,
    )

    if not chunks:
        return {
            "content": "No relevant documents found for your question. Please upload relevant documents first.",
            "sources": [],
            "confidence": 0.0,
            "tokens_used": 0,
        }

    context, sources = _build_context(chunks)
    messages = _build_messages(question, context, history)

    try:
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                f"{settings.OPENAI_BASE_URL}/chat/completions",
                headers={
                    "Authorization": f"Bearer {settings.OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.LLM_MODEL,
                    "messages": messages,
                    "temperature": 0.2,
                    "max_tokens": 1500,
                },
            )
            response.raise_for_status()
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            tokens_used = data.get("usage", {}).get("total_tokens", 0)
            confidence = round(sum(c["score"] for c in chunks[:3]) / min(3, len(chunks)), 3)

            return {
                "content": content,
                "sources": sources,
                "confidence": confidence,
                "tokens_used": tokens_used,
            }

    except Exception as e:
        logger.error(f"LLM error: {e}")
        return {
            "content": "Failed to generate a response. Please check your LLM configuration.",
            "sources": sources,
            "confidence": 0.0,
            "tokens_used": 0,
        }
