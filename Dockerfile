# Uber trips pipeline: Dagster (UI + scheduler) running dlt → dbt → Google Sheets. See docker-compose.yml.
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PATH=/app/.venv/bin:$PATH \
    DAGSTER_HOME=/opt/dagster \
    TZ=America/Sao_Paulo

WORKDIR /app

# Dependencies first, so code changes don't reinstall them.
COPY pyproject.toml uv.lock .python-version ./
RUN uv sync --frozen --no-dev --no-install-project

COPY . .
RUN uv sync --frozen --no-dev && mkdir -p /opt/dagster && touch /opt/dagster/dagster.yaml

EXPOSE 3002
CMD ["dagster", "dev", "-h", "0.0.0.0", "-p", "3002"]
