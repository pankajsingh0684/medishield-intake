# MediShield Intake

MediShield's multi-agent document intake project. The current repository contains
the Python project skeleton, local infrastructure configuration, shared typed
contracts, deterministic decision engine, and PostgreSQL schema/repositories.
API, worker, agents, and the web application are not implemented yet.

## Current progress

- Steps 1–5 are implemented and validated; changes are not committed yet.
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

## Local infrastructure

Create `.env` from `.env.example`. The credentials and model IDs marked
`replace-with-` are local placeholders; replace them before using external services.
The MinIO image is compiled locally from a pinned upstream source release, so the
first Compose startup takes longer.

```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d
docker compose -f infra/docker-compose.yml ps
uv run alembic upgrade head
```

Set a local-only test-user password before seeding. On PowerShell:

```powershell
$env:SEED_TEST_USER_PASSWORD = "local-only-test-password"
uv run python scripts/seed.py
```

Database integration tests use the separate `medishield_test` database, created by
the Compose Postgres initialization script on a fresh volume. If the Postgres volume
already existed before that script was added, create the database once with:

```bash
docker compose -f infra/docker-compose.yml exec postgres createdb -U medishield medishield_test
```

Set `TEST_DATABASE_URL` in `.env` (the `.env.example` value targets this database).
Then `uv run pytest` runs the PostgreSQL tests; they fail with a configuration error
instead of skipping if the URL is missing. **The migration test drops and recreates
the `public` schema in `medishield_test`, so never point `TEST_DATABASE_URL` at a
database containing data you need.** It tests upgrades from both an empty database
and revision `762e1c97c741`.

The compose stack binds service ports to localhost. Endpoints are PostgreSQL
`localhost:5432`, Redis `localhost:6380`, MinIO `localhost:9000` (console
`localhost:9001`), and Qdrant `localhost:6333` (gRPC `localhost:6334`).

Install the MinIO Client (`mc`), load the `.env` values in a Bash-compatible shell,
then create and enable versioning for the configured bucket:

```bash
set -a
. ./.env
set +a
mc alias set medishield "$S3_ENDPOINT" "$S3_ACCESS_KEY" "$S3_SECRET_KEY"
mc mb --ignore-existing "medishield/$S3_BUCKET"
mc version enable "medishield/$S3_BUCKET"
```