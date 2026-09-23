''''
Alembic 迁移脚本模板
''''
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = __revision__ = '<<revision>>'
down_revision = __down_revision__ = '<<down_revision>>'
branch_labels = __branch_labels__ = '<<branch_labels>>'
depends_on = __depends_on__ = '<<depends_on>>'


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
