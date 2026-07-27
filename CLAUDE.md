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
- `cogs/data_sync.py` (`DataSyncCog`) — owns *state* synchronization (users, guilds, roles, user_roles). Runs a full catch-up sweep on `on_ready` and reacts to guild/member/role lifecycle events at runtime. Do not duplicate this work in other cogs. `_sync_user_roles` clears before re-inserting, but the clear is **guild-scoped** (`clear_user_roles(user_id, guild_id)`) — a user on several of the bot's guilds must not lose guild B's roles when guild A re-syncs. The startup sweep rebuilds `user_roles` for every guild, so gaps self-heal on the next boot.
- `cogs/message_events.py` — message create/edit logging. Edits are stored as **new rows** with `is_edited=True`, not as updates. The cog does **not** filter bot authors anymore — every message (including the bot's own and other bots') is written with an `is_bot` flag, and dedup against the live log is handled by `messages.discord_id UNIQUE` + `ON CONFLICT DO NOTHING`.
- `cogs/voice_events.py` — voice session tracking. Sessions are held **in memory** in `self.voice_start_times` keyed by `(user_id, guild_id)`; a bot restart loses any open sessions. AFK channel moves are treated as session-end. Bots are no longer skipped, so music/utility bots will accumulate sessions — filter on read (`WHERE is_bot = FALSE`) if you don't want them.
- `cogs/general_events.py` — moderation/system events (reactions, bans/unbans, timeouts, channel/role lifecycle, message deletes) written to the `events` table via `_log_event`. Also unfiltered for bots; same `is_bot` column applies.
- `cogs/history_backfill.py` (`HistoryBackfillCog`) — admin-only slash command `/backfill_history` that walks every readable text channel and thread via `channel.history(limit=None)` and inserts past messages + a capped sample of reactions. All DB writes go through `asyncio.to_thread` so the Discord event loop keeps responding (heartbeat won't drop). Messages already present (matched by `discord_id`) are skipped, so the command is **idempotent**. Reactions are hard-capped per message via `MAX_REACTIONS_PER_MESSAGE` to avoid pathological pagination/rate-limit blowups. Archived threads are not walked. Progress (% of channels done, current channel, running totals) is reported by editing a single **ephemeral** followup message every `PROGRESS_EDIT_INTERVAL_S` seconds; edit failures (Discord rate-limit or expired interaction token) are logged but don't abort the backfill.
- `cogs/shutdown.py` (`ShutdownCog`) — `/off` closes the client. Note the container runs with `--restart unless-stopped`, so in practice this restarts the bot.
- `cogs/command_log.py` (`CommandLogCog`) — audit log of every slash command invocation (who/what/when/args) into `events` (`what='command'`), via the client's global `application_command_before_invoke` hook — new commands are covered automatically. Attempts rejected by a check are logged as `what='command denied'` from `on_application_command_error`. Audit entries ignore blacklists on purpose.
- `cogs/logs.py` (`LogsCog`) — admin-only `/logi [typ] [limit]` showing the newest entries (events / messages / voice / command audit) for the guild; always ephemeral. Reads via `get_recent_*` helpers in `Database`, dispatched through `asyncio.to_thread`.
- `cogs/module_control.py` (`ModuleControlCog`) — admin-only `/moduly status|wylacz|wlacz` toggling individual features per guild. The registry of toggleable modules lives in this file's `MODULES` dict; keys must match the `database.is_module_enabled(guild_id, key)` calls in the gated cogs (`gif_react`, `mention_webhook`, `message_log`, `voice_log`, `event_log`, `speak_up`, `summarize`, `profile`). State persists in `module_states` (a row = disabled; default enabled) with an in-memory cache like the blacklists. `data_sync` and `command_log` are deliberately not toggleable. When adding a new toggleable feature: add the key to `MODULES` and gate the feature's entry point with `is_module_enabled`.

### Multi-guild invariants
Fryderyk runs as a single process serving **several guilds**, so anything scoped to "the server" must carry a `guild_id`:
- **In-memory state must be keyed by guild.** `RandomReactionCog.reaction_probs` is a `guild_id -> DynamicProbability` dict (a shared instance would let one busy guild consume every other guild's daily GIF budget, and `/gif_szansa` would report a stranger's state); `VoiceEventsCog.voice_start_times` is keyed by `(user_id, guild_id)`. Never hang per-server counters off `self` directly.
- **Deletes must be scoped.** Rows in `user_roles` are shared across guilds via `roles.guild_id`; `clear_user_roles` takes an optional `guild_id` and callers should always pass it.
- **Globally-keyed tables need filtering on read.** `user_profiles` is one row per user with no guild column, so `/wizytowki_lista` filters `get_all_user_profiles()` through `guild.get_member(...)` — unfiltered, it would list members of other servers.
- **Known, accepted footguns:** `/off` kills the process for every guild; a newly joined guild starts with all modules enabled and empty blacklists; all n8n webhooks are shared across guilds and only distinguish servers by the `guild_id` field in the payload.

### Slash command access control
**Every slash command requires the operator role.** The role is matched **by name, not by ID** — the bot lives on several guilds, and a hardcoded snowflake only ever matched one of them. A global `client.application_command_check` in `main.py` delegates to `baseUtils.is_operator(interaction)`, which compares every one of the author's roles against `OPERATOR_ROLE_NAME` (env var, default `fryderyk-operator`) through `baseUtils.normalize_role_name` — lowercase, alphanumerics only, so `fryderyk-operator` / `Fryderyk Operator` / `Fryderyk_Operator` are all accepted. Each guild just needs a role with that name; no per-guild config. Check failures are answered with an ephemeral message by the `on_application_command_error` handler in `main.py`. `/off` additionally carries an explicit `application_checks.check(is_operator)` (not `has_role`, which is exact-name/ID only). When adding a new command, remember it is gated by this global check automatically.

### Database layer
`utilities/Database.py` is the single access point to PostgreSQL.
- On construction it (a) connects to the `postgres` admin DB and `CREATE DATABASE` the target if missing, then (b) opens a `SimpleConnectionPool` (1–20), then (c) calls `_create_tables()` which idempotently runs `CREATE TABLE IF NOT EXISTS` for the full schema. Schema changes belong in `_create_tables`; there are no migrations.
- Idempotent in-place migrations also live at the bottom of `_create_tables` — `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` for new columns (`messages.discord_id`, `*.is_bot`) and a `DO $$ ... $$` block that promotes legacy `TIMESTAMP` columns to `TIMESTAMPTZ` interpreting the bare values as local time in the server's current `TimeZone` GUC. Always add new schema changes here so existing databases pick them up on next start.
- All query helpers (`execute_query`, `fetch_one`, `fetch_all`) borrow a connection from the pool, commit/rollback, and return it. Always use these helpers rather than touching `psycopg2` directly so the pool isn't leaked.
- Domain helpers are grouped by table: `put_*` / `get_*` / `delete_*`. `put_*` uses `ON CONFLICT … DO UPDATE` for upserts on the entity tables, `ON CONFLICT (discord_id) DO NOTHING` for `messages` (the dedup key for the live + backfill paths), and plain `INSERT` for the append-only `voice` / `events` tables. `message_exists(discord_id)` is provided for the backfill path so it can skip already-logged messages cheaply.
- **Blacklists are cached in memory.** Both blacklist tables are loaded into sets on startup (`_load_blacklist_caches`) and `is_blacklisted` / `is_gif_blacklisted` are pure set lookups — safe to call from event handlers without blocking. `put_*`/`delete_*` blacklist helpers keep the caches in sync; if you ever write to those tables another way, refresh the cache too. `is_context_blacklisted(guild_id, channel_id, member, gif=)` is the combined channel+roles check used by all event cogs.
- `DataSyncCog` helpers are synchronous and every listener dispatches them via `asyncio.to_thread`; the startup catch-up runs once per process (guarded flag — `on_ready` re-fires on reconnects).

### Timezone convention
All time columns are `TIMESTAMPTZ`, so PostgreSQL handles strefę natively — what you send is normalized to UTC for storage and rendered in the reader's session timezone on the way out. Convention in cogs: store `self.tz = ZoneInfo(config.get_timezone())` (or a hardcoded `ZoneInfo("Europe/Warsaw")` for the legacy cogs) and convert UTC timestamps with `.astimezone(self.tz)` (or `datetime.now(self.tz)`) before insertion. Do not write naive datetimes — `TIMESTAMPTZ` will assume the server's session timezone, which is brittle.

### Discord intents
`main.py` enables `message_content` and `members` on top of the defaults. New event handlers that need privileged data must verify the intent is enabled here and in the Discord Developer Portal.

## Configuration

Environment variables (loaded via `python-dotenv` in `ConfigReader`):
- `BOT_TOKEN`, `POSTGRES_HOST`, `POSTGRES_PORT`, `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` — Discord/PG credentials.
- `TIMEZONE` (optional, default `Europe/Warsaw`) — IANA tz name returned by `ConfigReader.get_timezone()`. Only `HistoryBackfillCog` reads it right now; the other cogs hardcode `Europe/Warsaw` and should be migrated through `config.get_timezone()` if you ever need to change zones.
- `OPERATOR_ROLE_NAME` (optional, default `fryderyk-operator`) — **name** of the role required to use any slash command; read by `baseUtils.get_operator_role_name()` and matched case/separator-insensitively. Replaces the old `OPERATOR_ROLE_ID`, which is no longer read.
- n8n webhook URLs come from `ConfigReader.get_n8n_url(feature, env)` where feature is one of `summarize`/`profile`/`speak`/`mention` and env is `production`/`test`. Env var names: `N8N_WEBHOOK_*`, `N8N_PROFILE_WEBHOOK_*`, `N8N_SPEAK_WEBHOOK_*`, `N8N_MENTION_WEBHOOK_*` (`*` = `PRODUCTION_URL`/`TEST_URL`). `N8N_MENTION_ENVS` (comma-separated, default `production`) controls which environments the mention webhook fires to.
- In the webhook slash commands the `env` option is optional (default `production`); choosing `test` requires guild admin permissions.

Defaults in `ConfigReader.get_db_config` are for local-only use; production reads everything from `.env`.
