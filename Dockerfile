# One image for the API, the worker and migrations; compose picks the command.
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy PYTHONUNBUFFERED=1

# dependencies first so code edits don't reinstall them
COPY pyproject.toml uv.lock ./
COPY packages/geoapps-core/pyproject.toml packages/geoapps-core/
COPY packages/geoapps-db/pyproject.toml packages/geoapps-db/
COPY packages/geoapps-api/pyproject.toml packages/geoapps-api/
COPY packages/geoapps-workers/pyproject.toml packages/geoapps-workers/
RUN uv sync --frozen --no-dev --no-install-workspace

COPY packages ./packages
RUN uv sync --frozen --no-dev

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000
CMD ["geoapps-api"]
