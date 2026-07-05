"""create incidents table (Phase 3 - Knowledge Graph Intelligence)



Purpose
-------
Adds the `incidents` table — the Postgres system-of-record for incidents,
synced into Neo4j as :Incident nodes by the Phase 3 graph sync pipeline.

IMPORTANT: Replace `down_revision` below with the actual latest Phase 2
revision id before running `alembic upgrade head`. This file does NOT
touch any existing table.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = "p3_001_create_incidents"
down_revision = "<SET_TO_LATEST_PHASE2_REVISION_ID>"
branch_labels = None
depends_on = None

incident_severity = postgresql.ENUM(
    "low", "medium", "high", "critical", name="incidentseverity", create_type=False
)
incident_status = postgresql.ENUM(
    "open", "investigating", "resolved", "closed", name="incidentstatus", create_type=False
)


def upgrade() -> None:
    incident_severity.create(op.get_bind(), checkfirst=True)
    incident_status.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "incidents",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column(
            "asset_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("assets.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "document_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("documents.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "reported_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("severity", incident_severity, nullable=False, server_default="medium"),
        sa.Column("status", incident_status, nullable=False, server_default="open"),
        sa.Column("failure_mode_code", sa.String(length=20), nullable=True),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("graph_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("graph_sync_status", sa.String(length=20), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
            nullable=False,
        ),
    )

    op.create_index(
        "ix_incidents_asset_id_occurred_at",
        "incidents",
        ["asset_id", "occurred_at"],
    )
    op.create_index("ix_incidents_status", "incidents", ["status"])
    op.create_index("ix_incidents_graph_sync_status", "incidents", ["graph_sync_status"])


def downgrade() -> None:
    op.drop_index("ix_incidents_graph_sync_status", table_name="incidents")
    op.drop_index("ix_incidents_status", table_name="incidents")
    op.drop_index("ix_incidents_asset_id_occurred_at", table_name="incidents")
    op.drop_table("incidents")
    incident_status.drop(op.get_bind(), checkfirst=True)
    incident_severity.drop(op.get_bind(), checkfirst=True)
