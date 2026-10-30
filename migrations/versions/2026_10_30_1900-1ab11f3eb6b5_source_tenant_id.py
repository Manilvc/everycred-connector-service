"""Replace sources.tenant_origin with sources.tenant_id.

The DCS now takes the tenant from an X-Tenant-ID header on its internal
holder API, so a source names its tenant by id instead of by frontend
origin.

Revision ID: 1ab11f3eb6b5
Revises: c2ba282c9fa0
Create Date: 2026-10-30 19:00:00.000000

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "1ab11f3eb6b5"
down_revision: str | Sequence[str] | None = "c2ba282c9fa0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(
            sa.Column("tenant_id", sa.String(length=100), nullable=True)
        )
        batch_op.drop_column("tenant_origin")


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("sources") as batch_op:
        batch_op.add_column(
            sa.Column("tenant_origin", sa.String(length=255), nullable=True)
        )
        batch_op.drop_column("tenant_id")
