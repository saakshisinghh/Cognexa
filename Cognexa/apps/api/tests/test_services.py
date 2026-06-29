"""
Unit tests for INDUS MIND Phase 1 services.
"""
import pytest
from apps.api.services.chunker import split_text, _estimate_tokens, _recursive_split


# ─── Chunker Tests ────────────────────────────────────────────────────────────

class TestChunker:
    def test_empty_text_returns_no_chunks(self):
        chunks = split_text("", document_id="test-id")
        assert chunks == []

    def test_short_text_is_single_chunk(self):
        text = "This is a short paragraph that fits in one chunk."
        chunks = split_text(text, document_id="test-id", chunk_size=512, chunk_overlap=64)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].chunk_index == 0

    def test_long_text_splits_into_multiple_chunks(self):
        # Create a long text of ~2000 tokens
        paragraph = "This is a paragraph about industrial equipment maintenance. " * 10
        text = "\n\n".join([paragraph] * 5)
        chunks = split_text(text, document_id="test-id", chunk_size=100, chunk_overlap=20)
        assert len(chunks) > 1

    def test_chunk_indices_are_sequential(self):
        paragraph = "Sentence number one. Sentence number two. Sentence number three. " * 20
        chunks = split_text(paragraph, document_id="test-id", chunk_size=50, chunk_overlap=10)
        for i, chunk in enumerate(chunks):
            assert chunk.chunk_index == i

    def test_chunk_has_metadata(self):
        text = "A test paragraph with some content about pumps."
        chunks = split_text(text, document_id="doc-123", source="test.pdf")
        assert len(chunks) > 0
        assert chunks[0].metadata["document_id"] == "doc-123"
        assert chunks[0].metadata["source"] == "test.pdf"

    def test_token_estimate_is_positive(self):
        assert _estimate_tokens("hello world") > 0
        assert _estimate_tokens("") == 1  # max(1, 0//4)

    def test_page_detection_from_form_feed(self):
        text = "Page one content here.\fPage two content here.\fPage three content here."
        chunks = split_text(text, document_id="test-id")
        # All chunks should have page numbers
        for chunk in chunks:
            assert chunk.page_number is not None
            assert chunk.page_number >= 1


# ─── Extractor Tests ──────────────────────────────────────────────────────────

class TestExtractor:
    def test_empty_text_returns_no_entities(self):
        from apps.api.services.extractor import extract_entities
        result = extract_entities("")
        assert result == []

    def test_regex_fallback_detects_industrial_terms(self):
        from apps.api.services.extractor import _extract_with_regex
        text = "The pump operates at 1450 RPM with a discharge pressure of 45 PSI."
        entities = _extract_with_regex(text)
        # Should find RPM and PSI
        entity_texts = [e["text"] for e in entities]
        assert any("RPM" in t or "PSI" in t for t in entity_texts)

    def test_iso_standard_detection(self):
        from apps.api.services.extractor import _extract_with_regex
        text = "The equipment was inspected per ISO 14224:2016 guidelines."
        entities = _extract_with_regex(text)
        entity_texts = [e["text"] for e in entities]
        assert any("ISO" in t for t in entity_texts)


# ─── Auth Tests ───────────────────────────────────────────────────────────────

class TestAuth:
    def test_password_hash_and_verify(self):
        from apps.api.routers.auth import hash_password, verify_password
        password = "secure_password_123"
        hashed = hash_password(password)
        assert hashed != password
        assert verify_password(password, hashed)
        assert not verify_password("wrong_password", hashed)

    def test_access_token_creation_and_decode(self):
        from apps.api.routers.auth import create_access_token, decode_access_token
        token = create_access_token("user-123", "engineer")
        payload = decode_access_token(token)
        assert payload["sub"] == "user-123"
        assert payload["role"] == "engineer"
        assert payload["type"] == "access"

    def test_invalid_token_raises_http_exception(self):
        from fastapi import HTTPException
        from apps.api.routers.auth import decode_access_token
        with pytest.raises(HTTPException) as exc:
            decode_access_token("not.a.valid.token")
        assert exc.value.status_code == 401


# ─── Utils Tests ──────────────────────────────────────────────────────────────

class TestConfig:
    def test_settings_load(self):
        from apps.api.config import settings
        assert settings.APP_NAME == "INDUS MIND API"
        assert settings.ALGORITHM == "HS256"
        assert settings.CHUNK_SIZE > 0
        assert settings.EMBEDDING_DIMENSION > 0
