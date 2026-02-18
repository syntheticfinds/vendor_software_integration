"""add summaries and trajectory_data to health_scores

Revision ID: f1a2b3c4d5e6
Revises: a1b2c3d4e5f6
Create Date: 2026-02-09 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'f1a2b3c4d5e6'
down_revision: Union[str, None] = 'a1b2c3d4e5f6'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('health_scores', schema=None) as batch_op:
        batch_op.add_column(sa.Column('summaries', sa.JSON, nullable=True))
        batch_op.add_column(sa.Column('trajectory_data', sa.JSON, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table('health_scores', schema=None) as batch_op:
        batch_op.drop_column('trajectory_data')
        batch_op.drop_column('summaries')
