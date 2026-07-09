import json
import logging

from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from app.repos.message_store import MessageMetadataStore
from app.schemas import ConversationMessage, SessionSummary

logger = logging.getLogger(__name__)


class SessionRepository:
    """
    Manages the persistence and retrieval of conversation sessions.

    Wraps two storage layers:
      - LangGraph checkpointer: stores the full agent state (messages, tool calls, etc.)
      - MessageMetadataStore: stores per-message metadata (source, similarity_score)
    """

    def __init__(
        self,
        agent: CompiledStateGraph,
        checkpointer: BaseCheckpointSaver,
        message_store: MessageMetadataStore | None = None,
    ) -> None:
        self._agent = agent
        self._checkpointer = checkpointer
        self._message_store = message_store

    async def get_history(self, session_id: str) -> list[ConversationMessage]:
        """
        Retrieve all messages for a session, enriched with source and similarity_score
        from the message_metadata table when available.
        Tool call messages and tool responses are filtered out.
        """
        logger.info("SessionRepository.get_history: session_id=%s", session_id)
        config = {"configurable": {"thread_id": session_id}}
        state = await self._agent.aget_state(config)
        if not state or not state.values:
            logger.info(
                "SessionRepository.get_history: no state found for session_id=%s", session_id
            )
            return []

        metadata_records = []
        if self._message_store:
            metadata_records = await self._message_store.get_by_session(session_id)
        meta_iter = iter(metadata_records)

        messages: list[ConversationMessage] = []
        for msg in state.values.get("messages", []):
            if isinstance(msg, HumanMessage):
                messages.append(ConversationMessage(role="user", content=str(msg.content)))
            elif isinstance(msg, AIMessage) and msg.content and not msg.tool_calls:
                meta = next(meta_iter, None)
                content = str(msg.content)
                try:
                    data = json.loads(content)
                    if isinstance(data, dict) and "answer" in data:
                        content = data["answer"]
                except (json.JSONDecodeError, TypeError):
                    pass
                messages.append(
                    ConversationMessage(
                        role="assistant",
                        content=content,
                        source=meta.source if meta else None,
                        similarity_score=meta.similarity_score if meta else None,
                    )
                )

        logger.info(
            "SessionRepository.get_history: session_id=%s returned %d messages",
            session_id,
            len(messages),
        )
        return messages

    async def list_sessions(self) -> list[SessionSummary]:
        """
        List all stored conversation sessions, each with a preview of the first user message.
        Deduplicates by thread_id so only the latest checkpoint per session is returned.
        """
        logger.info("SessionRepository.list_sessions: fetching all sessions")
        seen: set[str] = set()
        sessions: list[SessionSummary] = []

        async for checkpoint_tuple in self._checkpointer.alist({}):
            meta = checkpoint_tuple.metadata or {}
            config = checkpoint_tuple.config or {}
            thread_id = config.get("configurable", {}).get("thread_id", "unknown")

            if thread_id in seen:
                continue
            seen.add(thread_id)

            preview: str | None = None
            checkpoint = checkpoint_tuple.checkpoint or {}
            for msg in checkpoint.get("channel_values", {}).get("messages", []):
                if isinstance(msg, HumanMessage) and msg.content:
                    text = str(msg.content).strip()
                    preview = text[:80] + ("…" if len(text) > 80 else "")
                    break

            sessions.append(
                SessionSummary(
                    session_id=thread_id,
                    message_count=meta.get("step", 0),
                    preview=preview,
                )
            )

        logger.info("SessionRepository.list_sessions: found %d sessions", len(sessions))
        return sessions

    async def delete(self, session_id: str) -> None:
        """
        Delete a session from all storage layers:
        - message_metadata table
        - LangGraph checkpoint tables (checkpoints, checkpoint_blobs, checkpoint_writes)
        """
        logger.info("SessionRepository.delete: session_id=%s", session_id)

        if self._message_store:
            await self._message_store.delete_by_session(session_id)

        if hasattr(self._checkpointer, "conn"):
            conn = self._checkpointer.conn
            async with conn.cursor() as cur:
                for table in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    await cur.execute(
                        f"DELETE FROM {table} WHERE thread_id = %s",  # noqa: S608
                        (session_id,),
                    )
                    logger.debug(
                        "SessionRepository.delete: deleted from %s rows=%d",
                        table,
                        cur.rowcount,
                    )

        logger.info("SessionRepository.delete: session_id=%s deleted", session_id)
