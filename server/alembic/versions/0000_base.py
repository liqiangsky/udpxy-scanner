"""
Base migration - empty placeholder
"""
from alembic import op
import sqlalchemy as sa


revision = 'base'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
