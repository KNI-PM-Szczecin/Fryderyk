import asyncio
import os
import random
from datetime import datetime
from zoneinfo import ZoneInfo

import nextcord
from nextcord.ext import commands, tasks

# Presence is global for the bot account, so it is driven by one "home" guild.
HOME_GUILD_ID = int(os.getenv("PRESENCE_GUILD_ID", "1357420845970100335"))
ALEKSY_ID = 1517684419807285289

# Defaults seeded into presence_lines when the table is empty. Several rows of
# one kind form a pool picked at random. {n} = number, {channel} = channel name.
# kind 'setting' rows are "name=value" thresholds.
DEFAULT_LINES = [
    ("voice", "podsłuchuje voice ({n} os.)"),
    ("aleksy", "obraża się na tostera"),
    ("busy", "nie nadąża za #{channel} 😭"),
    ("read_today", "przeczytał już {n} wiadomości"),
    ("night", "śpi, nie budzić"),
    ("idle", "udaje, że pracuje"),
    ("idle", "liczy cytryny"),
    ("idle", "czeka, aż ktoś go zawoła"),
    ("idle", "ignoruje tostera"),
    ("idle", "czyta logi do poduszki"),
    ("setting", "busy_per_hour=40"),
    ("setting", "aleksy_minutes=10"),
    ("setting", "night_start=1"),
    ("setting", "night_end=8"),
]


class PresenceCog(commands.Cog):
    """
    Keeps the bot's custom status in sync with what is going on. Every ~2 min the
    first matching rule wins: an external state set by n8n (bot_state), people on
    voice, A.L.E.K.S.Y. talking recently, a busy channel, today's message count,
    night time (idle) and finally a random line from the pool. All DB reads run
    in a worker thread and every failure falls back to the next rule, so a
    database that is not ready yet never kills the loop.
    """

    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        self.tz = ZoneInfo("Europe/Warsaw")
        self._last = None
        self._seeded = False

    @commands.Cog.listener()
    async def on_ready(self):
        # Started here, not in __init__: cogs are built before the event loop runs.
        if not self.update_presence.is_running():
            self.update_presence.start()

    def cog_unload(self):
        self.update_presence.cancel()

    # --- DB helpers (blocking, run via asyncio.to_thread) ---

    def _seed_defaults(self):
        row = self.database.fetch_one("SELECT COUNT(*) FROM presence_lines")
        if row is None:
            return False
        if row[0] == 0:
            for kind, text in DEFAULT_LINES:
                self.database.execute_query(
                    "INSERT INTO presence_lines (kind, text) VALUES (%s, %s)", (kind, text)
                )
        return True

    def _load_lines(self):
        rows = self.database.fetch_all("SELECT kind, text FROM presence_lines WHERE enabled")
        lines, settings = {}, {}
        for kind, text in rows or []:
            if kind == "setting" and "=" in text:
                name, value = text.split("=", 1)
                settings[name.strip()] = value.strip()
            else:
                lines.setdefault(kind, []).append(text)
        for kind, text in DEFAULT_LINES:
            if kind == "setting":
                name, value = text.split("=", 1)
                settings.setdefault(name, value)
            elif kind not in lines:
                lines.setdefault(kind, []).append(text)
        return lines, settings

    def _read_stats(self, aleksy_minutes):
        state = self.database.fetch_one(
            "SELECT text FROM bot_state WHERE expires_at > now() ORDER BY updated_at DESC LIMIT 1"
        )
        aleksy = self.database.fetch_one(
            "SELECT 1 FROM messages WHERE guild_id = %s AND user_id = %s "
            "AND date > now() - %s * interval '1 minute' LIMIT 1",
            (HOME_GUILD_ID, ALEKSY_ID, aleksy_minutes),
        )
        busiest = self.database.fetch_one(
            "SELECT channel_name, COUNT(*) FROM messages WHERE guild_id = %s AND NOT is_bot "
            "AND date > now() - interval '1 hour' GROUP BY channel_name ORDER BY 2 DESC LIMIT 1",
            (HOME_GUILD_ID,),
        )
        today = self.database.fetch_one(
            "SELECT COUNT(*) FROM messages WHERE guild_id = %s AND NOT is_bot AND date >= CURRENT_DATE",
            (HOME_GUILD_ID,),
        )
        return {
            "state": state[0] if state else None,
            "aleksy": aleksy is not None,
            "busiest": busiest,
            "today": today[0] if today else 0,
        }

    # --- rule evaluation ---

    def _voice_count(self, guild):
        return sum(
            1
            for channel in guild.voice_channels
            for member in channel.members
            if not member.bot
        )

    @staticmethod
    def _pick(lines, kind, **fmt):
        pool = lines.get(kind) or []
        if not pool:
            return None
        try:
            return random.choice(pool).format(**fmt)
        except (KeyError, IndexError, ValueError):
            return random.choice(pool)

    @staticmethod
    def _int(settings, name, default):
        try:
            return int(settings.get(name, default))
        except (TypeError, ValueError):
            return default

    async def _decide(self):
        guild = self.client.get_guild(HOME_GUILD_ID)
        if guild is not None and not self.database.is_module_enabled(guild.id, "presence"):
            return nextcord.Status.online, None

        if not self._seeded:
            self._seeded = bool(await asyncio.to_thread(self._seed_defaults))
        lines, settings = await asyncio.to_thread(self._load_lines)
        try:
            stats = await asyncio.to_thread(self._read_stats, self._int(settings, "aleksy_minutes", 10))
        except Exception as e:
            print(f"[presence] stats failed: {e}")
            stats = {"state": None, "aleksy": False, "busiest": None, "today": 0}

        online = nextcord.Status.online
        if stats["state"]:
            return online, stats["state"]

        voice = self._voice_count(guild) if guild is not None else 0
        if voice:
            return online, self._pick(lines, "voice", n=voice)

        if stats["aleksy"]:
            return online, self._pick(lines, "aleksy")

        busiest = stats["busiest"]
        if busiest and busiest[1] >= self._int(settings, "busy_per_hour", 40):
            return online, self._pick(lines, "busy", channel=(busiest[0] or "").split("┃")[-1])

        hour = datetime.now(self.tz).hour
        night_start = self._int(settings, "night_start", 1)
        night_end = self._int(settings, "night_end", 8)
        is_night = (night_start <= hour < night_end) if night_start <= night_end else (hour >= night_start or hour < night_end)
        if is_night and (not busiest or busiest[1] < 5):
            return nextcord.Status.idle, self._pick(lines, "night")

        # daytime with nothing special: today's count or a random line, alternating
        if stats["today"] and random.random() < 0.5:
            return online, self._pick(lines, "read_today", n=stats["today"])
        return online, self._pick(lines, "idle")

    @tasks.loop(seconds=120)
    async def update_presence(self):
        try:
            status, text = await self._decide()
            text = (text or "")[:128] or None
            if (status, text) == self._last:
                return
            activity = nextcord.CustomActivity(name=text) if text else None
            await self.client.change_presence(status=status, activity=activity)
            self._last = (status, text)
        except Exception as e:
            print(f"[presence] update failed: {e}")

