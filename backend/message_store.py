import logging
from dataclasses import dataclass

import psycopg
from psycopg.rows import dict_row

logger = logging.getLogger(__name__)

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS message_metadata (
    id               SERIAL PRIMARY KEY,
    session_id       TEXT        NOT NULL,
    role             TEXT        NOT NULL DEFAULT 'assistant',
    source           TEXT        NOT NULL,
    similarity_score FLOAT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_message_metadata_session_id
    ON message_metadata (session_id, created_at);
"""


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
    into the message_metadata PostgreSQL table.

    Uses a single persistent async connection shared across all operations.
    Call setup() once at startup to ensure the table exists.
    """

    def __init__(self, conn_string: str) -> None:
        self._conn_string = conn_string
        self._conn: psycopg.AsyncConnection | None = None

    async def setup(self) -> None:
        """Open the connection and create the table if it does not exist."""
        logger.info("MessageMetadataStore: connecting to database")
        self._conn = await psycopg.AsyncConnection.connect(
            self._conn_string, autocommit=True, row_factory=dict_row
        )
        async with self._conn.cursor() as cur:
            await cur.execute(CREATE_TABLE_SQL)
        logger.info("MessageMetadataStore: table ready")

    async def close(self) -> None:
        """Close the database connection."""
        if self._conn:
            await self._conn.close()
            logger.info("MessageMetadataStore: connection closed")

    async def save(
        self,
        session_id: str,
        source: str,
        similarity_score: float | None,
        role: str = "assistant",
    ) -> None:
        """Persist metadata for one assistant message."""
        assert self._conn, "MessageMetadataStore.setup() must be called first"
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                INSERT INTO message_metadata (session_id, role, source, similarity_score)
                VALUES (%s, %s, %s, %s)
                """,
                (session_id, role, source, similarity_score),
            )
        logger.debug(
            "MessageMetadataStore.save: session_id=%s source=%s similarity_score=%s",
            session_id,
            source,
            similarity_score,
        )

    async def delete_by_session(self, session_id: str) -> int:
        """Delete all metadata rows for a session. Returns the number of rows deleted."""
        assert self._conn, "MessageMetadataStore.setup() must be called first"
        async with self._conn.cursor() as cur:
            await cur.execute(
                "DELETE FROM message_metadata WHERE session_id = %s",
                (session_id,),
            )
            deleted = cur.rowcount
        logger.info("MessageMetadataStore.delete_by_session: session_id=%s deleted=%d", session_id, deleted)
        return deleted

    async def get_by_session(self, session_id: str) -> list[MessageRecord]:
        """Return all metadata rows for a session ordered by creation time."""
        assert self._conn, "MessageMetadataStore.setup() must be called first"
        async with self._conn.cursor() as cur:
            await cur.execute(
                """
                SELECT session_id, role, source, similarity_score, created_at
                FROM message_metadata
                WHERE session_id = %s
                ORDER BY created_at ASC
                """,
                (session_id,),
            )
            rows = await cur.fetchall()
        return [
            MessageRecord(
                session_id=row["session_id"],
                role=row["role"],
                source=row["source"],
                similarity_score=row["similarity_score"],
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]
