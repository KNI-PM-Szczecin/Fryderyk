# Repository Guidelines

## Before You Start: Check the Current `nextcord` Release
**Always research the latest `nextcord` version on the web before touching anything
that uses the library** — slash/application commands, intents, UI (modals/views),
event listeners, or the pinned version itself. `nextcord` moves fast and ships
breaking changes between majors, so do not rely on memory or training data.

- Web-search the current `nextcord` version and read its changelog before writing
  code (PyPI, `github.com/nextcord/nextcord/releases`,
  `docs.nextcord.dev/en/stable/whats_new.html`).
- Keep `requirements.txt` (`nextcord==3.2.0`) and the `Dockerfile` Python version
  (`python:3.12`) compatible: **nextcord ≥3.0 requires Python ≥3.12**. Always keep
  `nextcord` pinned — an unpinned requirement makes rebuilds non-deterministic.
- Some APIs are version-gated (`nextcord.InteractionContextType`, `contexts=`,
  `integration_types=` are 3.x-only). Using a newer API on an older runtime makes
  the cog fail to load silently, so the command never registers.
- Never update `nextcord` at runtime (e.g. a command that runs `pip install`); bump
  the version in `requirements.txt` + the base image and redeploy instead.

## Project Structure & Module Organization
Fryderyk is a Python Discord logging bot built with `nextcord` and PostgreSQL.
Core startup logic lives in `main.py`. Feature modules are cogs in `cogs/`, such
as `message_events.py`, `history_backfill.py`, and `log_blacklist.py`.
Shared helpers live in `utilities/`: `Database.py` owns PostgreSQL access and
schema creation, while `baseUtils.py` handles config loading and cog discovery.
Deployment files are at the repository root: `Dockerfile`, `docker-compose.yml`,
`requirements.txt`, and `README.md`. There is currently no dedicated `tests/`
directory.

## Build, Test, and Development Commands
Create a local environment and install dependencies:
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Run locally with a populated `.env`:
```bash
python main.py
```
Build and run the Docker image:
```bash
docker build -t fryderyk-bot:0.1.0 .
docker compose up -d
```
The compose setup expects the external Docker network `n8n-net`; create it once
with `docker network create n8n-net` if needed.

## Coding Style & Naming Conventions
Use Python 3.12+ and follow existing PEP 8-style formatting: 4-space
indentation, snake_case functions and variables, and PascalCase classes. Cog
files use snake_case names and must export a matching class for the loader:
`foo_bar.py` should provide `FooBarCog` or `FooBar`. Prefer cog constructors of
`__init__(self, client, config, database)` unless `main.py` is updated to pass
additional dependencies.

## Testing Guidelines
No test framework is configured yet. For changes that can be tested without
Discord, add focused `pytest` tests under a new `tests/` directory and document
the command. For runtime changes, verify with `python main.py` or Docker against
a disposable PostgreSQL database and confirm slash commands or event listeners
behave as expected.

## Database & Configuration Notes
Keep all PostgreSQL access in `utilities/Database.py` and use its helper methods
instead of raw `psycopg2` calls. Schema changes belong in `_create_tables()` as
idempotent `CREATE TABLE IF NOT EXISTS` or `ALTER TABLE ... ADD COLUMN IF NOT
EXISTS` statements. Required configuration comes from `.env`: `BOT_TOKEN`,
`POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`,
`POSTGRES_DB`, and optional `TIMEZONE` (default `Europe/Warsaw`). Do not commit
secrets or generated caches such as `__pycache__/`.

## Commit & Pull Request Guidelines
Recent history mostly uses concise Conventional Commit prefixes, for example
`feat: add /version slash command` and `fix: register /version as guild-specific
command`. Keep commits scoped and imperative. Pull requests should describe the
behavior change, note database or environment impacts, include manual test
results, and attach screenshots or command output when Discord interactions are
user-visible.
