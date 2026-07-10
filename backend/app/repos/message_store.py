import logging
from dataclasses import dataclass

from sqlalchemy import delete, select

from app.repos.database import Base, build_engine_and_session
from app.repos.models import MessageMetadata

logger = logging.getLogger(__name__)


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
        self._engine, self._session_factory = build_engine_and_session(conn_string)

    async def setup(self) -> None:
        """Create all ORM tables if they do not exist."""
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
            session.add(
                MessageMetadata(
                    session_id=session_id,
                    role=role,
                    source=source,
                    similarity_score=similarity_score,
                )
            )
            await session.commit()
        logger.debug(
            "MessageMetadataStore.save: session_id=%s source=%s similarity_score=%s",
            session_id,
            source,
            similarity_score,
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
            session_id,
            deleted,
        )
        return deleted
