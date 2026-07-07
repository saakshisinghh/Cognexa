# INDUS MIND
### The Operating Memory of Industrial Enterprises

> **Phase 1 MVP** — Enterprise AI platform for industrial document intelligence. Upload, OCR, chunk, embed, and chat with your industrial documents using semantic search and RAG-powered copilot.

---

## Architecture

```
indusmind/
├── apps/
│   ├── api/                   # FastAPI monolith (Python 3.11)
│   │   ├── main.py            # App entrypoint, lifespan, middleware
│   │   ├── config.py          # Pydantic-settings environment config
│   │   ├── db.py              # SQLAlchemy engine + session
│   │   ├── weaviate_client.py # Weaviate singleton + schema init
│   │   ├── models/            # SQLAlchemy ORM models
│   │   ├── schemas/           # Pydantic request/response schemas
│   │   ├── routers/           # FastAPI routers (auth, documents, search, copilot, assets)
│   │   ├── services/          # Business logic (ocr, chunker, extractor, embedder, rag)
│   │   └── tests/             # Pytest unit tests
│   └── web/                   # Next.js 14 App Router (TypeScript)
│       ├── app/               # Pages (dashboard, documents, copilot, search, assets)
│       ├── components/        # Reusable React components
│       ├── lib/               # API client, utilities
│       ├── store/             # Zustand state stores
│       └── types/             # TypeScript type definitions
├── docker-compose.yml         # Full stack: Postgres + Weaviate + MinIO + API + Web
├── .env.example               # All environment variables documented
├── Makefile                   # Developer shortcuts
└── .github/workflows/ci.yml   # CI: lint, test, type-check, Docker build
```

### Data Flow

```
Upload → MinIO Storage
      → OCR (Tesseract / AWS Textract)
      → NER Entity Extraction (spaCy)
      → Recursive Chunking
      → Sentence-Transformers Embedding
      → Weaviate Vector Store + PostgreSQL metadata

Query → Embed question
      → Weaviate ANN search (cosine similarity)
      → Retrieve top-K chunks
      → Assemble context + prompt
      → Stream LLM response (SSE)
      → Return answer + sources + confidence
```

### Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 14 App Router, TypeScript, Tailwind CSS, shadcn/ui, Zustand, React Query, Framer Motion |
| Backend | FastAPI, SQLAlchemy 2.0, Pydantic v2, Alembic |
| Database | PostgreSQL 16 |
| Vector DB | Weaviate 1.25 |
| Object Storage | MinIO |
| OCR | PyMuPDF + Tesseract (Textract abstraction layer) |
| NER | spaCy en_core_web_sm + regex industrial patterns |
| Embeddings | Sentence-Transformers (all-MiniLM-L6-v2) |
| LLM | OpenAI-compatible API (GPT-4o-mini default, Ollama compatible) |
| Auth | JWT + bcrypt + refresh token rotation + RBAC |
| Deployment | Docker Compose |
| CI/CD | GitHub Actions |

---

## Quick Start

### Prerequisites

- Docker Engine 24+
- Docker Compose V2
- 8GB RAM minimum (for embedding model)
- OpenAI API key (or local Ollama)

### 1. Clone and configure

```bash
git clone https://github.com/your-org/indusmind.git
cd indusmind
cp .env.example .env
```

Edit `.env` and set at minimum:
```env
SECRET_KEY=your-very-secure-random-key-here
OPENAI_API_KEY=sk-your-openai-key
```

### 2. Start all services

```bash
make up
# or: docker compose up --build
```

First startup takes 3–5 minutes (downloads embedding model, spaCy model).

### 3. Create admin user

```bash
make seed
```

This creates: `admin@indusmind.io` / `admin1234`

### 4. Access the platform

| Service | URL |
|---------|-----|
| Web App | http://localhost:3000 |
| API Docs | http://localhost:8000/api/docs |
| MinIO Console | http://localhost:9001 (minioadmin/minioadmin) |
| Weaviate | http://localhost:8080 |

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | — | **Required.** JWT signing key. Generate with `python -c "import secrets; print(secrets.token_urlsafe(64))"` |
| `DATABASE_URL` | postgres://indusmind:indusmind@postgres/indusmind | PostgreSQL connection URL |
| `OPENAI_API_KEY` | — | **Required.** OpenAI (or compatible) API key |
| `OPENAI_BASE_URL` | https://api.openai.com/v1 | LLM endpoint. Set to Ollama/Azure URL if needed |
| `LLM_MODEL` | gpt-4o-mini | Model name to use for RAG responses |
| `EMBEDDING_MODEL` | all-MiniLM-L6-v2 | Sentence-Transformers model (runs locally) |
| `CHUNK_SIZE` | 512 | Max tokens per document chunk |
| `CHUNK_OVERLAP` | 64 | Overlap tokens between chunks |
| `USE_TEXTRACT` | false | Use AWS Textract instead of Tesseract |
| `WEAVIATE_URL` | http://weaviate:8080 | Weaviate endpoint |
| `MINIO_ENDPOINT` | minio:9000 | MinIO endpoint |
| `NEXT_PUBLIC_API_URL` | http://localhost:8000 | API URL for the frontend |

---

## Running Locally (without Docker)

### Backend

