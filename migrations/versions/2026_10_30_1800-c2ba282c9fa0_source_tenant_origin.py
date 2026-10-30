"""Add sources.tenant_origin.

Revision ID: c2ba282c9fa0
Revises: 748c4dbd1658
Create Date: 2026-10-30 18:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2ba282c9fa0"
down_revision: str | Sequence[str] | None = "748c4dbd1658"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(
            sa.Column("tenant_origin", sa.String(length=255), nullable=True)
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("sources") as batch_op:
        batch_op.drop_column("tenant_origin")
