"""automatically add votes table

Revision ID: 914269a29711
Revises: 9a0171feae78
Create Date: 2023-05-10 23:42:13.918318

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '914269a29711'
down_revision = '9a0171feae78'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    pass
    # ### end Alembic commands ###


def downgrade() -> None:
    # ### commands auto generated by Alembic - please adjust! ###
    op.drop_table('votes') 
    pass
    # ### end Alembic commands ###