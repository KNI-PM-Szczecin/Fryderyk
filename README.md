# Fryderyk - Discord Logging Bot

Fryderyk is an advanced Discord logging bot written in Python using the `nextcord` library. The bot monitors messages, voice activity, and system events, storing them in an external PostgreSQL database with full support for the Polish timezone.

## Features

- **Message Logging**: Records message content, edits, authors, and channels (table `messages`).
- **Voice Logging**: Tracks time spent in voice channels, join moments, and session durations (table `voice`).
- **Event Logging**: Records reactions, bans, timeouts, channel/role changes, and user joins (table `events`).
- **Data Synchronization**: Automatically updates information about users, guilds, and roles (tables `users`, `guilds`, `roles`, `user_roles`).
- **Full Timezone Support**: All logs are saved using the `Europe/Warsaw` timezone.

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

## Running the Bot

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
  --restart unless-stopped \
  fryderyk-bot:0.1.0
```

### 2. Docker Compose (Alternative)
If you prefer using Docker Compose, run:
```bash
docker compose up -d
```
*Note: This will create a grouped project view in Docker Desktop.*


## Database Structure

The bot automatically creates the required tables in the connected database on the first run. The main log sources are:
- `messages`: Chat history.
- `voice`: Voice statistics.
- `events`: Moderation and system logs.
