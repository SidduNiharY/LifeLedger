FROM python:3.14-slim
COPY --from=ghcr.io/astral-sh/uv:0.13 /uv /usr/local/bin/uv
ENV PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy PATH="/srv/.venv/bin:$PATH"
WORKDIR /srv
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./alembic.ini
USER 1000:1000
CMD ["uvicorn", "--factory", "app.api.main:app_factory", "--host", "0.0.0.0", "--port", "8000"]
