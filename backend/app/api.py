import logging

from celery.result import AsyncResult
from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.auth import create_access_token, get_current_user
from app.repos.models import User
from app.schemas import (
    AskQuestionRequest,
    AskQuestionResponse,
    ConversationMessage,
    LoginRequest,
    RegisterRequest,
    SessionSummary,
    TokenResponse,
    UserResponse,
)
from app.tasks.embed_task import rebuild_embeddings

logger = logging.getLogger(__name__)

router = APIRouter()


# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------


@router.post("/auth/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, request: Request) -> TokenResponse:
    """Create a new user account and return a bearer token."""
    try:
        user = await request.app.state.user_repo.create(body.username, body.password)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    token = create_access_token(user.id)
    logger.info("register: user_id=%d username=%r", user.id, user.username)
    return TokenResponse(access_token=token)


@router.post("/auth/login", response_model=TokenResponse)
async def login(body: LoginRequest, request: Request) -> TokenResponse:
    """Authenticate with username and password, return a bearer token."""
    user = await request.app.state.user_repo.authenticate(body.username, body.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
        )
    token = create_access_token(user.id)
    logger.info("login: user_id=%d username=%r", user.id, user.username)
    return TokenResponse(access_token=token)


@router.get("/auth/me", response_model=UserResponse)
async def me(current_user: User = Depends(get_current_user)) -> UserResponse:
    """Return the currently authenticated user."""
    return UserResponse(id=current_user.id, username=current_user.username)


# ---------------------------------------------------------------------------
# Sessions (protected)
# ---------------------------------------------------------------------------


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(
    request: Request,
    current_user: User = Depends(get_current_user),
) -> list[SessionSummary]:
    """List all conversation sessions belonging to the authenticated user."""
    user_session_ids = await request.app.state.user_repo.get_user_sessions(current_user.id)
    all_sessions = await request.app.state.sessions.list_sessions()
    return [s for s in all_sessions if s.session_id in set(user_session_ids)]


@router.get("/sessions/{session_id}", response_model=list[ConversationMessage])
async def get_session(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> list[ConversationMessage]:
    """Retrieve the full message history for a session owned by the current user."""
    if not await request.app.state.user_repo.owns_session(current_user.id, session_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session not found.")
    return await request.app.state.sessions.get_history(session_id)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(
    session_id: str,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> None:
    """Delete a session owned by the current user."""
    if not await request.app.state.user_repo.owns_session(current_user.id, session_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Session not found.")
    await request.app.state.sessions.delete(session_id)
    await request.app.state.user_repo.unlink_session(session_id)


# ---------------------------------------------------------------------------
# Chat (protected)
# ---------------------------------------------------------------------------


@router.post("/ask-question", response_model=AskQuestionResponse)
async def ask_question(
    q: AskQuestionRequest,
    request: Request,
    current_user: User = Depends(get_current_user),
) -> AskQuestionResponse:
    """Answer a question using the router agent, after guardrail validation."""
    logger.info("session_id=%s question=%r user_id=%d", q.session_id, q.question, current_user.id)

    # Link session to user on first message (silently ignored if already linked)
    await request.app.state.user_repo.link_session(current_user.id, q.session_id)

    result = await request.app.state.agent.ask(q.session_id, q.question)
    logger.info("source=%s similarity_score=%s", result.source, result.similarity_score)
    return AskQuestionResponse(
        answer=result.answer,
        source=result.source,
        similarity_score=result.similarity_score,
    )


# ---------------------------------------------------------------------------
# Admin
# ---------------------------------------------------------------------------


@router.post("/admin/embed", status_code=202)
async def trigger_embed() -> dict:
    """Enqueue an async embeddings rebuild task. Returns the task ID immediately."""
    task = rebuild_embeddings.delay()
    logger.info("trigger_embed: enqueued task_id=%s", task.id)
    return {"task_id": task.id, "status": "queued"}


@router.get("/admin/embed/{task_id}")
async def embed_status(task_id: str) -> dict:
    """Poll the status of an embeddings rebuild task."""
    result = AsyncResult(task_id)
    response: dict = {"task_id": task_id, "status": result.status}
    if result.successful():
        response["result"] = result.result
    elif result.failed():
        response["error"] = str(result.result)
    return response
