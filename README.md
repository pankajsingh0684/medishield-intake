# MediShield Intake

MediShield's multi-agent document intake project. The repository contains shared
typed contracts, the deterministic decision engine, PostgreSQL schema and
repositories, and the Step 6 ingestion API. The worker, agents, and web application
are still in progress.

## Current progress

- Steps 1–6 are implemented and validated.
- PostgreSQL 16, Redis, locally built MinIO, and Qdrant run through Docker Compose.
- Redis is published on `localhost:6380` because `localhost:6379` is already in use
  on the development machine.
- The decision engine has 100% measured coverage.

## Development checks

```bash
uv sync
uv run pytest
uv run ruff check .
uv run pytest packages/tests/test_decision.py --cov=packages.decision --cov-report=term-missing --cov-fail-under=100
```

## Local setup

Copy `.env.example` to `.env` and replace each `replace-with-` value with a local
secret. Keep `.env` untracked. `LLM_PROVIDER=stub` works offline and needs no model
API keys. The MinIO image is compiled locally from a pinned upstream source release,
so its first Compose startup takes longer.

```bash
cp .env.example .env
docker compose --env-file .env -f infra/docker-compose.yml up -d --wait
bash scripts/init_local.sh
uv run alembic upgrade head
uv run python scripts/seed.py
```

The initializer is safe to rerun. It creates `medishield_test`, authenticates to
Redis, creates `medishield-documents` and `medishield-documents-test` if missing,
and creates the `policy_chunks` Qdrant collection if needed. Redis and Qdrant use
credentials from `.env`; all service ports are bound to `127.0.0.1`.

Open the services from the repository root:

```bash
docker compose --env-file .env -f infra/docker-compose.yml exec postgres psql -U <user> -d medishield
docker compose --env-file .env -f infra/docker-compose.yml exec redis redis-cli
AUTH <password>
```

For MinIO, open http://127.0.0.1:9001 and use the root user and password from
`.env`. For Qdrant, open http://127.0.0.1:6333/dashboard and provide the API key
from `.env`.

Database integration tests use `TEST_DATABASE_URL` and the separate
`medishield-documents-test` bucket. They fail with a configuration error rather than
skipping if the test database URL is missing. **The migration test drops and
recreates the `public` schema in `medishield_test`, so never point
`TEST_DATABASE_URL` at a database containing data you need.** It tests upgrades
from both an empty database and revision `762e1c97c741`.

```bash
uv run pytest
uv run ruff check .
```
