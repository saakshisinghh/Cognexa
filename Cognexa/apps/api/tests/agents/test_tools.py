"""
apps/api/tests/agents/test_tools.py

Tool tests: the ALL_TOOLS registry, permission gating on sensitive
tools, and unknown-tool handling in execute_tool().
"""
from __future__ import annotations

import pytest

from apps.api.agents.tools import ALL_TOOLS, list_tools, get_tool, execute_tool


class TestToolRegistry:
    def test_all_twelve_tools_registered(self):
        expected = {
            "semantic_search", "knowledge_graph_query", "document_reader", "asset_lookup",
            "incident_search", "compliance_search", "maintenance_history", "rag_retrieval",
            "hybrid_search", "prompt_library", "conversation_history", "audit_lookup",
        }
        assert expected == set(ALL_TOOLS.keys())

    def test_list_tools_excludes_sensitive_when_requested(self):
        all_tools = list_tools(include_sensitive=True)
        safe_tools = list_tools(include_sensitive=False)
        assert len(safe_tools) < len(all_tools)
        assert all(not t["sensitive"] for t in safe_tools)

    def test_audit_lookup_is_marked_sensitive(self):
        assert get_tool("audit_lookup").sensitive is True

    def test_get_tool_unknown_returns_none(self):
        assert get_tool("not_a_real_tool") is None


class _FakeRole:
    def __init__(self, value):
        self.value = value


class _FakeUser:
    def __init__(self, role_value):
        self.role = _FakeRole(role_value)


@pytest.mark.asyncio
class TestExecuteToolPermissions:
    async def test_unknown_tool_returns_error_not_exception(self, fake_db):
        result = await execute_tool("not_a_real_tool", {}, db=fake_db)
        assert result.ok is False
        assert "Unknown tool" in result.error

    async def test_sensitive_tool_blocked_for_viewer_role(self, fake_db, monkeypatch):
        # Patch the underlying audit_lookup DB query chain isn't needed —
        # permission check short-circuits before the tool body runs.
        user = _FakeUser("viewer")
        result = await execute_tool("audit_lookup", {}, db=fake_db, current_user=user)
        assert result.ok is False
        assert "Insufficient permissions" in result.error

    async def test_sensitive_tool_allowed_for_admin_role_reaches_tool_body(self, fake_db, monkeypatch):
        import apps.api.agents.tools as tools_mod

        class FakeQuery:
            def filter(self, *a, **k): return self
            def order_by(self, *a, **k): return self
            def limit(self, *a, **k): return self
            def all(self): return []

        class FakeDBWithQuery:
            def query(self, *a, **k): return FakeQuery()

        user = _FakeUser("admin")
        result = await execute_tool("audit_lookup", {}, db=FakeDBWithQuery(), current_user=user)
        # Permission check passed; tool body executed against the fake DB.
        assert result.ok is True
        assert result.data == []

    async def test_tool_exception_is_captured_not_raised(self, fake_db, monkeypatch):
        import apps.api.agents.tools as tools_mod

        async def broken(input, *, db, **kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(tools_mod.ALL_TOOLS["asset_lookup"], "run", broken)
        result = await execute_tool("asset_lookup", {}, db=fake_db)
        assert result.ok is False
        assert "boom" in result.error