```bash
cd apps/api

# Install system dependencies (Ubuntu/Debian)
sudo apt-get install tesseract-ocr libgl1-mesa-glx

# Install Python dependencies
pip install -r requirements.txt
python -m spacy download en_core_web_sm

# Start services (Postgres, Weaviate, MinIO) via Docker
docker compose up postgres weaviate minio -d

# Run API
DATABASE_URL=postgresql://indusmind:indusmind@localhost:5432/indusmind \
  uvicorn apps.api.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend

```bash
cd apps/web
npm install
NEXT_PUBLIC_API_URL=http://localhost:8000 npm run dev
```

---

## API Overview

All endpoints are prefixed with `/api/v1`. Full Swagger docs at `/api/docs`.

### Authentication (`/auth`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/auth/signup` | Register new user |
| POST | `/auth/login` | Login → access + refresh tokens |
| POST | `/auth/refresh` | Rotate refresh token |
| POST | `/auth/logout` | Revoke refresh token |
| GET | `/auth/me` | Current user profile |

### Documents (`/documents`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/documents/upload` | Upload single document (multipart) |
| POST | `/documents/bulk-upload` | Upload up to 20 documents |
| GET | `/documents` | List with pagination, filters, search |
| GET | `/documents/{id}` | Document detail + chunks |
| PATCH | `/documents/{id}` | Update metadata, tags, category |
| DELETE | `/documents/{id}` | Delete + cleanup vectors + storage |
| POST | `/documents/{id}/reprocess` | Re-run OCR + embedding pipeline |
| GET | `/documents/{id}/download` | Stream raw file |
| GET | `/documents/{id}/chunks` | Paginated chunks list |

### Search (`/search`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/search` | Semantic search with filters |
| GET | `/search/suggest` | Autocomplete suggestions |

### Copilot (`/copilot`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/copilot/conversations` | Create conversation |
| GET | `/copilot/conversations` | List user's conversations |
| GET | `/copilot/conversations/{id}` | Conversation + messages |
| DELETE | `/copilot/conversations/{id}` | Delete conversation |
| POST | `/copilot/conversations/{id}/messages` | Send message (non-streaming) |
| POST | `/copilot/conversations/{id}/messages/stream` | Send message (SSE streaming) |

### Assets (`/assets`)
| Method | Path | Description |
|--------|------|-------------|
| POST | `/assets` | Create asset |
| GET | `/assets` | List with pagination + filters |
| GET | `/assets/{id}` | Asset detail |
| PATCH | `/assets/{id}` | Update asset |
| DELETE | `/assets/{id}` | Delete asset |
| GET | `/assets/{id}/documents` | Linked documents |
| GET | `/assets/{id}/stats` | Storage + processing stats |

### Agents (`/agents`) — Phase 5
| Method | Path | Description |
|--------|------|-------------|
| GET | `/agents` | List registered agents (catalog) |
| GET | `/agents/{agent_key}` | Agent detail |
| PATCH | `/agents/{agent_key}` | Enable/disable agent (admin only) |
| GET | `/agents/health` | Health check all agents |
| GET | `/agents/{agent_key}/health` | Health check one agent |
| POST | `/agents/{agent_key}/run` | Run agent (`stream: true` for SSE) |
| POST | `/agents/{agent_key}/cancel/{execution_id}` | Request cancellation |
| GET | `/agents/executions` | Execution history (filterable by agent/status) |
| GET | `/agents/executions/{execution_id}` | Execution detail (plan, answer, confidence, sources) |
| GET | `/agents/executions/{execution_id}/logs` | Raw execution step log |
| POST | `/agents/workflows` | Run a multi-agent workflow (sequential/parallel/supervisor) |
| GET | `/agents/workflows/{workflow_id}` | Workflow detail |

See [`docs/architecture/phase5-agentic-platform.md`](docs/architecture/phase5-agentic-platform.md) for the full agent architecture, execution flow, and tool system.

---

## Using with Ollama (Local LLM)

```env
OPENAI_BASE_URL=http://host.docker.internal:11434/v1
OPENAI_API_KEY=ollama
LLM_MODEL=llama3.2:3b
```

```bash
ollama pull llama3.2:3b
```

---

## Makefile Commands

```bash
make dev          # Start with live logs
make up           # Start detached
make down         # Stop all
make logs         # Tail all logs
make seed         # Create demo admin
make test         # Run pytest
make lint         # Flake8 + TypeScript
make shell-api    # Bash into API container
make db-shell     # psql shell
make clean        # Full cleanup
make health       # Check service health
```

---

## User Roles

| Role | Permissions |
|------|------------|
| `admin` | Full access including user management |
| `engineer` | Upload, process, search, chat |
| `viewer` | Search and chat only |

---

## Deployment

For production deployment:

1. Set strong `SECRET_KEY`
2. Set real database credentials
3. Configure MinIO with proper credentials or swap for S3
4. Use a real domain in `CORS_ORIGINS`
5. Put Nginx/Caddy in front of both services
6. Enable Weaviate authentication

```bash
# Production build
docker compose -f docker-compose.yml up -d --build
```

---

## Phase Roadmap

| Phase | Scope | Status |
|-------|-------|--------|
| **P1 MVP** | Document upload, OCR, embedding, semantic search, RAG copilot, assets, auth | ✅ Complete |
| **P2 Production** | Celery workers, Redis queue, audit log | ✅ Complete |
| **P3 Knowledge Graph** | Neo4j entity graph, graph queries | ✅ Complete |
| **P4 Copilot+** | Cross-encoder reranking, enhanced prompts, confidence scoring | ✅ Complete |
| **P5 Agents** | LangGraph RCA/maintenance/compliance/lessons agents, multi-agent workflows | ✅ **This release** |
| P6 Memory | Temporal memory, knowledge decay, time machine | Planned |
| P7 Enterprise | Microservices, Kubernetes, Kafka, Terraform | Future |

---

## Contributing

1. Create feature branch from `develop`
2. Make changes, run `make lint` and `make test`  
3. Open PR against `develop`
4. CI must pass before merge

---

*Built with ❤️ for industrial engineers. INDUS MIND — Phase 1 MVP.*
