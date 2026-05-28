# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Fryderyk is a Discord logging bot built on `nextcord` that persists messages, voice sessions, and moderation/system events to an external PostgreSQL database. All timestamps are stored in the `Europe/Warsaw` timezone.

## Commands

Local run (requires a populated `.env`):
```bash
pip install -r requirements.txt
python main.py
```

Docker (single container, matches the deployment style in `README.md`):
```bash
docker build -t fryderyk-bot:0.1.0 .
docker run -d --name Fryderyk --env-file .env \
  --add-host=host.docker.internal:host-gateway \
  --restart unless-stopped fryderyk-bot:0.1.0
```

Docker Compose alternative: `docker compose up -d`.

There is no test suite, linter, or formatter configured in this repo.

## Architecture

### Cog auto-loader
`utilities/baseUtils.py` — `Loader` walks the `cogs/` folder at startup and instantiates one class per file using a strict naming convention:

- File `foo_bar.py` must export class `FooBarCog` (preferred) or `FooBar`.
- The loader inspects `__init__` parameters and resolves each by name from a `payload` dict built in `main.py`. The available keys are `client`, `config`, and `database`. A new cog needing additional dependencies must have them added to `payload` in `main.py`.
- Failed loads are printed but do not crash the bot.

When adding a new cog, follow the existing constructor signature `__init__(self, client, config, database)` and decorate handlers with `@commands.Cog.listener()`.

### Cog responsibilities
- `cogs/data_sync.py` (`DataSyncCog`) — owns *state* synchronization (users, guilds, roles, user_roles). Runs a full catch-up sweep on `on_ready` and reacts to guild/member/role lifecycle events at runtime. Do not duplicate this work in other cogs.
- `cogs/message_events.py` — message create/edit logging. Edits are stored as **new rows** with `is_edited=True`, not as updates.
- `cogs/voice_events.py` — voice session tracking. Sessions are held **in memory** in `self.voice_start_times` keyed by `(user_id, guild_id)`; a bot restart loses any open sessions. AFK channel moves are treated as session-end.
- `cogs/general_events.py` — moderation/system events (reactions, bans/unbans, timeouts, channel/role lifecycle, message deletes) written to the `events` table via `_log_event`.
- `cogs/user_events.py` — placeholder; user sync logic lives in `DataSyncCog`.

### Database layer
`utilities/Database.py` is the single access point to PostgreSQL.
- On construction it (a) connects to the `postgres` admin DB and `CREATE DATABASE` the target if missing, then (b) opens a `SimpleConnectionPool` (1–20), then (c) calls `_create_tables()` which idempotently runs `CREATE TABLE IF NOT EXISTS` for the full schema. Schema changes belong in `_create_tables`; there are no migrations.
- All query helpers (`execute_query`, `fetch_one`, `fetch_all`) borrow a connection from the pool, commit/rollback, and return it. Always use these helpers rather than touching `psycopg2` directly so the pool isn't leaked.
- Domain helpers are grouped by table: `put_*` / `get_*` / `delete_*`. `put_*` uses `ON CONFLICT … DO UPDATE` for upserts on the entity tables and plain `INSERT` for the append-only log tables (`messages`, `voice`, `events`).

### Timezone convention
Every cog stores `self.tz = ZoneInfo("Europe/Warsaw")` and converts UTC timestamps with `.astimezone(self.tz)` (or `datetime.now(self.tz)`) before insertion. Preserve this when adding new event handlers — do not write naive or UTC timestamps to the DB.

### Discord intents
`main.py` enables `message_content` and `members` on top of the defaults. New event handlers that need privileged data must verify the intent is enabled here and in the Discord Developer Portal.

## Configuration

Environment variables (loaded via `python-dotenv` in `ConfigReader`): `BOT_TOKEN`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB`. Defaults in `ConfigReader.get_db_config` are for local-only use; production reads everything from `.env`.
