"""drop pagerduty_service column

Revision ID: a1b2c3d4e5f6
Revises: bd03a4d845bd
Create Date: 2026-02-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = 'bd03a4d845bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('software_registrations', schema=None) as batch_op:
        batch_op.drop_column('pagerduty_service')


def downgrade() -> None:
    with op.batch_alter_table('software_registrations', schema=None) as batch_op:
        batch_op.add_column(sa.Column('pagerduty_service', sa.String(255), nullable=True))
