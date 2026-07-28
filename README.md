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

Workspace management currently includes:

- workspace creation, listing, reading, updating, and deletion
- automatic owner membership when a workspace is created
- owner, admin, member, and viewer roles
- member listing and adding users by registered email
- owner-controlled role changes
- owner/admin member removal with owner-protection rules
- non-member workspace hiding to avoid leaking private workspace existence

Decision management currently includes:

- workspace-scoped decision creation, listing, reading, updating, and deletion
- technology, architecture, delivery, team-process, and other categories
- draft, active, closed, and archived lifecycle states
- guarded lifecycle transitions and automatic close/archive timestamps
- status/category filters with bounded pagination
- viewer read-only access and member/editor write permissions
- owner/admin-only deletion of draft decisions
- immutable closed and archived decision content
- optional due and review dates with schedule validation

Proposal comparison currently includes:

- parallel proposal branches under each decision
- draft, submitted, and withdrawn proposal states
- author-owned proposal editing with owner/admin moderation
- immutable submitted proposals until explicitly reopened
- ordered comparison criteria with weights from 1 to 100
- owner/admin criterion creation, editing, ordering, and deletion
- 1-to-5 proposal scoring with an optional rationale
- weighted comparison results for fully scored submitted proposals
- viewer read access without proposal, criterion, or score mutation rights

Structured objections currently include:

- informational, major, and blocking concern severities
- objections attached to submitted proposal branches
- open, resolved, and dismissed objection states
- objection-author resolution and reopening
- owner/admin moderation, including dismissal
- append-only transition events preserving resolution history
- severity and status filters
- a repository-level open-blocking check for the upcoming voting gate

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
7. Proposal branches and weighted comparison criteria
8. Structured objections and resolution tracking (this milestone)

## Decision lifecycle

New decisions always start as `draft`.

```text
draft -> active -> closed
  |         |         |
  +---------+---------+-> archived
              ^
              |
           reopened
```

Allowed transitions:

- `draft` to `active` or `archived`
- `active` to `closed` or `archived`
- `closed` to `active` or `archived`
- `archived` is terminal

Closed and archived decisions cannot be edited. Only draft decisions can be
deleted, and deletion requires an owner or admin role.

## Proposal comparison workflow

Each proposal begins as a `draft`. Its author, an owner, or an admin can submit,
reopen, withdraw, or delete it according to the following lifecycle:

```text
draft <-> submitted
  |          |
  +----------+-> withdrawn
```

Submitted proposals cannot be edited until they are reopened as drafts, and
withdrawn proposals are terminal. Owners and admins define ordered comparison
criteria and assign each criterion a weight from 1 to 100. Members can score a
submitted proposal from 1 to 5 and include a rationale.

The comparison endpoint returns a weighted score only when a submitted proposal
has a score for every current criterion. This prevents an incomplete proposal
from appearing artificially stronger than a fully evaluated alternative.

## Structured objection workflow

Members can raise informational, major, or blocking objections against a
submitted proposal. Objections begin as `open`. The objection author, owner, or
admin can mark an objection `resolved`; only owners and admins can dismiss one.
Resolved and dismissed objections can be reopened by the objection author,
owner, or admin.

Every status transition requires a note and creates an append-only history
event. Reopening clears the current resolution fields but does not erase the
earlier event. This preserves why a concern changed state and prepares the next
milestone to prevent voting from opening while blocking objections remain open.

The next milestone adds quorum-based voting and uses unresolved blocking
objections as a voting gate.
