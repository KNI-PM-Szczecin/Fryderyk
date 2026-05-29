# Fryderyk - Discord Logging Bot

Fryderyk is an advanced Discord logging bot written in Python using the `nextcord` library. The bot monitors messages, voice activity, and system events, storing them in an external PostgreSQL database with full support for the Polish timezone.

## Features

- **Message Logging**: Records message content, edits, authors, and channels (table `messages`). Each row carries the Discord message ID (`discord_id`) and an `is_bot` flag, so re-running ingestion is idempotent and bot vs human traffic can be filtered after the fact.
- **Voice Logging**: Tracks time spent in voice channels, join moments, and session durations (table `voice`). Includes an `is_bot` flag.
- **Event Logging**: Records reactions, bans, timeouts, channel/role changes, and user joins (table `events`). Includes an `is_bot` flag.
- **Data Synchronization**: Automatically updates information about users, guilds, and roles (tables `users`, `guilds`, `roles`, `user_roles`).
- **History Backfill**: Admin-only slash command `/backfill_history` walks every readable text channel and thread and inserts past messages (and a capped sample of reactions) into the DB. Messages already present are skipped via `discord_id`, so the command is safe to re-run.
- **Full Timezone Support**: All time columns are `TIMESTAMPTZ`; values are produced in the configured timezone (`TIMEZONE` env var, default `Europe/Warsaw`) and PostgreSQL handles conversion natively.

## Requirements

- Python 3.10+
- External PostgreSQL Database
- Libraries listed in `requirements.txt`

## Configuration (Environment Variables)

The bot is configured via a `.env` file. Below is a list of available flags:

| Variable | Description |
| :--- | :--- |
| `BOT_TOKEN` | Your Discord bot token. |
| `POSTGRES_HOST` | External database host (IP address or hostname). |
| `POSTGRES_PORT` | PostgreSQL port (default `5432`). |
| `POSTGRES_USER` | Database user. |
| `POSTGRES_PASSWORD`| Database password. |
| `POSTGRES_DB` | Database name. |
| `TIMEZONE` | Optional. IANA timezone name used by the backfill cog (default `Europe/Warsaw`). |

## Running the Bot

> **Network requirement:** The bot attaches to the external Docker network `n8n-net` so it can reach other services (e.g. the PostgreSQL container) on the same shared network. Create it once before the first run if it does not already exist:
> ```bash
> docker network create n8n-net
> ```

### 1. Single Container (Recommended for clean Docker Desktop view)
To avoid project grouping in Docker Desktop and have the bot appear as a single item named `Fryderyk`, use this method:

**Build the image:**
```bash
docker build -t fryderyk-bot:0.1.0 .
```

**Run the container:**
```bash
docker run -d \
  --name Fryderyk \
  --env-file .env \
  --add-host=host.docker.internal:host-gateway \
  --network n8n-net \
  --restart unless-stopped \
  fryderyk-bot:0.1.0
```

### 2. Docker Compose (Alternative)
If you prefer using Docker Compose, run:
```bash
docker compose up -d
```
*Note: This will create a grouped project view in Docker Desktop. The compose file declares `n8n-net` as an external network, so make sure it exists (see the network requirement above) before bringing the stack up.*


## Database Structure

The bot automatically creates the required tables in the connected database on the first run. The main log sources are:
- `messages`: Chat history.
- `voice`: Voice statistics.
- `events`: Moderation and system logs.
