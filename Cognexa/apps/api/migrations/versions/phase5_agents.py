"""
migrations/versions/phase5_agents.py

Phase 5 — Agentic AI Platform.

Creates the three new tables backing the Agent API (agent_definitions,
agent_workflows, agent_executions, agent_execution_steps) and extends
the existing native Postgres `auditaction` enum with the four new
Phase 5 audit action values used by services/agent_executor.py and
services/agent_registry.py.

Chain: 002_phase4 -> phase5_agents
"""
from alembic import op
import sqlalchemy as sa

revision = "phase5_agents"
down_revision = "002_phase4"
branch_labels = None
depends_on = None


_NEW_AUDIT_ACTIONS = ["agent_execute", "agent_cancel", "agent_enable", "agent_disable", "workflow_execute"]


def upgrade() -> None:
    # ── extend the AuditAction enum (native Postgres type) ──────────────
    for value in _NEW_AUDIT_ACTIONS:
        op.execute(f"ALTER TYPE auditaction ADD VALUE IF NOT EXISTS '{value}'")

    # ── agent_definitions ────────────────────────────────────────────────
    op.create_table(
        "agent_definitions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_key", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("version", sa.String(20), nullable=False, server_default="1.0.0"),
        sa.Column("capabilities", sa.JSON(), server_default="[]"),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("health_status", sa.String(20), server_default="unknown"),
        sa.Column("last_health_check_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_agent_definitions_agent_key", "agent_definitions", ["agent_key"], unique=True)

    # ── agent_workflows ──────────────────────────────────────────────────
    op.create_table(
        "agent_workflows",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("mode", sa.String(20), nullable=False, server_default="sequential"),
        sa.Column("agent_keys", sa.JSON(), server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("shared_context", sa.JSON(), server_default="{}"),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("conflicts", sa.JSON(), server_default="[]"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_agent_workflows_user_id", "agent_workflows", ["user_id"])
    op.create_index("ix_agent_workflows_status", "agent_workflows", ["status"])
    op.create_index("ix_agent_workflows_created_at", "agent_workflows", ["created_at"])

    # ── agent_executions ─────────────────────────────────────────────────
    op.create_table(
        "agent_executions",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("agent_key", sa.String(64), nullable=False),
        sa.Column("workflow_id", sa.String(), sa.ForeignKey("agent_workflows.id", ondelete="SET NULL"), nullable=True),
        sa.Column("user_id", sa.String(), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("goal", sa.Text(), nullable=False),
        sa.Column("context", sa.JSON(), server_default="{}"),
        sa.Column("mode", sa.String(20), nullable=False, server_default="single"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("plan", sa.JSON(), nullable=True),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("structured_output", sa.JSON(), nullable=True),
        sa.Column("confidence", sa.JSON(), nullable=True),
        sa.Column("sources", sa.JSON(), server_default="[]"),
        sa.Column("errors", sa.JSON(), server_default="[]"),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("completed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("celery_task_id", sa.String(), nullable=True),
        sa.Column("cancel_requested", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_agent_executions_agent_key", "agent_executions", ["agent_key"])
    op.create_index("ix_agent_executions_workflow_id", "agent_executions", ["workflow_id"])
    op.create_index("ix_agent_executions_user_id", "agent_executions", ["user_id"])
    op.create_index("ix_agent_executions_status", "agent_executions", ["status"])
    op.create_index("ix_agent_executions_created_at", "agent_executions", ["created_at"])
    op.create_index("ix_agent_executions_celery_task_id", "agent_executions", ["celery_task_id"])
    op.create_index("ix_agent_executions_agent_created", "agent_executions", ["agent_key", "created_at"])

    # ── agent_execution_steps ────────────────────────────────────────────
    op.create_table(
        "agent_execution_steps",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("execution_id", sa.String(), sa.ForeignKey("agent_executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("step_name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Float(), nullable=True),
        sa.Column("timestamp", sa.TIMESTAMP(timezone=True), server_default=sa.text("NOW()")),
    )
    op.create_index("ix_agent_execution_steps_execution_id", "agent_execution_steps", ["execution_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_execution_steps_execution_id", table_name="agent_execution_steps")
    op.drop_table("agent_execution_steps")

    op.drop_index("ix_agent_executions_agent_created", table_name="agent_executions")
    op.drop_index("ix_agent_executions_celery_task_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_created_at", table_name="agent_executions")
    op.drop_index("ix_agent_executions_status", table_name="agent_executions")
    op.drop_index("ix_agent_executions_user_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_workflow_id", table_name="agent_executions")
    op.drop_index("ix_agent_executions_agent_key", table_name="agent_executions")
    op.drop_table("agent_executions")

    op.drop_index("ix_agent_workflows_created_at", table_name="agent_workflows")
    op.drop_index("ix_agent_workflows_status", table_name="agent_workflows")
    op.drop_index("ix_agent_workflows_user_id", table_name="agent_workflows")
    op.drop_table("agent_workflows")

    op.drop_index("ix_agent_definitions_agent_key", table_name="agent_definitions")
    op.drop_table("agent_definitions")

    # Note: Postgres does not support removing enum values in a downgrade
    # without recreating the type; intentionally left as a no-op here,
    # matching this repo's existing precedent of additive-only enum changes.
