# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

Fryderyk is a Discord logging bot built on `nextcord` that persists messages, voice sessions, and moderation/system events to an external PostgreSQL database. All timestamps are stored in the `Europe/Warsaw` timezone.

## Before you start: check the current nextcord release

**Always research the latest `nextcord` version on the web before working on anything that touches the library** — slash/application commands, intents, UI (modals/views), event listeners, or the pinned version itself. `nextcord` evolves fast and ships breaking changes between majors, and your training data may be stale. Do this even for "small" changes.

1. Web-search the current `nextcord` version and read its release notes / changelog (PyPI, `github.com/nextcord/nextcord/releases`, `docs.nextcord.dev/en/stable/whats_new.html`) before proposing or writing code.
2. Cross-check what version this repo actually pins (`requirements.txt`) and what Python the image runs (`Dockerfile`). They must stay compatible — e.g. **nextcord ≥3.0 requires Python ≥3.12**. The current pin is `nextcord==3.2.0` on `python:3.12`. **Keep `nextcord` pinned**; an unpinned requirement makes every rebuild non-deterministic.
3. Note any API that only exists in a given major before using it — e.g. `nextcord.InteractionContextType` / `contexts=` / `integration_types=` are 3.x-only. Using a newer API while the running version is older makes the whole cog fail to load silently (the `Loader` swallows the exception), so the command never registers.
4. Never "update nextcord at runtime" (e.g. a slash command that runs `pip install`). Bump the version in `requirements.txt` + the base image and let the image rebuild/redeploy handle it.

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
- `cogs/message_events.py` — message create/edit logging. Edits are stored as **new rows** with `is_edited=True`, not as updates. The cog does **not** filter bot authors anymore — every message (including the bot's own and other bots') is written with an `is_bot` flag, and dedup against the live log is handled by `messages.discord_id UNIQUE` + `ON CONFLICT DO NOTHING`.
- `cogs/voice_events.py` — voice session tracking. Sessions are held **in memory** in `self.voice_start_times` keyed by `(user_id, guild_id)`; a bot restart loses any open sessions. AFK channel moves are treated as session-end. Bots are no longer skipped, so music/utility bots will accumulate sessions — filter on read (`WHERE is_bot = FALSE`) if you don't want them.
- `cogs/general_events.py` — moderation/system events (reactions, bans/unbans, timeouts, channel/role lifecycle, message deletes) written to the `events` table via `_log_event`. Also unfiltered for bots; same `is_bot` column applies.
- `cogs/history_backfill.py` (`HistoryBackfillCog`) — admin-only slash command `/backfill_history` that walks every readable text channel and thread via `channel.history(limit=None)` and inserts past messages + a capped sample of reactions. All DB writes go through `asyncio.to_thread` so the Discord event loop keeps responding (heartbeat won't drop). Messages already present (matched by `discord_id`) are skipped, so the command is **idempotent**. Reactions are hard-capped per message via `MAX_REACTIONS_PER_MESSAGE` to avoid pathological pagination/rate-limit blowups. Archived threads are not walked. Progress (% of channels done, current channel, running totals) is reported by editing a single **ephemeral** followup message every `PROGRESS_EDIT_INTERVAL_S` seconds; edit failures (Discord rate-limit or expired interaction token) are logged but don't abort the backfill.
- `cogs/user_events.py` — placeholder; user sync logic lives in `DataSyncCog`.

### Database layer
`utilities/Database.py` is the single access point to PostgreSQL.
- On construction it (a) connects to the `postgres` admin DB and `CREATE DATABASE` the target if missing, then (b) opens a `SimpleConnectionPool` (1–20), then (c) calls `_create_tables()` which idempotently runs `CREATE TABLE IF NOT EXISTS` for the full schema. Schema changes belong in `_create_tables`; there are no migrations.
- Idempotent in-place migrations also live at the bottom of `_create_tables` — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for new columns (`messages.discord_id`, `*.is_bot`) and a `DO $$ ... $$` block that promotes legacy `TIMESTAMP` columns to `TIMESTAMPTZ` interpreting the bare values as local time in the server's current `TimeZone` GUC. Always add new schema changes here so existing databases pick them up on next start.
- All query helpers (`execute_query`, `fetch_one`, `fetch_all`) borrow a connection from the pool, commit/rollback, and return it. Always use these helpers rather than touching `psycopg2` directly so the pool isn't leaked.
- Domain helpers are grouped by table: `put_*` / `get_*` / `delete_*`. `put_*` uses `ON CONFLICT … DO UPDATE` for upserts on the entity tables, `ON CONFLICT (discord_id) DO NOTHING` for `messages` (the dedup key for the live + backfill paths), and plain `INSERT` for the append-only `voice` / `events` tables. `message_exists(discord_id)` is provided for the backfill path so it can skip already-logged messages cheaply.

### Timezone convention
All time columns are `TIMESTAMPTZ`, so PostgreSQL handles strefę natively — what you send is normalized to UTC for storage and rendered in the reader's session timezone on the way out. Convention in cogs: store `self.tz = ZoneInfo(config.get_timezone())` (or a hardcoded `ZoneInfo("Europe/Warsaw")` for the legacy cogs) and convert UTC timestamps with `.astimezone(self.tz)` (or `datetime.now(self.tz)`) before insertion. Do not write naive datetimes — `TIMESTAMPTZ` will assume the server's session timezone, which is brittle.

### Discord intents
`main.py` enables `message_content` and `members` on top of the defaults. New event handlers that need privileged data must verify the intent is enabled here and in the Discord Developer Portal.

## Configuration

Environment variables (loaded via `python-dotenv` in `ConfigReader`):
- `BOT_TOKEN`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — Discord/PG credentials.
- `TIMEZONE` (optional, default `Europe/Warsaw`) — IANA tz name returned by `ConfigReader.get_timezone()`. Only `HistoryBackfillCog` reads it right now; the other cogs hardcode `Europe/Warsaw` and should be migrated through `config.get_timezone()` if you ever need to change zones.

Defaults in `ConfigReader.get_db_config` are for local-only use; production reads everything from `.env`.
