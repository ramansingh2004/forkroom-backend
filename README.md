# ForkRoom Backend

Backend monorepository for ForkRoom, a real-time collaborative decision
workspace.

The repository contains the FastAPI API, TypeScript Hocuspocus collaboration
service, and Celery worker processes:

- versioned API routing
- validated environment configuration
- asynchronous PostgreSQL access with SQLAlchemy and asyncpg
- Redis client and dependency
- liveness and readiness health checks
- Alembic migration wiring
- Docker Compose services for PostgreSQL, Redis, RabbitMQ, MinIO, Mailpit,
  workers, Beat, and Hocuspocus
- Ruff, mypy, Pytest, and HTTPX configuration

Search indexing, PDF exports, WebRTC infrastructure, and the production
observability stack remain later milestones.

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
- a repository-level open-blocking check used by the voting gate

Quorum-based voting currently includes:

- owner/admin-created voting sessions for active decisions
- draft, open, closed, and cancelled voting-session states
- unresolved blocking-objection enforcement before opening
- at least two submitted proposal choices per session
- immutable voter and proposal eligibility snapshots at opening time
- owner, admin, and member voter eligibility with viewer exclusion
- one durable PostgreSQL ballot per eligible participant
- optional timezone-aware voting deadlines
- hidden results until the session closes
- configurable quorum percentages with invalid below-quorum outcomes
- proposal tallies, tie detection, and a winner only for valid non-tied results

Decision locking currently includes:

- owner/admin locking from a closed, quorum-valid, non-tied voting result
- a second blocking-objection check immediately before locking
- immutable snapshots of decision metadata and the winning proposal
- aggregate quorum, tally, winner, and tie outcome preservation
- dissent preservation through losing proposal and objection snapshots
- SHA-256 hashes over canonical JSON snapshots
- hash verification without exposing individual participant ballots
- database uniqueness for one lock per decision and voting session
- a terminal `locked` decision state that prevents silent edits or reopening

Implementation tracking currently includes:

- implementation actions connected directly to locked decisions
- owner/admin assignment to eligible owner, admin, or member participants
- todo, in-progress, blocked, completed, and cancelled action states
- assignee-owned progress transitions with owner/admin oversight
- optional action descriptions and timezone-aware due dates
- database-validated completion and cancellation timestamps
- terminal completed and cancelled actions retained as durable history

Scheduled decision reviews currently include:

- owner/admin review scheduling for locked decisions
- one active scheduled review per decision
- timezone-aware future review dates and optional review notes
- review rescheduling and cancellation without deleting history
- workspace-member read access to action and review records
- Celery Beat scheduling for due review reminders

Async notifications currently include:

- RabbitMQ transport with dedicated delivery, scheduler, and dead-letter queues
- Celery workers and Celery Beat scheduling
- durable PostgreSQL notification and delivery-attempt state
- action, decision-review, decision-deadline, and voting-close reminders
- stable idempotency keys that prevent duplicate notifications
- exponential retry delays with a configured maximum
- failed-delivery dead-letter routing and durable failure details
- stale delivery-lease recovery after worker crashes
- authenticated list, unread-count, read, and read-all APIs

Attachment storage currently includes:

- workspace, decision, and proposal-scoped attachment metadata
- direct browser uploads using short-lived presigned MinIO URLs
- a 25 MiB configurable upload limit
- owner, admin, and member uploads with viewer read-only access
- Celery processing with actual-size validation and SHA-256 hashing
- retry recovery and RabbitMQ dead-letter routing for failed processing
- short-lived download URLs only after processing succeeds
- soft-deleted metadata with object removal from MinIO

Mailpit captures local verification and password-reset messages without sending
real email. Open http://localhost:8025 after registering or requesting a reset.

## Prerequisites

