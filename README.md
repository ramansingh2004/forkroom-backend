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
- Docker Compose services for PostgreSQL, Redis, and Mailpit
- Ruff, mypy, Pytest, and HTTPX configuration

The Hocuspocus collaboration service, Celery workers, RabbitMQ, and MinIO will
be added in later milestones.

Authentication currently includes:

- registration with email verification
- login with access and rotating refresh tokens
- secure logout and refresh-token reuse detection
- forgot-password and one-time password reset links
- global token invalidation after a password reset
- Redis-backed per-IP authentication rate limits

Mailpit captures local verification and password-reset messages without sending
real email. Open http://localhost:8025 after registering or requesting a reset.

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
docker compose up -d postgres redis mailpit
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Windows Command Prompt:

```bat
copy .env.example .env
uv sync --dev
docker compose up -d postgres redis mailpit
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Open:

- API documentation: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json
- Liveness: http://localhost:8000/api/v1/health/live
- Readiness: http://localhost:8000/api/v1/health/ready
- Mailpit inbox: http://localhost:8025

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
docker compose logs -f postgres redis mailpit
docker compose down
```

PostgreSQL is exposed on `localhost:5434`, Redis on `localhost:6379`, Mailpit
SMTP on `localhost:1025`, and the Mailpit inbox on `localhost:8025`.

## First development sequence

1. Foundation and health checks (this milestone)
2. User model and first Alembic migration
3. Registration, login, refresh rotation, and logout
4. Email verification and password recovery
5. Workspace model, membership, and role permissions
6. Decision model and lifecycle
