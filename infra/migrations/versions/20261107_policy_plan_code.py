"""Add policy plan codes for member-to-policy resolution.

Revision ID: 20261107_plan_code
Revises: 5b20261101
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20261107_plan_code"
down_revision: str | None = "5b20261101"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("policies", sa.Column("plan_code", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("policies", "plan_code")
