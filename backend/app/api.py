import logging

from celery.result import AsyncResult
from fastapi import APIRouter, Request

from app.schemas import AskQuestionRequest, AskQuestionResponse, ConversationMessage, SessionSummary
from app.tasks.embed_task import rebuild_embeddings

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(request: Request) -> list[SessionSummary]:
    """List all stored conversation sessions."""
    return await request.app.state.sessions.list_sessions()


@router.get("/sessions/{session_id}", response_model=list[ConversationMessage])
async def get_session(session_id: str, request: Request) -> list[ConversationMessage]:
    """Retrieve the full message history for a given session."""
    return await request.app.state.sessions.get_history(session_id)


@router.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request) -> None:
    """Delete a session and all its associated data."""
    await request.app.state.sessions.delete(session_id)


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


@router.post("/ask-question", response_model=AskQuestionResponse)
async def ask_question(q: AskQuestionRequest, request: Request) -> AskQuestionResponse:
    """Answer a question using the router agent."""
    logger.info("session_id=%s question=%r", q.session_id, q.question)
    result = await request.app.state.agent.ask(q.session_id, q.question)
    logger.info("source=%s similarity_score=%s", result.source, result.similarity_score)
    return AskQuestionResponse(
        answer=result.answer,
        source=result.source,
        similarity_score=result.similarity_score,
    )
