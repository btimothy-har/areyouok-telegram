from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import declarative_base, sessionmaker

from areyouok_telegram.config import PG_CONNECTION_STRING

Base = declarative_base()

async_engine = create_async_engine(
    f"postgresql+asyncpg://{PG_CONNECTION_STRING}",
    pool_pre_ping=True,
    pool_size=40,
    max_overflow=20,
    pool_timeout=30,
    pool_recycle=3600,
    connect_args={
        "timeout": 10,
        "command_timeout": 60,
    },
)
AsyncDbSession = sessionmaker(async_engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def async_database():
    conn = AsyncDbSession()
    try:
        yield conn
        await conn.commit()
    except Exception:
        await conn.rollback()
        raise
    finally:
        await conn.close()
