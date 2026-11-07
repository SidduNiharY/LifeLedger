"""readonly_role

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-07 18:00:00.000000

"""

from collections.abc import Sequence

from alembic import op

from app.mcp.role import readonly_role_statements

# revision identifiers, used by Alembic.
revision: str = "0005"
down_revision: str | Sequence[str] | None = "0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Upgrade schema."""
    for stmt in readonly_role_statements():
        op.execute(stmt)


def downgrade() -> None:
    """Downgrade schema."""
    op.execute(
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public REVOKE SELECT ON TABLES FROM lifeledger_ro;"
    )
    op.execute("REVOKE SELECT ON ALL TABLES IN SCHEMA public FROM lifeledger_ro;")
    op.execute("REVOKE USAGE ON SCHEMA public FROM lifeledger_ro;")
    op.execute("DROP ROLE IF EXISTS lifeledger_ro;")
