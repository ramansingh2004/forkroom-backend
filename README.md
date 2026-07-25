# ForkRoom Backend

Backend monorepository for ForkRoom, a real-time collaborative decision
workspace.

This first milestone contains the FastAPI foundation:

- versioned API routing
- validated environment configuration
- asynchronous PostgreSQL access with SQLAlchemy and asyncpg
- Redis client and dependency
- liveness and readiness health checks
- Alembic migration wiring
- Docker Compose services for PostgreSQL and Redis
- Ruff, mypy, Pytest, and HTTPX configuration

The Hocuspocus collaboration service, Celery workers, RabbitMQ, and MinIO will
be added in later milestones.

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop (for PostgreSQL and Redis)

## Local setup

```bash
git clone <your-backend-repository-url>
cd forkroom-backend

cp .env.example .env
uv sync --dev
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Windows Command Prompt:

```bat
copy .env.example .env
uv sync --dev
docker compose up -d postgres redis
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Open:

- API documentation: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json
- Liveness: http://localhost:8000/api/v1/health/live
- Readiness: http://localhost:8000/api/v1/health/ready

## Quality checks

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run pytest
```

To automatically format the code:

```bash
uv run ruff format .
uv run ruff check --fix .
```

## Initial architecture

```text
app/
├── controllers/    Request orchestration
├── core/           Settings and infrastructure clients
├── dependencies/   Reusable FastAPI dependencies
├── middleware/     HTTP and WebSocket middleware
├── models/         SQLAlchemy models
├── permissions/    Authorization policies
├── repositories/   Database access
├── routes/         HTTP and WebSocket endpoints
├── schemas/        Request and response DTOs
├── services/       Business rules
├── utils/          Shared helpers
└── validators/     Domain-specific validation
```

Keep HTTP-specific behavior in routes/controllers, business rules in services,
and SQLAlchemy queries in repositories.

## Docker services

```bash
docker compose up -d
docker compose ps
docker compose logs -f postgres redis
docker compose down
```

PostgreSQL is exposed on `localhost:5432` and Redis on `localhost:6379`.

## First development sequence

1. Foundation and health checks (this milestone)
2. User model and first Alembic migration
3. Registration, login, refresh rotation, and logout
4. Workspace model, membership, and role permissions
5. Decision model and lifecycle

