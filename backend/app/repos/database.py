"""
Shared SQLAlchemy async engine, session factory, and declarative base.

All ORM models import Base from here so that create_all() creates every
table in a single pass.
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass


def build_engine_and_session(conn_string: str):
    """
    Return an (engine, session_factory) tuple for the given connection string.
    Converts plain postgresql:// to postgresql+psycopg:// if needed.
    """
    async_url = conn_string.replace("postgresql://", "postgresql+psycopg://", 1)
    engine = create_async_engine(async_url, echo=False)
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    return engine, session_factory
