"""allow shared webhook_secret

Revision ID: bd03a4d845bd
Revises: 647117031c1e
Create Date: 2026-02-14 15:46:15.700294

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'bd03a4d845bd'
down_revision: Union[str, None] = '647117031c1e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table('jira_webhooks', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_jira_webhooks_webhook_secret'))
        batch_op.create_index(op.f('ix_jira_webhooks_webhook_secret'), ['webhook_secret'], unique=False)


def downgrade() -> None:
    with op.batch_alter_table('jira_webhooks', schema=None) as batch_op:
        batch_op.drop_index(op.f('ix_jira_webhooks_webhook_secret'))
        batch_op.create_index(op.f('ix_jira_webhooks_webhook_secret'), ['webhook_secret'], unique=True)
