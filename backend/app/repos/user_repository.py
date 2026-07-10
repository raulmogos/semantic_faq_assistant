import logging

import bcrypt as _bcrypt
from sqlalchemy import select

from app.repos.database import Base, build_engine_and_session
from app.repos.models import User, UserSession

logger = logging.getLogger(__name__)


def _truncate(password: str) -> bytes:
    """bcrypt silently truncates at 72 bytes — enforce it explicitly."""
    return password.encode()[:72]


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(_truncate(password), _bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(_truncate(password), hashed.encode())


class UserRepository:
    """
    Async repository for user persistence and authentication.

    Responsibilities:
    - Create and verify users (hashed passwords via bcrypt)
    - Associate chat session IDs with a user
    - List all session IDs that belong to a user
    """

    def __init__(self, conn_string: str) -> None:
        self._engine, self._session_factory = build_engine_and_session(conn_string)

    async def setup(self) -> None:
        """Create all ORM tables if they do not exist."""
        logger.info("UserRepository: creating tables")
        async with self._engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        logger.info("UserRepository: tables ready")

    async def close(self) -> None:
        await self._engine.dispose()
        logger.info("UserRepository: engine disposed")

    # ------------------------------------------------------------------
    # User CRUD
    # ------------------------------------------------------------------

    async def create(self, username: str, password: str) -> User:
        """
        Create a new user with a bcrypt-hashed password.
        Raises ValueError if the username is already taken.
        """
        async with self._session_factory() as session:
            existing = await session.scalar(select(User).where(User.username == username))
            if existing:
                raise ValueError(f"Username {username!r} is already taken.")
            user = User(username=username, password_hash=_hash_password(password))
            session.add(user)
            await session.commit()
            await session.refresh(user)
            logger.info("UserRepository.create: created user_id=%d username=%r", user.id, username)
            return user

    async def get_by_username(self, username: str) -> User | None:
        """Return the User with the given username, or None if not found."""
        async with self._session_factory() as session:
            return await session.scalar(select(User).where(User.username == username))

    async def get_by_id(self, user_id: int) -> User | None:
        """Return the User with the given id, or None if not found."""
        async with self._session_factory() as session:
            return await session.scalar(select(User).where(User.id == user_id))

    async def authenticate(self, username: str, password: str) -> User | None:
        """
        Verify credentials. Returns the User on success, None on failure.
        Uses constant-time comparison to prevent timing attacks.
        """
        user = await self.get_by_username(username)
        if not user or not _verify_password(password, user.password_hash):
            logger.warning("UserRepository.authenticate: failed for username=%r", username)
            return None
        logger.info("UserRepository.authenticate: success user_id=%d", user.id)
        return user

    # ------------------------------------------------------------------
    # Session linkage
    # ------------------------------------------------------------------

    async def link_session(self, user_id: int, session_id: str) -> None:
        """
        Associate a LangGraph session_id with a user.
        Silently ignored if the mapping already exists.
        """
        async with self._session_factory() as session:
            existing = await session.scalar(
                select(UserSession).where(UserSession.session_id == session_id)
            )
            if existing:
                return
            session.add(UserSession(user_id=user_id, session_id=session_id))
            await session.commit()
            logger.debug(
                "UserRepository.link_session: user_id=%d session_id=%s", user_id, session_id
            )

    async def get_user_sessions(self, user_id: int) -> list[str]:
        """Return all session IDs belonging to a user, ordered by creation time."""
        async with self._session_factory() as session:
            rows = await session.scalars(
                select(UserSession)
                .where(UserSession.user_id == user_id)
                .order_by(UserSession.created_at)
            )
            return [row.session_id for row in rows]

    async def owns_session(self, user_id: int, session_id: str) -> bool:
        """Return True if the session belongs to the given user."""
        async with self._session_factory() as session:
            row = await session.scalar(
                select(UserSession).where(
                    UserSession.user_id == user_id,
                    UserSession.session_id == session_id,
                )
            )
            return row is not None

    async def unlink_session(self, session_id: str) -> None:
        """Remove the user-session mapping (called when a session is deleted)."""
        from sqlalchemy import delete as sa_delete

        async with self._session_factory() as session:
            await session.execute(
                sa_delete(UserSession).where(UserSession.session_id == session_id)
            )
            await session.commit()
