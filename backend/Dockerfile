# SignalOps AI Production Dockerfile
FROM python:3.11-slim as base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=8000

WORKDIR /app

# Install build tools for native CFFI / psycopg extensions if needed
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Source first, then install. An editable install has to be able to find the
# `app` package at install time — with only pyproject.toml present, setuptools
# discovers nothing and the import fails at runtime instead of at build.
COPY . .

# `.[ai]` was removed: pydantic-ai-slim[google] is a plain dependency now, and
# pip warned-and-skipped the non-existent extra rather than failing loudly.
RUN pip install --upgrade pip && pip install -e .

EXPOSE 8000

# Run migrations automatically before booting API server
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
