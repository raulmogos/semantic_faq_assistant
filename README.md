# 🤖 Semantic FAQ Assistant

> 🔍 Ask a question. Get a smart answer — from a knowledge base, an AI agent, or a compliance guard.

A ⚡ RAG-powered FAQ chatbot that routes questions through semantic vector search, an LLM agent, or a compliance agent depending on relevance. Built with 🐍 FastAPI, 🦜 LangGraph, 🗄️ pgvector, 🌿 Celery, and ⚛️ React.

---

## Architecture

```
┌─────────────┐     ┌──────────────┐     ┌─────────────────┐
│   Frontend  │────▶│   Backend    │────▶│ Router Agent    │
│   (React)   │     │  (FastAPI)   │     │ (LangGraph)     │
└─────────────┘     └──────────────┘     └────────┬────────┘
                                                   │
                          ┌────────────────────────┼──────────────────┐
                          ▼                        ▼                  ▼
                   ┌─────────────┐       ┌──────────────┐   ┌──────────────┐
                   │  pgvector   │       │  OpenAI LLM  │   │  Compliance  │
                   │  (search)   │       │  (subagent)  │   │    Agent     │
                   └─────────────┘       └──────────────┘   └──────────────┘

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

Edit `backend/.env` and set your OpenAI API key:

```env
OPENAI_API_KEY=sk-...
```

**3. Start the stack**

```bash
docker compose up --build
```

**4. Load the knowledge base**

On first run the embeddings are not yet in the database. Trigger a rebuild:

```bash
curl -X POST http://localhost:8000/admin/embed
```

Or click the **Rebuild Embeddings** button in the top-right corner of the UI.

---

## Services & URLs

| URL | Service | Description |
|-----|---------|-------------|
| **http://localhost:3000** | Frontend | React chat UI — ask questions, browse past conversations, manage sessions |
| **http://localhost:8080** | DBgate | Database GUI — inspect PostgreSQL tables (vectors, messages, checkpoints) |
| **http://localhost:8000** | Backend API | FastAPI application (see endpoints below) |
| **http://localhost:8000/docs** | API Docs | Auto-generated Swagger UI for all endpoints |
| **http://localhost:5555** | Flower | Celery task monitor — view worker status, task queue, success/failure history |

---

## API Endpoints

### Chat

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/ask-question` | Submit a question. Body: `{ "session_id": "uuid", "question": "..." }` |

### Sessions

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/sessions` | List all past conversation sessions with preview and message count |
| `GET` | `/sessions/{session_id}` | Get full message history for a session |
| `DELETE` | `/sessions/{session_id}` | Delete a session and all its data |

### Admin

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/admin/embed` | Enqueue an async embeddings rebuild. Returns `{ "task_id": "..." }` |
| `GET` | `/admin/embed/{task_id}` | Poll the status of a rebuild task (`PENDING → STARTED → SUCCESS`) |

---

## Project Structure

```
semantic_fqa_assistant/
├── backend/
│   ├── main.py                  # FastAPI app, lifespan, middleware
│   ├── app/
│   │   ├── api.py               # All route handlers
│   │   ├── agent.py             # LangGraph router agent
│   │   ├── celery_app.py        # Celery instance
│   │   ├── schemas.py           # Pydantic models
│   │   ├── settings.py          # Centralised configuration
│   │   ├── similarity_search.py # Cosine similarity over pgvector
│   │   ├── repos/
│   │   │   ├── message_store.py      # SQLAlchemy ORM for message metadata
│   │   │   └── session_repository.py # Session CRUD over LangGraph checkpoints
│   │   ├── tasks/
│   │   │   └── embed_task.py    # Celery task: rebuild embeddings
│   │   └── utils/
│   │       └── logging_config.py
│   ├── Dockerfile
│   ├── requirements.txt
│   └── pyproject.toml           # ruff / black / isort config
├── frontend/
│   └── src/
│       ├── App.jsx              # Chat UI with session sidebar
│       └── theme.js             # MUI theme (yellow #ffd000)
├── data/
│   └── knowledge_base.json      # FAQ source data
├── db/
│   └── init.sql                 # PostgreSQL init (vector extension, tables)
└── docker-compose.yml
```

---

## Development

### Linting & formatting (from `backend/`)

```bash
ruff check . --fix   # lint + auto-fix imports
black .              # format
isort .              # sort imports
```
```
ruff check . --fix && black . && isort .
```

### Useful Docker commands

```bash
docker compose up --build          # build and start everything
docker compose up -d               # start in background
docker compose logs -f backend     # tail backend logs
docker compose restart backend     # restart backend after code changes
docker compose down -v             # stop and remove volumes (full reset)
```
