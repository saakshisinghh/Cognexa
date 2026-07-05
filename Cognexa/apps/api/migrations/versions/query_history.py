"""
migrations/versions/query_history.py

FIX: query_history table was never created by any migration.

apps/api/services/copilot_v2.py::_persist_query() INSERTs into
query_history, and submit_feedback() UPDATEs it — but the only existing
migration that touches this table is 002_phase4
(conversation_sessions.py), and that migration only runs
`op.add_column("query_history", ...)` for the Phase 4 columns
(session_id, confidence_level, confidence_score, conflict_detected,
conflict_count, conflicts_json, retrieval_stats_json, feedback,
elapsed_ms). It assumes the base table already exists from an earlier
Phase 1 migration — but no such migration exists anywhere in this repo,
and there is no QueryHistory ORM model either (see apps/api/models/__init__.py).

This is why requests hit:
    relation "query_history" does not exist

This migration creates the base table with exactly the columns that
_persist_query()'s INSERT statement writes to before the Phase 4 columns
are added on top of it:
    id, user_id, query_text, response_text, retrieved_chunks, created_at

Chain: p3_001_create_incidents -> 003_create_query_history -> 002_phase4
(conversation_sessions.py's down_revision must be updated from
"p3_001_create_incidents" to "003_create_query_history" — see the note
at the bottom of this file / the accompanying one-line diff.)
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "003_create_query_history"
down_revision = "p3_001_create_incidents"
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        "query_history",

        sa.Column(
            "id",
            sa.String(),
            primary_key=True,
        ),

        sa.Column(
            "user_id",
            sa.String(),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),

        sa.Column(
            "query_text",
            sa.Text(),
            nullable=False,
        ),

        sa.Column(
            "response_text",
            sa.Text(),
            nullable=True,
        ),

        sa.Column(
            "retrieved_chunks",
            postgresql.JSONB(),
            nullable=False,
            server_default="[]",
        ),

        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),
    )

    op.create_index(
        "ix_query_history_user_created",
        "query_history",
        ["user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index("ix_query_history_user_created", table_name="query_history")
    op.drop_table("query_history")


# ---------------------------------------------------------------------------
# REQUIRED ONE-LINE EDIT in migrations/versions/conversation_sessions.py:
#
#   down_revision = "p3_001_create_incidents"
#
# must become:
#
#   down_revision = "003_create_query_history"
#
# so that Alembic runs this migration (which creates query_history) BEFORE
# conversation_sessions.py's `op.add_column("query_history", ...)` calls,
# which otherwise still fail with "relation query_history does not exist"
# even after adding this file.
# ---------------------------------------------------------------------------