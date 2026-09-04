"""b3 b2 durable run state and plan hash

Adds the columns required to make an agent run reconstructable from the database
alone (blocker B3) and to make approval durable and tamper-evident (blocker B2).

HAND-WRITTEN, DELIBERATELY. `alembic revision --autogenerate` was run to discover the
delta, but its output was discarded because it also emitted ~110 `alter_column`
operations against every `id`, `*_id`, `created_at` and `updated_at` column in the
schema. Those are SQLite reflection artifacts: the local scratch database has no
native UUID type and no timezone-aware timestamp, so with `compare_type=True` alembic
sees a difference against every such column. Applied to PostgreSQL they would rewrite
every UUID and timestamp column in all 24 tables - a full-table lock per table - and
`op.drop_constraint(None, ...)` cannot drop an unnamed constraint at all.

Only the intended operations are kept below.

Safety on a populated table: every added column is either nullable or has a
server_default. PostgreSQL 11+ adds a NOT NULL column with a constant default without
rewriting the table, so this does not need the expand/contract procedure.

Revision ID: 28ef4ca1db49
Revises: 75fbe090f4f0
Create Date: 2026-09-04

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '28ef4ca1db49'
down_revision: Union[str, None] = '75fbe090f4f0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

FK_APPROVED_BY = "fk_agent_runs_approved_by_users"


def upgrade() -> None:
    # --- agent_plans: the hash a human approves -----------------------------------
    # sha256 of the canonical plan markdown. Nullable because rows created before this
    # revision have no hash; the application treats a missing hash as "cannot resume".
    op.add_column("agent_plans", sa.Column("plan_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_agent_plans_plan_hash", "agent_plans", ["plan_hash"], unique=False)

    # --- agent_runs: everything needed to rebuild a run with no in-process state ---
    op.add_column(
        "agent_runs",
        sa.Column(
            "execution_mode",
            sa.String(length=50),
            server_default="APPROVAL_REQUIRED",
            nullable=False,
        ),
    )
    # The original HTTP request is gone when a worker picks the run up, so the prompt
    # has to live on the row.
    op.add_column(
        "agent_runs",
        sa.Column("user_prompt", sa.Text(), server_default="", nullable=False),
    )
    # Lets a restarted process reattach to, or reap, the container this run owns.
    op.add_column("agent_runs", sa.Column("sandbox_id", sa.String(length=255), nullable=True))

    # --- agent_runs: durable approval record --------------------------------------
    op.add_column("agent_runs", sa.Column("approved_by", sa.UUID(), nullable=True))
    op.add_column("agent_runs", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("agent_runs", sa.Column("approved_plan_hash", sa.String(length=64), nullable=True))
    # Named explicitly so downgrade can drop it. SET NULL rather than CASCADE: deleting
    # an approver must not delete the run they approved.
    #
    # batch_alter_table, not op.create_foreign_key: SQLite has no
    # "ALTER TABLE ... ADD CONSTRAINT", so a plain create_foreign_key raises
    # NotImplementedError there and the migration could not be exercised outside
    # PostgreSQL. Batch mode is a pass-through on PostgreSQL (a single ALTER, no table
    # rewrite) and a copy-and-move on SQLite, so the same revision runs on both.
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.create_foreign_key(
            FK_APPROVED_BY,
            "users",
            ["approved_by"],
            ["id"],
            ondelete="SET NULL",
        )
    # Supports the stalled-run reaper's "non-terminal and older than N" query.
    op.create_index("idx_runs_status_created", "agent_runs", ["status", "created_at"], unique=False)

    # --- coding_tasks: map an external session id to its task ---------------------
    # A task row is now created per session so agent_runs.task_id (NOT NULL FK) always
    # resolves. Unique so the mapping is one-to-one and idempotent under retry.
    op.add_column("coding_tasks", sa.Column("session_id", sa.UUID(), nullable=True))
    op.create_index("ix_coding_tasks_session_id", "coding_tasks", ["session_id"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_coding_tasks_session_id", table_name="coding_tasks")
    op.drop_column("coding_tasks", "session_id")

    op.drop_index("idx_runs_status_created", table_name="agent_runs")
    with op.batch_alter_table("agent_runs") as batch_op:
        batch_op.drop_constraint(FK_APPROVED_BY, type_="foreignkey")
    op.drop_column("agent_runs", "approved_plan_hash")
    op.drop_column("agent_runs", "approved_at")
    op.drop_column("agent_runs", "approved_by")
    op.drop_column("agent_runs", "sandbox_id")
    op.drop_column("agent_runs", "user_prompt")
    op.drop_column("agent_runs", "execution_mode")

    op.drop_index("ix_agent_plans_plan_hash", table_name="agent_plans")
    op.drop_column("agent_plans", "plan_hash")
