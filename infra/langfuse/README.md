# Self-Hosted Langfuse Setup

LifeLedger uses [Langfuse](https://langfuse.com/) for LLM observability, distributed tracing of transaction categorization, and tracking category accuracy feedback scores.

## Setup Instructions

### 1. Download Docker Compose Configuration

1. Download the official `docker-compose.yml` from the [Langfuse GitHub repository](https://github.com/langfuse/langfuse) (use a v3/v4 release tag) into `infra/langfuse/docker-compose.yml`.
2. Ensure the web port mapping is configured for local access:
   ```yaml
   ports:
     - "127.0.0.1:3000:3000"
   ```
3. Langfuse runs multiple containers (web, worker, Postgres, ClickHouse, Redis, MinIO). Ensure Docker Desktop has at least 4 GB of memory allocated.

### 2. Start Langfuse

Run the Compose project in detached mode:

```bash
docker compose -p langfuse -f infra/langfuse/docker-compose.yml up -d
```

### 3. Generate API Keys

1. Navigate to [http://127.0.0.1:3000](http://127.0.0.1:3000) in your browser.
2. Sign up and create an organization and project (e.g. `LifeLedger`).
3. Under Project Settings -> API Keys, create a new API key pair.
4. Copy the keys to your LifeLedger `.env` file:
   ```env
   LANGFUSE_PUBLIC_KEY=pk-lf-...
   LANGFUSE_SECRET_KEY=sk-lf-...
   LANGFUSE_HOST=http://host.docker.internal:3000
   ```

### 4. Restart LifeLedger Services

Restart LifeLedger containers so the new environment variables take effect:

```bash
docker compose up -d
```

## How It Works in LifeLedger

- **Tracing**: Whenever a transaction is processed by the model ladder (`app/ledger/categorise.py`), a `categorise_transaction` span is created under tracer `lifeledger` and exported to Langfuse.
- **Feedback Scores**: When you tap a category button in Telegram (`/review` or `/fix`), LifeLedger compares the chosen category against the model's prior guess/suggestion. It records a `category_correct` score (`1.0` if matching, `0.0` if overridden) associated with the trace ID.
