import json
import logging
import uuid

from langchain.agents import create_agent
from langgraph.prebuilt import create_react_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_postgres import PGVector
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph

from message_store import MessageMetadataStore
from schemas import AgentResponse, ConversationMessage, FaqAnswer, SessionSummary
from settings import Settings
from similarity_search import create_search_faq_tool

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a helpful FAQ assistant.

Follow these steps for every question:
1. Is the question IT related and follows the topics that the system is designed to answer?
    If not, we have to route it to a Compliance Agent, set source='compliance'. Any other questions which are unrelated to IT should be answered by the Compliance Agent, set source='compliance'.
    If the question is somehow related to the conversation history, we have to route it to a OpenAI Agent, set source='llm'.
2. Always call the search_faq tool with the user's question.
3. Read the tool result carefully — it includes similarity_score, threshold.
4. Take a decision based on the relevancy of the question and the similarity_score should be above the threshold.
5. If you decide to respond from your own knowledge: answer using the conversation history and set source='llm',
    otherwise return the answer from the search_faq tool and set source='vector_search'.
6. Always set similarity_score to the value returned by the tool (null if no results).
5. Reply with ONLY a valid JSON object — no prose, no markdown — in this exact shape:
   {"answer": "<plain text answer>", "source": "<vector_search|llm|compliance>", "similarity_score": <float or null>}
