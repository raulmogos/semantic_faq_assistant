# 🤖 Semantic FAQ Assistant

> 🔍 Ask a question. Get a smart answer — from a knowledge base, an AI agent, or a compliance guard.

A ⚡ RAG-powered FAQ chatbot that routes questions through semantic vector search, an LLM agent, or a compliance agent depending on relevance. Built with 🐍 FastAPI, 🦜 LangGraph, 🗄️ pgvector, 🌿 Celery, and ⚛️ React.

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Frontend  │────▶│   Backend    │────▶│ Router Agent    │
│  (React +   │     │  (FastAPI +  │     │ (LangGraph)     │
│   JWT auth) │     │  JWT bearer) │     └────────┬────────┘
└─────────────┘     └──────────────┘              │
                                   ┌──────────────┼──────────────┐
                                   ▼              ▼              ▼
                            ┌───────────┐  ┌──────────┐  ┌──────────────┐
                            │ pgvector  │  │ OpenAI   │  │  Compliance  │
                            │ (search)  │  │ subagent │  │    Agent     │
                            └───────────┘  └──────────┘  └──────────────┘

┌─────────────┐     ┌──────────────┐
│    Redis    │────▶│    Celery    │  (async embedding rebuild)
└─────────────┘     └──────────────┘
```

**Routing logic:**
1. Questions about the conversation history → answered directly from LangGraph state
2. Off-topic (non-IT) questions → Compliance Agent (fixed response)
3. IT questions with high vector similarity → Knowledge Base answer
4. IT questions with low vector similarity → OpenAI LLM subagent

---

## Prerequisites

- [Docker](https://www.docker.com/) and Docker Compose
- An OpenAI API key

---

## Setup

**1. Clone the repository**

```bash
git clone <repo-url>
cd semantic_fqa_assistant
```

**2. Configure environment variables**

```bash
cp backend/.env.example backend/.env
```

Edit `backend/.env` and fill in:

```env
OPENAI_API_KEY=sk-...
JWT_SECRET_KEY=<random-secret>   # python -c "import secrets; print(secrets.token_hex(32))"
```

**3. Start the stack**

```bash
docker compose up --build
```

**4. Register an account**

Open **http://localhost:3000**, click **Register**, and create your first account.

**5. Load the knowledge base**

On first run the embeddings are not yet in the database. Click the **Rebuild Embeddings** button in the top-right corner of the UI, or call the API:

```bash
curl -X POST http://localhost:8000/admin/embed
```

---

## Services & URLs

| URL | Service | Description |
|-----|---------|-------------|
| **http://localhost:3000** | Frontend | React chat UI — login, ask questions, browse past conversations |
| **http://localhost:8080** | DBgate | Database GUI — inspect PostgreSQL tables (vectors, messages, users, checkpoints) |
| **http://localhost:8000** | Backend API | FastAPI application |
| **http://localhost:8000/docs** | API Docs | Auto-generated Swagger UI for all endpoints |
| **http://localhost:5555** | Flower | Celery task monitor — worker status, task queue, success/failure history |

---

## API Endpoints

### Auth (public)

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/auth/register` | Create account. Body: `{ "username": "...", "password": "..." }` → returns bearer token |
| `POST` | `/auth/login` | Login. Same body → returns bearer token |
| `GET` | `/auth/me` | Returns current user info (requires token) |

All other endpoints require `Authorization: Bearer <token>`.

### Chat 🔒

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ask-question` | Submit a question. Body: `{ "session_id": "uuid", "question": "..." }` |

### Sessions 🔒

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sessions` | List the current user's past conversations |
| `GET` | `/sessions/{session_id}` | Get full message history for a session |
| `DELETE` | `/sessions/{session_id}` | Delete a session and all its data |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/embed` | Enqueue an async embeddings rebuild. Returns `{ "task_id": "..." }` |
| `GET` | `/admin/embed/{task_id}` | Poll the status of a rebuild task (`PENDING → STARTED → SUCCESS`) |

---

## Authentication

The app uses **stateless JWT bearer tokens** (HS256, 1 hour expiry).

- Tokens are stored in `localStorage` on the frontend
- Every protected request includes `Authorization: Bearer <token>`
- A 401 response automatically logs the user out and redirects to the login page
- Sessions are scoped per user — each user only sees their own conversations

---

## Project Structure

```
semantic_fqa_assistant/
├── backend/
│   ├── main.py                       # FastAPI app, lifespan, middleware
│   ├── app/
│   │   ├── api.py                    # All route handlers
│   │   ├── agent.py                  # LangGraph router agent
│   │   ├── auth.py                   # JWT creation/decoding, get_current_user dependency
│   │   ├── celery_app.py             # Celery instance
│   │   ├── schemas.py                # Pydantic models
│   │   ├── settings.py               # Centralised configuration
│   │   ├── similarity_search.py      # Cosine similarity over pgvector
│   │   ├── repos/
│   │   │   ├── database.py           # Shared SQLAlchemy Base + async engine factory
│   │   │   ├── models.py             # ORM models: User, UserSession, MessageMetadata
│   │   │   ├── message_store.py      # Message metadata persistence
│   │   │   ├── session_repository.py # Session CRUD over LangGraph checkpoints
│   │   │   └── user_repository.py    # User creation, auth, session linkage
│   │   ├── tasks/
│   │   │   └── embed_task.py         # Celery task: rebuild embeddings
│   │   └── utils/
│   │       └── logging_config.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pyproject.toml                # ruff / black / isort config
├── frontend/
│   └── src/
│       ├── App.jsx                   # Auth page + chat UI with session sidebar
│       └── theme.js                  # MUI theme (yellow #ffd000)
├── data/
│   └── knowledge_base.json           # FAQ source data
├── db/
│   └── init.sql                      # PostgreSQL init (vector extension)
└── docker-compose.yml
```

---

## Development

### Linting & formatting (from `backend/`)

```bash
ruff check . --fix   # lint + auto-fix
black .              # format
isort .              # sort imports
```
```bash
cd backend
ruff check . --fix && black . && isort .
```

### Useful Docker commands

```bash
docker compose up --build          # build and start everything
docker compose up -d               # start in background
docker compose logs -f backend     # tail backend logs
docker compose restart backend     # restart after code changes
docker compose down -v             # stop and remove volumes (full reset)
```
