"""add software_id to jira_webhooks

Revision ID: 647117031c1e
Revises: 506e26659117
Create Date: 2026-02-14 15:24:16.698710

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '647117031c1e'
down_revision: Union[str, None] = '506e26659117'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Drop existing webhooks — they were per-company and are incompatible
    # with the new per-software schema.
    op.execute("DELETE FROM jira_webhooks")

    # SQLite requires batch mode to alter table structure.
    with op.batch_alter_table('jira_webhooks', schema=None) as batch_op:
        batch_op.add_column(sa.Column('software_id', sa.Uuid(), nullable=False,
                                       server_default='00000000-0000-0000-0000-000000000000'))
        batch_op.alter_column('software_id', server_default=None)
        batch_op.drop_index(op.f('ix_jira_webhooks_company_id'))
        batch_op.create_index(op.f('ix_jira_webhooks_company_id'), ['company_id'], unique=False)
        batch_op.create_index(op.f('ix_jira_webhooks_software_id'), ['software_id'], unique=True)
        batch_op.create_foreign_key(
            'fk_jira_webhooks_software_id',
            'software_registrations', ['software_id'], ['id']
        )


def downgrade() -> None:
    with op.batch_alter_table('jira_webhooks', schema=None) as batch_op:
        batch_op.drop_constraint('fk_jira_webhooks_software_id', type_='foreignkey')
        batch_op.drop_index(op.f('ix_jira_webhooks_software_id'))
        batch_op.drop_index(op.f('ix_jira_webhooks_company_id'))
        batch_op.create_index(op.f('ix_jira_webhooks_company_id'), ['company_id'], unique=True)
        batch_op.drop_column('software_id')
