# A menos que isso que algum serviço precise, mude apenas os caminhos relativos ao serviço

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=services/users/pyproject.toml,target=services/users/pyproject.toml \
    --mount=type=bind,source=libs/python/common/pyproject.toml,target=libs/python/common/pyproject.toml \
    uv sync --frozen --no-dev --no-install-workspace --package users-service

COPY pyproject.toml uv.lock ./
COPY libs/python/common libs/python/common
COPY services/users services/users
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --no-editable --package users-service

FROM python:3.12-slim AS runtime

RUN useradd --system --uid 1001 --no-create-home app
WORKDIR /app

COPY --from=builder --chown=app:app /app/.venv /app/.venv
COPY --chown=app:app services/users/alembic.ini ./alembic.ini
COPY --chown=app:app services/users/migrations ./migrations

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app
EXPOSE 8000

HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health/live')"

CMD ["uvicorn", "users_service.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000"]
