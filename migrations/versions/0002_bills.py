"""bills

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-07 13:21:22.396406

"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "0002"
down_revision: str | Sequence[str] | None = "0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "bills",
        sa.Column("id", sa.BigInteger(), sa.Identity(always=False), nullable=False),
        sa.Column(
            "kind",
            sa.Enum("bill", "renewal", name="billkind", native_enum=False, length=32),
            nullable=False,
        ),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column(
            "payee_keywords",
            postgresql.ARRAY(sa.Text()),
            server_default=sa.text("'{}'::text[]"),
            nullable=False,
        ),
        sa.Column("amount_due", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("due_on", sa.Date(), nullable=False),
        sa.Column(
            "recurrence",
            sa.Enum(
                "none",
                "monthly",
                "yearly",
                name="recurrence",
                native_enum=False,
                length=32,
            ),
            server_default="none",
            nullable=False,
        ),
        sa.Column("anchor_day", sa.SmallInteger(), nullable=True),
        sa.Column(
            "status",
            sa.Enum(
                "open",
                "paid",
                "expired",
                "cancelled",
                name="billstatus",
                native_enum=False,
                length=32,
            ),
            server_default="open",
            nullable=False,
        ),
        sa.Column(
            "source",
            sa.Enum(
                "manual",
                "pdf",
                "email",
                "calendar",
                name="billsource",
                native_enum=False,
                length=32,
            ),
            nullable=False,
        ),
        sa.Column("external_ref", sa.Text(), nullable=True),
        sa.Column("inbound_message_id", sa.BigInteger(), nullable=True),
        sa.Column("workflow_id", sa.Text(), nullable=True),
        sa.Column("paid_transaction_id", sa.BigInteger(), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["inbound_message_id"],
            ["inbound_messages.id"],
        ),
        sa.ForeignKeyConstraint(
            ["paid_transaction_id"],
            ["transactions.id"],
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("paid_transaction_id"),
    )
    op.create_index(op.f("ix_bills_due_on"), "bills", ["due_on"], unique=False)
    op.create_index(op.f("ix_bills_status"), "bills", ["status"], unique=False)
    op.create_index(
        "uq_bills_source_external_ref",
        "bills",
        ["source", "external_ref"],
        unique=True,
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "uq_bills_source_external_ref",
        table_name="bills",
        postgresql_where=sa.text("external_ref IS NOT NULL"),
    )
    op.drop_index(op.f("ix_bills_status"), table_name="bills")
    op.drop_index(op.f("ix_bills_due_on"), table_name="bills")
    op.drop_table("bills")
