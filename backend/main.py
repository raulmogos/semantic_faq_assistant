import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from starlette.responses import Response

from agent import RouterAgent
from celery.result import AsyncResult
from tasks.embed_task import rebuild_embeddings
from utils.logging_config import setup_logging
from repos.message_store import MessageMetadataStore
from schemas import AskQuestionRequest, AskQuestionResponse, ConversationMessage, SessionSummary
from repos.session_repository import SessionRepository
from settings import get_settings

settings = get_settings()
setup_logging(settings)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application")
    message_store = MessageMetadataStore(settings.database_url)
    await message_store.setup()

    async with AsyncPostgresSaver.from_conn_string(
        settings.database_url
    ) as checkpointer:
        logger.info("Setting up PostgreSQL checkpointer tables")
        await checkpointer.setup()
        agent = RouterAgent(
            settings,
            settings.get_vector_store(),
            checkpointer=checkpointer,
            message_store=message_store,
        )
        app.state.agent = agent
        app.state.sessions = SessionRepository(agent._agent, checkpointer, message_store)
        logger.info("Application ready")
        yield

    await message_store.close()
    logger.info("Shutting down application")


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def log_requests(request: Request, call_next) -> Response:
    logger.info("%s %s", request.method, request.url.path)
    response = await call_next(request)
    logger.info("%s %s -> %s", request.method, request.url.path, response.status_code)
    return response


@app.get("/sessions", response_model=list[SessionSummary])
async def list_sessions(request: Request) -> list[SessionSummary]:
    """List all stored conversation sessions."""
    return await request.app.state.sessions.list_sessions()


@app.get("/sessions/{session_id}", response_model=list[ConversationMessage])
async def get_session(session_id: str, request: Request) -> list[ConversationMessage]:
    """Retrieve the full message history for a given session."""
    return await request.app.state.sessions.get_history(session_id)


@app.delete("/sessions/{session_id}", status_code=204)
async def delete_session(session_id: str, request: Request) -> None:
    """Delete a session and all its associated data."""
    await request.app.state.sessions.delete(session_id)


@app.post("/admin/embed", status_code=202)
async def trigger_embed() -> dict:
    """Enqueue an async embeddings rebuild task. Returns the task ID immediately."""
    task = rebuild_embeddings.delay()
    logger.info("trigger_embed: enqueued task_id=%s", task.id)
    return {"task_id": task.id, "status": "queued"}


@app.get("/admin/embed/{task_id}")
async def embed_status(task_id: str) -> dict:
    """Poll the status of an embeddings rebuild task."""
    result = AsyncResult(task_id)
    response: dict = {"task_id": task_id, "status": result.status}
    if result.successful():
        response["result"] = result.result
    elif result.failed():
        response["error"] = str(result.result)
    return response


@app.post("/ask-question", response_model=AskQuestionResponse)
async def ask_question(q: AskQuestionRequest, request: Request) -> AskQuestionResponse:
    logger.info("session_id=%s question=%r", q.session_id, q.question)
    result = await request.app.state.agent.ask(q.session_id, q.question)
    logger.info("source=%s similarity_score=%s", result.source, result.similarity_score)
    return AskQuestionResponse(
        answer=result.answer,
        source=result.source,
        similarity_score=result.similarity_score,
    )
