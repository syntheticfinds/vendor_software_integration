import sqlalchemy.event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import settings

engine = create_async_engine(settings.DATABASE_URL, echo=False)


@sqlalchemy.event.listens_for(engine.sync_engine, "connect")
def _set_sqlite_pragmas(dbapi_conn, _connection_record):
    """Enable WAL mode and busy timeout for SQLite concurrency."""
    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA busy_timeout=5000")
    cursor.close()


async_session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    async with async_session_factory() as session:
        yield session
