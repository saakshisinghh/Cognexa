from alembic import op
import sqlalchemy as sa

revision = "002_phase4"
down_revision = "003_create_query_history"
branch_labels = None
depends_on = None


def upgrade() -> None:

    op.create_table(
        "conversation_sessions",

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
            "plant_id",
            sa.String(),
            nullable=True,
        ),

        sa.Column(
            "pinned_asset_id",
            sa.String(),
            sa.ForeignKey("assets.id", ondelete="SET NULL"),
            nullable=True,
        ),

        sa.Column(
            "pinned_asset_tag",
            sa.String(100),
            nullable=True,
        ),

        sa.Column(
            "title",
            sa.String(200),
            nullable=True,
        ),

        sa.Column(
            "recent_messages_json",
            sa.Text(),
            nullable=False,
            server_default="[]",
        ),

        sa.Column(
            "message_count",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),

        sa.Column(
            "last_active_at",
            sa.TIMESTAMP(timezone=True),
            nullable=True,
            server_default=sa.text("NOW()"),
        ),

        sa.Column(
            "created_at",
            sa.TIMESTAMP(timezone=True),
            nullable=False,
            server_default=sa.text("NOW()"),
        ),

        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    op.create_index(
        "ix_conversation_sessions_user_active",
        "conversation_sessions",
        ["user_id", "is_archived", "last_active_at"],
    )

    op.add_column(
        "query_history",
        sa.Column(
            "session_id",
            sa.String(),
            sa.ForeignKey(
                "conversation_sessions.id",
                ondelete="SET NULL",
            ),
            nullable=True,
        ),
    )

    op.add_column(
        "query_history",
        sa.Column(
            "confidence_level",
            sa.String(10),
            nullable=True,
        ),
    )

    op.add_column(
        "query_history",
        sa.Column(
            "confidence_score",
            sa.Numeric(6, 4),
            nullable=True,
        ),
    )

    op.add_column(
        "query_history",
        sa.Column(
            "conflict_detected",
            sa.Boolean(),
            nullable=True,
        ),
    )

    op.add_column(
        "query_history",
        sa.Column(
            "conflict_count",
            sa.Integer(),
            nullable=True,
        ),
    )

    op.add_column(
        "query_history",
        sa.Column(
            "conflicts_json",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "query_history",
        sa.Column(
            "retrieval_stats_json",
            sa.Text(),
            nullable=True,
        ),
    )

    op.add_column(
        "query_history",
        sa.Column(
            "feedback",
            sa.String(10),
            nullable=True,
        ),
    )

    op.add_column(
        "query_history",
        sa.Column(
            "elapsed_ms",
            sa.Integer(),
            nullable=True,
        ),
    )


def downgrade() -> None:

    for col in [
        "elapsed_ms",
        "feedback",
        "retrieval_stats_json",
        "conflicts_json",
        "conflict_count",
        "conflict_detected",
        "confidence_score",
        "confidence_level",
        "session_id",
    ]:
        op.drop_column("query_history", col)

    op.drop_index(
        "ix_conversation_sessions_user_active",
        table_name="conversation_sessions",
    )

    op.drop_table("conversation_sessions")