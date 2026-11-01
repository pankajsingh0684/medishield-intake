"""Add reference dates, typed history fields, and policy exclusions.

Revision ID: 5b20261101
Revises: 762e1c97c741
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "5b20261101"
down_revision: str | None = "762e1c97c741"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "cases",
        sa.Column(
            "received_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    op.add_column("claim_history", sa.Column("kind", sa.Text(), nullable=True))
    op.execute("UPDATE claim_history SET kind = 'PRIOR_CLAIM' WHERE kind IS NULL")
    op.alter_column("claim_history", "kind", nullable=False)
    op.create_check_constraint(
        "ck_claim_history_kind",
        "claim_history",
        "kind IN ('PRIOR_CLAIM','EPISODE_CLAIM','PRIOR_STAY')",
    )
    op.add_column("claim_history", sa.Column("claim_number", sa.Text(), nullable=True))
    op.add_column("claim_history", sa.Column("admit_date", sa.Date(), nullable=True))
    op.add_column("claim_history", sa.Column("discharge_date", sa.Date(), nullable=True))

    op.create_table(
        "policy_exclusions",
        sa.Column("exclusion_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("policy_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("range_start", sa.Text(), nullable=False),
        sa.Column("range_end", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=True),
        sa.Column("basis", sa.Text(), nullable=True),
        sa.Column("page", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["policy_id"], ["policies.policy_id"]),
        sa.PrimaryKeyConstraint("exclusion_id"),
    )


def downgrade() -> None:
    op.drop_table("policy_exclusions")
    op.drop_column("claim_history", "discharge_date")
    op.drop_column("claim_history", "admit_date")
    op.drop_column("claim_history", "claim_number")
    op.drop_constraint("ck_claim_history_kind", "claim_history", type_="check")
    op.drop_column("claim_history", "kind")
    op.drop_column("cases", "received_at")