- Python 3.12
- [uv](https://docs.astral.sh/uv/)
- Docker Desktop (for PostgreSQL, Redis, RabbitMQ, MinIO, and Mailpit)

## Local setup

```bash
git clone <your-backend-repository-url>
cd forkroom-backend

cp .env.example .env
uv sync --dev
docker compose up -d postgres redis rabbitmq minio mailpit
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Windows Command Prompt:

```bat
copy .env.example .env
uv sync --dev
docker compose up -d postgres redis rabbitmq minio mailpit
uv run alembic upgrade head
uv run uvicorn app.main:app --reload
```

Open:

- API documentation: http://localhost:8000/docs
- OpenAPI schema: http://localhost:8000/openapi.json
- Liveness: http://localhost:8000/api/v1/health/live
- Readiness: http://localhost:8000/api/v1/health/ready
- Mailpit inbox: http://localhost:8025
- RabbitMQ management: http://localhost:15672
- MinIO API: http://localhost:9000
- MinIO console: http://localhost:9001

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

PostgreSQL is exposed on `localhost:5434`, Redis on `localhost:6379`, MinIO on
`localhost:9000` with its console on `localhost:9001`, Mailpit SMTP on
`localhost:1025`, and the Mailpit inbox on `localhost:8025`.

## First development sequence

1. Foundation and health checks (this milestone)
2. User model and first Alembic migration
3. Registration, login, refresh rotation, and logout
4. Email verification and password recovery
5. Workspace model, membership, and role permissions
6. Decision model and lifecycle
7. Proposal branches and weighted comparison criteria
8. Structured objections and resolution tracking
9. Quorum-based voting (this milestone)
10. Decision locking and immutable records
11. Owned implementation actions and scheduled reviews (this milestone)
12. Collaborative editor and Redis presence
13. RabbitMQ, Celery reminders, and durable notifications
14. MinIO attachments and asynchronous file processing (this milestone)

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
- a valid voting outcome moves `active` to terminal `locked`
- `locked` can change only through a future explicit revision
- `archived` is terminal

Closed, locked, and archived decisions cannot be edited. Only draft decisions
can be deleted, and deletion requires an owner or admin role.

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

## Quorum-based voting workflow

Owners and admins create a draft voting session for an active decision and set
a quorum percentage from 1 to 100. Only one draft or open session may exist for
a decision at a time. Opening requires at least two submitted proposals and
fails while any blocking objection remains open.

When voting opens, ForkRoom snapshots both the submitted proposal choices and
all eligible workspace voters. Owners, admins, and members are eligible;
viewers are read-only. A participant can cast exactly one ballot for one
snapshotted proposal, and the database unique constraint protects this rule
under concurrent requests.

Results stay unavailable while voting is open. After an owner or admin closes
the session, ForkRoom computes:

- required votes as `ceil(eligible voters * quorum percentage / 100)`
- whether quorum was met
- each proposal's vote count and percentage
- a winner only when quorum was met and one proposal has the highest tally
- a tie when multiple proposals share the highest tally

A below-quorum result is retained for auditability but marked invalid and has
no winner. Cancelling a draft or open session is terminal; a later revote uses
a new voting session and preserves the earlier record.

## Decision locking workflow

An owner or admin can lock an active decision only from a closed voting session
that met quorum and produced one winner. ForkRoom checks again for unresolved
blocking objections immediately before locking so a concern raised after voting
opened cannot be skipped.

The lock stores a canonical JSON snapshot containing the decision metadata,
winning proposal content, aggregate vote outcome, losing alternatives, and
objection records. Individual ballots and voter identities are not copied into
the snapshot. A SHA-256 document hash makes later snapshot changes detectable
through the verification endpoint.

The lock row, winner, and voting session are protected by foreign keys, while
unique constraints enforce one lock per decision and prevent the same voting
session from approving multiple decisions. Creating the lock atomically moves
the decision to the terminal `locked` state. Future corrections will create an
explicit revision rather than overwrite this approved record.

Owned implementation actions and scheduled reviews extend this immutable lock
history without changing the approved snapshot.

## Implementation action workflow

Owners and admins can add implementation actions only after a decision has been
locked. Every action has one eligible assignee from the workspace; viewers
cannot be assigned implementation work. Actions begin as `todo`.

```text
todo <-> in_progress <-> blocked
  \          |           /
   +---------+-----------> completed
   +---------+-----------> cancelled
```

The assignee, owner, or admin can move an action among active states or finish
it. Completed and cancelled actions are terminal and remain attached to the
locked decision as implementation history. Only owners and admins can edit the
action title, description, assignee, or due date.

## Scheduled review workflow

Owners and admins can schedule a future review for a locked decision. A partial
unique index permits only one currently scheduled review for a decision, while
cancelled records remain available as history. The scheduled date and notes can
be updated until the review is cancelled.

Review reminders are discovered by Celery Beat and delivered by the durable
notification workflow described below.

When the scheduled time arrives, an owner or admin completes the review with
one of three outcomes:

- `confirmed` keeps the existing locked decision and records why it remains valid
- `reopened` creates a new draft revision copied from the locked predecessor
- `superseded` creates a replacement draft with explicitly supplied metadata

The original decision and lock are never edited. Reopened and superseded
reviews atomically create a new decision plus an immutable revision link that
stores the root decision, predecessor, successor, source lock, review,
revision number, author, outcome, and rationale. Unique constraints prevent
duplicate successors, duplicate revision numbers, and multiple revisions from
the same predecessor or review.

Revision history is available from both the original decision and any
successor in its chain:

```text
POST /api/v1/workspaces/{workspace_id}/decisions/{decision_id}/reviews/{review_id}/outcome
GET  /api/v1/workspaces/{workspace_id}/decisions/{decision_id}/revisions
GET  /api/v1/workspaces/{workspace_id}/decisions/{decision_id}/revisions/{revision_id}
```

## Collaborative editor backend

ForkRoom keeps the collaboration service in this backend repository while
preserving clear service ownership:

- FastAPI validates workspace, decision, proposal and user permissions.
- `POST .../proposals/{proposal_id}/collaboration-token` creates a five-minute,
  document-scoped JWT for the browser's Hocuspocus provider.
- Owners, admins and members receive write access only while the decision and
  proposal are mutable. Viewers and submitted/locked content are read-only.
- Hocuspocus validates issuer, audience, expiry, document name and WebSocket
  origin before accepting a connection.
- Yjs document state is stored as binary data in PostgreSQL and versioned on
  every persisted snapshot.
- Redis synchronizes Yjs rooms across Hocuspocus replicas and holds expiring
  connection-presence records. Presence is never treated as durable history.

Run the collaboration service locally:

```bash
cd collaboration
npm install
npm run typecheck
npm test
npm run build
```

Or start PostgreSQL, Redis, Mailpit and the collaboration service together:

```bash
docker compose up -d --build
```

The frontend first requests a collaboration token from FastAPI, then connects
its Hocuspocus provider to `COLLABORATION_URL` using the returned
`document_name` and token. The collaboration secret must match in the FastAPI
and TypeScript service environments.

Apply the collaboration migration before starting Hocuspocus:

```bash
uv run alembic upgrade head
uv run alembic current
```

## Async notification platform

Celery Beat runs three periodic jobs. Every minute it discovers work due within
the configured reminder window. Every five minutes it recovers delivery leases
left behind by interrupted notification workers and republishes attachment
processing records that still need work. Reminder discovery covers:

- active implementation actions assigned to a participant
- scheduled decision reviews for owners and admins
- active decision deadlines for participating members
- open voting sessions for their snapshotted eligible voters

Each reminder is first inserted into PostgreSQL with a unique idempotency key.
Only a newly inserted row is published to RabbitMQ, so repeating Beat scans do
not create duplicate notifications. RabbitMQ is transport only; the database
retains the notification, attempt count, next attempt time, final result,
failure reason, and read state.

Temporary email failures use exponential backoff. A worker claims a delivery
with a database lease before sending, preventing two workers from sending the
same attempt. Exhausted jobs are marked `failed` and rejected into
`notifications.failed` through RabbitMQ's dead-letter exchange.

Notification API operations:

```text
GET  /api/v1/notifications
GET  /api/v1/notifications/unread-count
GET  /api/v1/notifications/{notification_id}
POST /api/v1/notifications/{notification_id}/read
POST /api/v1/notifications/read-all
```

## Attachment workflow

The browser never sends large attachment bodies through FastAPI. It first asks
FastAPI for a short-lived upload URL, uploads directly to MinIO, and then tells
FastAPI that the upload is complete:

```text
POST /api/v1/workspaces/{workspace_id}/attachments/uploads
PUT  {upload_url}
POST /api/v1/workspaces/{workspace_id}/attachments/{attachment_id}/complete
```

The completion call changes the durable PostgreSQL record from `pending` to
`processing` and publishes `forkroom.attachments.process` to the
`files.process` RabbitMQ queue. A Celery worker checks the object size, rejects
objects above the configured limit or with a size mismatch, computes SHA-256,
and marks the attachment `available`. Exhausted jobs are recorded as `rejected`
and routed to `files.failed`.

Workspace members can list metadata and request a download URL only for an
available object:

```text
GET    /api/v1/workspaces/{workspace_id}/attachments
GET    /api/v1/workspaces/{workspace_id}/attachments/{attachment_id}
POST   /api/v1/workspaces/{workspace_id}/attachments/{attachment_id}/download
DELETE /api/v1/workspaces/{workspace_id}/attachments/{attachment_id}
```

Use `decision_id` and `proposal_id` query parameters to filter evidence.
`proposal_id` always requires its parent `decision_id`. The upload creator can
delete their own file; owners and admins can remove any workspace attachment.
Viewers can list and download but cannot upload.

Start the complete local stack:

```bash
docker compose up -d --build
```

Apply the latest migration before starting workers:

```bash
uv run alembic upgrade head
uv run alembic current
```

The expected Alembic head is `c5e7a9b3d6f8`.
