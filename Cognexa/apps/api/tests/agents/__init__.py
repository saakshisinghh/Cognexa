"""
apps/api/tests/agents/__init__.py

Phase 5 test package. Shared fixtures live in conftest.py in this
directory (mocked LLM gateway + tool executor so these tests run
without a live Postgres/Weaviate/Neo4j/Redis/Ollama stack — matching
this repo's existing unit-test convention of testing service logic in
isolation, not requiring live infrastructure).
"""
