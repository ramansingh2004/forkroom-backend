from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncAttrs,
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from app.core.config import get_settings


class Base(AsyncAttrs, DeclarativeBase):
    pass


settings = get_settings()
engine: AsyncEngine = create_async_engine(
    settings.database_url,
    pool_pre_ping=True,
)
async_session_factory = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db_session() -> AsyncIterator[AsyncSession]:
    async with async_session_factory() as session:
        yield session


async def dispose_database() -> None:
    await engine.dispose()
