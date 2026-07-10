from typing import Literal

from pydantic import BaseModel

AnswerSource = Literal["vector_search", "llm", "compliance"]


class AgentResponse(BaseModel):
    """Structured output returned by the router agent and used internally throughout the app."""

    answer: str
    source: AnswerSource
    similarity_score: float | None = None


class SimilaritySearchResult(BaseModel):
    """Result of a single cosine similarity search against the knowledge base."""

    question: str
    answer: str
    category: str
    similarity_score: float


class AskQuestionRequest(BaseModel):
    """
    Request body for POST /ask-question.
    session_id must be generated once by the client at conversation start
    and reused for every subsequent message in the same conversation.
    LangGraph uses it as thread_id so the checkpointer manages history automatically.
    """

    session_id: str
    question: str


class AskQuestionResponse(BaseModel):
    """Response body for POST /ask-question."""

    answer: str
    source: AnswerSource
    similarity_score: float | None = None


class ConversationMessage(BaseModel):
    """A single human or assistant message in a conversation."""

    role: Literal["user", "assistant"]
    content: str
    source: Literal["vector_search", "llm", "compliance"] | None = None
    similarity_score: float | None = None


class SessionSummary(BaseModel):
    """Brief summary of a stored conversation session."""

    session_id: str
    message_count: int
    preview: str | None = None


class RegisterRequest(BaseModel):
    """Request body for POST /auth/register."""

    username: str
    password: str


class LoginRequest(BaseModel):
    """Request body for POST /auth/login."""

    username: str
    password: str


class TokenResponse(BaseModel):
    """Response body for auth endpoints."""

    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    """Public user representation (no password)."""

    id: int
    username: str
