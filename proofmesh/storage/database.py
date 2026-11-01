from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from proofmesh.app.config import get_settings


class Base(DeclarativeBase):
    pass


engine = create_async_engine(get_settings().database_url, future=True)
Session = async_sessionmaker(engine, expire_on_commit=False)


async def initialize() -> None:
    from proofmesh.storage import models  # noqa: F401

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)


async def get_session():
    async with Session() as session:
        yield session
