"""Cascade policy exclusions when their owning policy is deleted.

Revision ID: 20261125_policy_cascade
Revises: 20261107_decision_idempotency
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261125_policy_cascade"
down_revision: str | None = "20261107_decision_idempotency"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_constraint(
        "policy_exclusions_policy_id_fkey",
        "policy_exclusions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "policy_exclusions_policy_id_fkey",
        "policy_exclusions",
        "policies",
        ["policy_id"],
        ["policy_id"],
        ondelete="CASCADE",
    )


def downgrade() -> None:
    op.drop_constraint(
        "policy_exclusions_policy_id_fkey",
        "policy_exclusions",
        type_="foreignkey",
    )
    op.create_foreign_key(
        "policy_exclusions_policy_id_fkey",
        "policy_exclusions",
        "policies",
        ["policy_id"],
        ["policy_id"],
    )
