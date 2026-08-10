FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.8.3 /uv /uvx /bin/

FROM base AS dependencies

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

FROM base AS runtime

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        fonts-dejavu-core \
        libffi8 \
        libgdk-pixbuf-2.0-0 \
        libharfbuzz-subset0 \
        libharfbuzz0b \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
        shared-mime-info \
        tini \
    && rm -rf /var/lib/apt/lists/*

RUN addgroup --system forkroom && adduser --system --ingroup forkroom forkroom

COPY --from=dependencies --chown=forkroom:forkroom /app/.venv /app/.venv
COPY --chown=forkroom:forkroom alembic ./alembic
COPY --chown=forkroom:forkroom alembic.ini pyproject.toml ./
COPY --chown=forkroom:forkroom app ./app

ENV PATH="/app/.venv/bin:$PATH"

USER forkroom
EXPOSE 8000

ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