"""

class RouterAgent:
    """
    Orchestrates the three-path routing logic:
      - vector_search: high-confidence FAQ match found in the knowledge base
      - llm: on-topic question answered by the OpenAI subagent
      - compliance: off-topic or inappropriate question
    """

    def __init__(
        self,
        settings: Settings,
        vector_store: PGVector,
        checkpointer: BaseCheckpointSaver | None = None,
        message_store: MessageMetadataStore | None = None,
    ) -> None:
        self._settings = settings
        self._vector_store = vector_store
        self._checkpointer = checkpointer
        self._message_store = message_store
        self._agent = self._build_router()
        logger.info(
            "RouterAgent ready: model=%s collection=%s threshold=%.2f",
            settings.openai_model,
            settings.vector_collection_name,
            settings.similarity_threshold,
        )

    # ------------------------------------------------------------------
    # Tools
    # ------------------------------------------------------------------

    @staticmethod
    @tool
    def ask_compliance_agent() -> str:
        """
        Compliance Agent. Invoke when the user's question is completely off-topic
        or inappropriate for an IT FAQ assistant. Always returns a fixed response.
        """
        logger.info("ask_compliance_agent: triggered")
        return "This is not really what I was trained for, therefore I cannot answer. Try again."

    def _build_openai_subagent_tool(self):
        """
        Build the ask_openai_subagent tool bound to this instance's LLM.
        The subagent answers on-topic questions not found in the knowledge base,
        using the serialised conversation history for context.
        """
        settings = self._settings
        logger.debug(
            "_build_openai_subagent_tool: initialising subagent with model=%s",
            settings.openai_model,
        )
        subagent = create_agent(
            settings.get_llm(),
            system_prompt=(
                "You are a helpful FAQ assistant. "
                "Answer the question from your own knowledge or from the conversation history. "
                "If you don't know, say so and suggest the user contact support."
            ),
        )

        @tool
        def ask_openai_subagent(question: str, history: str = "[]") -> str:
            """
            OpenAI subagent for on-topic questions not found in the knowledge base.
            Pass the full conversation history as a JSON array so the subagent has context.
            """
            try:
                parsed_history = json.loads(history)
            except json.JSONDecodeError:
                logger.warning(
                    "ask_openai_subagent: malformed history JSON, proceeding without history. "
                    "question=%r history_preview=%r",
                    question,
                    history[:120],
                )
                parsed_history = []

            logger.info(
                "ask_openai_subagent: question=%r history_len=%d",
                question,
                len(parsed_history),
            )
            config = {"configurable": {"thread_id": str(uuid.uuid4())}}
            history_messages = [
                HumanMessage(content=m["content"]) if m["role"] == "user"
                else AIMessage(content=m["content"])
                for m in parsed_history
                if isinstance(m, dict) and "role" in m and "content" in m
            ]
            result = subagent.invoke(
                {"messages": history_messages + [HumanMessage(content=question)]},
                config=config,
            )
            for msg in reversed(result.get("messages", [])):
                if isinstance(msg, AIMessage) and msg.content:
                    logger.info(
                        "ask_openai_subagent: response length=%d", len(str(msg.content))
                    )
                    return str(msg.content)
            logger.warning("ask_openai_subagent: no AIMessage found in subagent result")
            return "I could not generate a response."

        return ask_openai_subagent

    # ------------------------------------------------------------------
    # Agent construction
    # ------------------------------------------------------------------

    def _build_router(self) -> CompiledStateGraph:
        """Assemble the LangGraph router agent with all tools and checkpointer."""
        search_tool = create_search_faq_tool(self._settings, self._vector_store)
        openai_tool = self._build_openai_subagent_tool()
        return create_react_agent(
            self._settings.get_llm(),
            tools=[search_tool, self.ask_compliance_agent, openai_tool],
            prompt=SYSTEM_PROMPT,
            checkpointer=self._checkpointer,
        )

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def _extract_response(self, result: dict) -> FaqAnswer:
        """
        Extract and clean the router agent's raw result into a FaqAnswer.

        The agent is prompted to return a JSON object as its final message.
        We scan messages in reverse and try to parse the first AIMessage that
        contains a JSON-encoded AgentResponse. If parsing fails, the raw text
        is returned as an llm answer.
        """
        for message in reversed(result.get("messages", [])):
            if not isinstance(message, AIMessage) or not message.content:
                continue
            content = str(message.content).strip()
            try:
                data = json.loads(content)
                # Unwrap double-encoded answer field if the model nested JSON inside JSON
                if isinstance(data.get("answer"), str):
                    try:
                        inner = json.loads(data["answer"])
                        if isinstance(inner, dict) and "answer" in inner:
                            logger.warning("_extract_response: unwrapping double-encoded answer")
                            data = inner
                    except (json.JSONDecodeError, TypeError):
                        pass
                parsed = AgentResponse.model_validate(data)
                logger.info(
                    "_extract_response: source=%s similarity_score=%s",
                    parsed.source,
                    parsed.similarity_score,
                )
                return FaqAnswer(
                    answer=parsed.answer,
                    source=parsed.source,
                    similarity_score=parsed.similarity_score,
                )
            except Exception:
                logger.warning("_extract_response: could not parse AIMessage as JSON, using raw content")
                return FaqAnswer(answer=content, source="llm")

        logger.error("_extract_response: no usable AIMessage found in agent result")
        return FaqAnswer(answer="I do not know.", source="llm")
    
    async def delete_session(self, session_id: str) -> None:
        """
        Delete a conversation session from all storage layers:
        - message_metadata table (our source/similarity data)
        - LangGraph checkpoint tables (checkpoints, checkpoint_blobs, checkpoint_writes)
        """
        logger.info("RouterAgent.delete_session: session_id=%s", session_id)

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
                        "RouterAgent.delete_session: deleted from %s rows=%d",
                        table,
                        cur.rowcount,
                    )

        logger.info("RouterAgent.delete_session: session_id=%s deleted", session_id)

    async def get_session_history(self, session_id: str) -> list[ConversationMessage]:
        """
        Retrieve all messages for a given session, enriched with source and similarity_score
        from the message_metadata table when available.
        """
        logger.info("RouterAgent.get_session_history: session_id=%s", session_id)
        config = {"configurable": {"thread_id": session_id}}
        state = await self._agent.aget_state(config)
        if not state or not state.values:
            logger.info("RouterAgent.get_session_history: no state found for session_id=%s", session_id)
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
                    parsed = AgentResponse.model_validate_json(content)
                    content = parsed.answer
                except Exception:
                    pass
                messages.append(ConversationMessage(
                    role="assistant",
                    content=content,
                    source=meta.source if meta else None,
                    similarity_score=meta.similarity_score if meta else None,
                ))

        logger.info(
            "RouterAgent.get_session_history: session_id=%s returned %d messages",
            session_id,
            len(messages),
        )
        return messages

    async def list_sessions(self) -> list[SessionSummary]:
        """
        List all conversation sessions stored in the checkpointer.
        Each session includes a preview taken from the first user message.
        """
        logger.info("RouterAgent.list_sessions: fetching all sessions")
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

            sessions.append(SessionSummary(
                session_id=thread_id,
                message_count=meta.get("step", 0),
                preview=preview,
            ))

        logger.info("RouterAgent.list_sessions: found %d sessions", len(sessions))
        return sessions

    async def ask(self, session_id: str, question: str) -> FaqAnswer:
        """
        Invoke the router agent for a given session and question.

        session_id is used as the LangGraph thread_id so the InMemorySaver checkpointer
        accumulates conversation history automatically — no manual history passing needed.
        Each call only submits the new question; prior turns are replayed from the checkpoint.
        """
        logger.info("RouterAgent.ask: session_id=%s question=%r", session_id, question)
        config = {"configurable": {"thread_id": session_id}}
        result = await self._agent.ainvoke(
            {"messages": [HumanMessage(content=question)]},
            config=config,
        )

        answer = self._extract_response(result)

        if self._message_store:
            await self._message_store.save(
                session_id=session_id,
                source=answer.source,
                similarity_score=answer.similarity_score,
            )

        return answer
