import asyncio
from zoneinfo import ZoneInfo

import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption

# Per-line and total caps so the embed stays within Discord's 4096-char
# description limit even at limit=25.
LINE_MAX_CHARS = 140
DESCRIPTION_MAX_CHARS = 3900


class LogsCog(commands.Cog):
    """
    Discord Cog providing the admin-only '/logi' slash command: shows the most
    recent log entries (events, messages, voice sessions, or the command audit)
    for the current guild. The response is always ephemeral — only the invoker
    sees it.
    """
    def __init__(self, client, config, database):
        """
        Initializes the LogsCog with the bot instance, config, and database connection.
        """
        self.client = client
        self.config = config
        self.database = database
        self.tz = ZoneInfo(config.get_timezone())

    def _fetch_lines(self, log_type, guild_id, limit):
        """
        Fetches recent rows for the requested log type and formats them into
        display lines (newest first). Runs synchronous DB queries — dispatch
        via asyncio.to_thread.
        """
        lines = []
        if log_type == "messages":
            for date, user_name, channel_name, message in self.database.get_recent_messages(guild_id, limit):
                text = (message or "").replace("\n", " ")
                lines.append(f"`{self._fmt_date(date)}` **{user_name}** w #{channel_name}: {text}")
        elif log_type == "voice":
            for date_join, user_name, channel_name, time_on in self.database.get_recent_voice(guild_id, limit):
                lines.append(f"`{self._fmt_date(date_join)}` **{user_name}** — {time_on}s w 🔊{channel_name}")
        else:
            whats = ("command", "command denied") if log_type == "commands" else None
            for date, user_name, what, about in self.database.get_recent_events(guild_id, limit, whats):
                user_label = user_name or "System"
                lines.append(f"`{self._fmt_date(date)}` **{user_label}** — {what}: {about}")
        return lines

    def _fmt_date(self, date):
        """Formats a TIMESTAMPTZ value in the bot's timezone; tolerates NULLs."""
        if not date:
            return "??"
        return date.astimezone(self.tz).strftime("%Y-%m-%d %H:%M")

    @nextcord.slash_command(
        name="logi",
        description="Pokaż ostatnie logi (odpowiedź widzi tylko wywołujący)",
        contexts=[nextcord.InteractionContextType.guild],
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def logi(
        self,
        interaction: Interaction,
        typ: str = SlashOption(
            name="typ",
            description="Rodzaj logów (domyślnie eventy)",
            required=False,
            default="events",
            choices={
                "Eventy serwera": "events",
                "Wiadomości": "messages",
                "Sesje głosowe": "voice",
                "Komendy (audyt)": "commands",
            },
        ),
        limit: int = SlashOption(
            name="limit",
            description="Ile wpisów pokazać (1-25, domyślnie 10)",
            required=False,
            default=10,
            min_value=1,
            max_value=25,
        ),
    ):
        """
        Ephemeral, admin-only view of the newest log entries for this guild.
        """
        await interaction.response.defer(ephemeral=True)

        lines = await asyncio.to_thread(self._fetch_lines, typ, interaction.guild.id, limit)

        if not lines:
            await interaction.followup.send("Brak wpisów w logach dla tego typu.", ephemeral=True)
            return

        description = ""
        shown = 0
        for line in lines:
            if len(line) > LINE_MAX_CHARS:
                line = line[:LINE_MAX_CHARS] + "…"
            if len(description) + len(line) + 1 > DESCRIPTION_MAX_CHARS:
                break
            description += line + "\n"
            shown += 1

        embed = nextcord.Embed(
            title=f"Ostatnie logi ({typ})",
            description=description,
            color=nextcord.Color.blurple(),
        )
        embed.set_footer(text=f"Pokazano {shown} z {len(lines)} pobranych wpisów (najnowsze pierwsze)")
        await interaction.followup.send(embed=embed, ephemeral=True)
