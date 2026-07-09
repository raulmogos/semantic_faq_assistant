import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import Float, String, func, select, delete
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

logger = logging.getLogger(__name__)


class Base(DeclarativeBase):
    pass


class MessageMetadata(Base):
    """ORM model for the message_metadata table."""

    __tablename__ = "message_metadata"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    role: Mapped[str] = mapped_column(String, nullable=False, default="assistant")
    source: Mapped[str] = mapped_column(String, nullable=False)
    similarity_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        nullable=False, server_default=func.now()
    )


@dataclass
class MessageRecord:
    session_id: str
    role: str
    source: str
    similarity_score: float | None
    created_at: str | None = None


class MessageMetadataStore:
    """
    Async repository for persisting per-message metadata (source, similarity_score)
    using SQLAlchemy ORM with an async engine.

    Call setup() once at startup to create the table if it does not exist.
    """

    def __init__(self, conn_string: str) -> None:
        async_conn_string = conn_string.replace("postgresql://", "postgresql+psycopg://", 1)
        self._engine = create_async_engine(async_conn_string, echo=False)
        self._session_factory = async_sessionmaker(self._engine, expire_on_commit=False)

    async def setup(self) -> None:
        """Create the message_metadata table if it does not exist."""
        logger.info("MessageMetadataStore: creating tables")
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("MessageMetadataStore: tables ready")

    async def close(self) -> None:
        """Dispose the async engine and release all connections."""
        await self._engine.dispose()
        logger.info("MessageMetadataStore: engine disposed")

    async def save(
        self,
        session_id: str,
        source: str,
        similarity_score: float | None,
        role: str = "assistant",
    ) -> None:
        """Persist metadata for one assistant message."""
        async with self._session_factory() as session:
            session.add(MessageMetadata(
                session_id=session_id,
                role=role,
                source=source,
                similarity_score=similarity_score,
            ))
            await session.commit()
        logger.debug(
            "MessageMetadataStore.save: session_id=%s source=%s similarity_score=%s",
            session_id, source, similarity_score,
        )

    async def get_by_session(self, session_id: str) -> list[MessageRecord]:
        """Return all metadata rows for a session ordered by creation time."""
        async with self._session_factory() as session:
            result = await session.execute(
                select(MessageMetadata)
                .where(MessageMetadata.session_id == session_id)
                .order_by(MessageMetadata.created_at)
            )
            rows = result.scalars().all()
        return [
            MessageRecord(
                session_id=row.session_id,
                role=row.role,
                source=row.source,
                similarity_score=row.similarity_score,
                created_at=str(row.created_at),
            )
            for row in rows
        ]

    async def delete_by_session(self, session_id: str) -> int:
        """Delete all metadata rows for a session. Returns the number of rows deleted."""
        async with self._session_factory() as session:
            result = await session.execute(
                delete(MessageMetadata).where(MessageMetadata.session_id == session_id)
            )
            await session.commit()
            deleted = result.rowcount
        logger.info(
            "MessageMetadataStore.delete_by_session: session_id=%s deleted=%d",
            session_id, deleted,
        )
        return deleted
