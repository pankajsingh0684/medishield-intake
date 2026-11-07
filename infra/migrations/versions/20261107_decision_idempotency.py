"""Ensure one decision per case and pipeline run.

Revision ID: 20261107_decision_idempotency
Revises: 20261107_plan_code
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261107_decision_idempotency"
down_revision: str | None = "20261107_plan_code"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_decisions_case_pipeline_run",
        "decisions",
        ["case_id", "pipeline_run"],
    )


def downgrade() -> None:
    op.drop_constraint("uq_decisions_case_pipeline_run", "decisions", type_="unique")
