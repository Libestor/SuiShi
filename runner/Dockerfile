FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends util-linux \
    && groupadd --system --gid 10001 runner-builder \
    && useradd --system --uid 10001 --gid runner-builder --no-create-home runner-builder \
    && groupadd --system --gid 10002 runner-exec \
    && useradd --system --uid 10002 --gid runner-exec --no-create-home runner-exec \
    && mkdir -p /runner-cache/envs /runner-cache/staging \
    && chmod 0755 /runner-cache /runner-cache/envs /runner-cache/staging \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev
COPY app ./app

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
EXPOSE 9000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "9000"]
