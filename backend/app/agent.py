import json
import logging
import uuid

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.tools import tool
from langchain_postgres import PGVector
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph.state import CompiledStateGraph
from langgraph.prebuilt import create_react_agent

from app.repos.message_store import MessageMetadataStore
from app.schemas import AgentResponse
from app.settings import Settings
from app.similarity_search import create_search_faq_tool

logger = logging.getLogger(__name__)


SYSTEM_PROMPT = """You are a helpful FAQ assistant with memory of the full conversation history.

Follow these steps for every new question:

1. Check if the question refers to the current conversation (e.g. "what was my first question?",
   "summarise our chat", "what did I ask earlier?").
   - If YES: answer directly from the conversation history visible to you. Set source='llm',
     similarity_score=null. Do NOT call any tool. Skip to step 5.

2. Is the question IT-related (accounts, billing, security, settings, passwords, devices, etc.)?
   - If NO (completely off-topic, unrelated to IT): call ask_compliance_agent. Set source='compliance'.
   - If YES: continue to step 3.

3. Call the search_faq tool with the user's question.

4. Read the tool result (it includes similarity_score and threshold).
   - If similarity_score >= threshold: return the knowledge-base answer in a personalized way. This means that the
        answers should be augmented with the retrieved information. Set source='vector_search'.
   - If similarity_score < threshold: call ask_openai_subagent with the question and a JSON array
     of previous turns as `history`. Set source='llm'.

5. Always set similarity_score to the value returned by search_faq (null if no tool was called).

6. Reply with ONLY a valid JSON object — no prose, no markdown — in this exact shape:
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
                (
                    HumanMessage(content=m["content"])
                    if m["role"] == "user"
                    else AIMessage(content=m["content"])
                )
                for m in parsed_history
                if isinstance(m, dict) and "role" in m and "content" in m
            ]
            result = subagent.invoke(
                {"messages": history_messages + [HumanMessage(content=question)]},
                config=config,
            )
            for msg in reversed(result.get("messages", [])):
                if isinstance(msg, AIMessage) and msg.content:
                    logger.info("ask_openai_subagent: response length=%d", len(str(msg.content)))
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

    def _extract_response(self, result: dict) -> AgentResponse:
        """
        Extract and clean the router agent's raw result into an AgentResponse.

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
                return parsed
            except Exception:
                logger.warning(
                    "_extract_response: could not parse AIMessage as JSON, using raw content"
                )
                return AgentResponse(answer=content, source="llm")

        logger.error("_extract_response: no usable AIMessage found in agent result")
        return AgentResponse(answer="I do not know.", source="llm")

    async def ask(self, session_id: str, question: str) -> AgentResponse:
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
