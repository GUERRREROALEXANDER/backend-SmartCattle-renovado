"""Site-wide settings, starting with the cover page's video

One small key/value table for what belongs to the whole deployment rather than
to an account. Its first key, "video_inicio", remembers which file the landing
page plays; it is unrelated to video_uploads and video_analyses.

Created only if missing, so the order in which this and the database
repository reach a database does not matter.

Revision ID: 0023_site_settings
Revises: 0022_anomalies_notifications
Create Date: 2026-11-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0023_site_settings"
down_revision = "0022_anomalies_notifications"
branch_labels = None
depends_on = None


def _exists() -> bool:
    return "site_settings" in sa.inspect(op.get_bind()).get_table_names()


def upgrade() -> None:
    if not _exists():
        op.create_table(
            "site_settings",
            sa.Column("key", sa.String(64), primary_key=True),
            sa.Column("value", sa.Text(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        )


def downgrade() -> None:
    if _exists():
        op.drop_table("site_settings")
