"""tests/unit/test_context_assembler.py"""

from uuid import uuid4
import pytest
from apps.api.schemas.retrieval import RetrievedChunk
from apps.api.services.context_assembler import assemble_context, _MAX_CONTEXT_CHARS


def _chunk(content: str, title: str = "Doc", page: int = 1, trust: float = 1.0) -> RetrievedChunk:
    c = RetrievedChunk(
        chunk_id=uuid4(), document_id=uuid4(), document_title=title,
        content=content, page_number=page, trust_score=trust,
    )
    c.source_ranks["bm25"] = 1
    return c


class TestContextAssembler:

    def test_empty_chunks_returns_empty_string_and_empty_citations(self):
        ctx, cits = assemble_context([])
        assert ctx == ""
        assert cits == []

    def test_single_chunk_produces_one_source_tag(self):
        ctx, cits = assemble_context([_chunk("pump seal procedure")])
        assert "[SOURCE:1]" in ctx
        assert len(cits) == 1

    def test_multiple_chunks_produce_sequential_source_tags(self):
        chunks = [_chunk(f"content {i}") for i in range(3)]
        ctx, cits = assemble_context(chunks)
        assert "[SOURCE:1]" in ctx
        assert "[SOURCE:2]" in ctx
        assert "[SOURCE:3]" in ctx
        assert len(cits) == 3

    def test_citation_excerpt_capped_at_300_chars(self):
        long_content = "x" * 500
        _, cits = assemble_context([_chunk(long_content)])
        assert len(cits[0].excerpt) <= 300

    def test_citation_contains_document_title(self):
        _, cits = assemble_context([_chunk("content", title="Pump Manual 2023")])
        assert cits[0].document_title == "Pump Manual 2023"

    def test_citation_contains_page_number(self):
        _, cits = assemble_context([_chunk("content", page=14)])
        assert cits[0].page_number == 14

    def test_total_context_does_not_exceed_limit(self):
        big_chunk = "x" * 15_000
        chunks = [_chunk(big_chunk) for _ in range(5)]
        ctx, _ = assemble_context(chunks)
        assert len(ctx) <= _MAX_CONTEXT_CHARS + 500  # +500 for marker overhead

    def test_sources_field_reflects_retrieval_paths(self):
        c = _chunk("content")
        c.source_ranks["vector"] = 2
        c.source_ranks["graph"] = 3
        _, cits = assemble_context([c])
        assert "bm25" in cits[0].sources

    def test_trust_score_included_in_citation(self):
        _, cits = assemble_context([_chunk("content", trust=0.75)])
        assert cits[0].trust_score == pytest.approx(0.75)

    def test_context_string_contains_document_title(self):
        ctx, _ = assemble_context([_chunk("seal info", title="Maintenance SOP")])
        assert "Maintenance SOP" in ctx

    def test_chunks_processed_in_order(self):
        c1 = _chunk("alpha content", title="First")
        c2 = _chunk("beta content", title="Second")
        ctx, cits = assemble_context([c1, c2])
        assert ctx.index("alpha") < ctx.index("beta")
        assert cits[0].document_title == "First"
        assert cits[1].document_title == "Second"
