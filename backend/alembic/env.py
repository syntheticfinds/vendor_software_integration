import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import async_engine_from_config

from alembic import context

from app.config import settings
from app.models.base import Base
from app.companies.models import Company  # noqa: F401
from app.monitoring.models import MonitoredEmail, MonitoredDriveFile, MonitoredJiraIssue, DetectedSoftware  # noqa: F401
from app.software.models import SoftwareRegistration  # noqa: F401
from app.signals.models import SignalEvent, HealthScore, ReviewDraft  # noqa: F401
from app.portal.models import PublicSoftwareIndex, ChatSession, ChatMessage  # noqa: F401
from app.outreach.models import OutreachCampaign, OutreachMessage  # noqa: F401
from app.intelligence.models import IntelligenceCache  # noqa: F401
from app.integrations.models import EmailIntegration, JiraWebhook, JiraPollingConfig  # noqa: F401

config = context.config
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    connectable = async_engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)
    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
