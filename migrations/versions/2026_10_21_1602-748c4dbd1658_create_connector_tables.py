"""Create connector tables.

Revision ID: 748c4dbd1658
Revises:
Create Date: 2026-10-21 16:02:38.222480

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision: str = "748c4dbd1658"
down_revision: str | Sequence[str] | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "clients",
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column(
            "kind",
            sa.Enum(
                "verifier",
                "holder_service",
                name="clientkind",
                native_enum=False,
                length=30,
            ),
            nullable=False,
        ),
        sa.Column("key_prefix", sa.String(length=12), nullable=False),
        sa.Column("key_hash", sa.String(length=64), nullable=False),
        sa.Column("revoked_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_clients")),
    )
    op.create_index(
        op.f("ix_clients_key_prefix"), "clients", ["key_prefix"], unique=True
    )
    op.create_table(
        "holder_notifications",
        sa.Column("event", sa.String(length=50), nullable=False),
        sa.Column("encrypted_payload", sa.Text(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "pending",
                "delivered",
                "failed",
                name="notificationstatus",
                native_enum=False,
                length=20,
            ),
            nullable=False,
        ),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), nullable=False),
        sa.Column("last_error", sa.String(length=255), nullable=True),
        sa.Column("delivered_at", sa.DateTime(), nullable=True),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holder_notifications")),
    )
    op.create_index(
        op.f("ix_holder_notifications_next_attempt_at"),
        "holder_notifications",
        ["next_attempt_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_holder_notifications_status"),
        "holder_notifications",
        ["status"],
        unique=False,
    )
    op.create_table(
        "sources",
        sa.Column("code", sa.String(length=50), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=False),
        sa.Column("normalizer", sa.String(length=50), nullable=False),
        sa.Column("encrypted_api_key", sa.Text(), nullable=False),
        sa.Column("encrypted_webhook_secret", sa.Text(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_sources")),
    )
    op.create_index(op.f("ix_sources_code"), "sources", ["code"], unique=True)
    op.create_table(
        "credential_routes",
        sa.Column("credential_id", sa.String(length=128), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("holder_key", sa.String(length=64), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("last_event_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_credential_routes_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_credential_routes")),
    )
    op.create_index(
        op.f("ix_credential_routes_credential_id"),
        "credential_routes",
        ["credential_id"],
        unique=True,
    )
    op.create_index(
        op.f("ix_credential_routes_holder_key"),
        "credential_routes",
        ["holder_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_credential_routes_source_id"),
        "credential_routes",
        ["source_id"],
        unique=False,
    )
    op.create_table(
        "holder_links",
        sa.Column("holder_key", sa.String(length=64), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_holder_links_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_holder_links")),
        sa.UniqueConstraint(
            "holder_key", "source_id", name=op.f("uq_holder_links_holder_key")
        ),
    )
    op.create_index(
        op.f("ix_holder_links_holder_key"),
        "holder_links",
        ["holder_key"],
        unique=False,
    )
    op.create_table(
        "source_events",
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("delivery_id", sa.String(length=128), nullable=False),
        sa.Column("event", sa.String(length=50), nullable=False),
        sa.Column("received_at", sa.DateTime(), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["source_id"],
            ["sources.id"],
            name=op.f("fk_source_events_source_id_sources"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_source_events")),
        sa.UniqueConstraint(
            "source_id", "delivery_id", name=op.f("uq_source_events_source_id")
        ),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_table("source_events")
    op.drop_index(
        op.f("ix_holder_links_holder_key"), table_name="holder_links"
    )
    op.drop_table("holder_links")
    op.drop_index(
        op.f("ix_credential_routes_source_id"), table_name="credential_routes"
    )
    op.drop_index(
        op.f("ix_credential_routes_holder_key"), table_name="credential_routes"
    )
    op.drop_index(
        op.f("ix_credential_routes_credential_id"),
        table_name="credential_routes",
    )
    op.drop_table("credential_routes")
    op.drop_index(op.f("ix_sources_code"), table_name="sources")
    op.drop_table("sources")
    op.drop_index(
        op.f("ix_holder_notifications_status"),
        table_name="holder_notifications",
    )
    op.drop_index(
        op.f("ix_holder_notifications_next_attempt_at"),
        table_name="holder_notifications",
    )
    op.drop_table("holder_notifications")
    op.drop_index(op.f("ix_clients_key_prefix"), table_name="clients")
    op.drop_table("clients")
