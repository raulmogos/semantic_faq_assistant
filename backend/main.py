import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from starlette.responses import Response

from app.agent import RouterAgent
from app.api import router
from app.repos.message_store import MessageMetadataStore
from app.repos.session_repository import SessionRepository
from app.repos.user_repository import UserRepository
from app.settings import get_settings
from app.utils.logging_config import setup_logging

settings = get_settings()
setup_logging(settings)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting application")

    user_repo = UserRepository(settings.database_url)
    await user_repo.setup()
    app.state.user_repo = user_repo

    message_store = MessageMetadataStore(settings.database_url)
    await message_store.setup()

    async with AsyncPostgresSaver.from_conn_string(settings.database_url) as checkpointer:
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
    await user_repo.close()
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


app.include_router(router)
