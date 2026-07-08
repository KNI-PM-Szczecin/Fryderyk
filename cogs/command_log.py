import asyncio
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import nextcord
from nextcord.ext import commands


class CommandLogCog(commands.Cog):
    """
    Audit log for slash commands: records WHO invoked WHAT command, WHEN, and
    with which arguments into the `events` table.

    Uses the client's global application_command_before_invoke hook, so every
    slash command (current and future) is logged with no per-command code.
    Denied attempts (failed checks, e.g. missing operator role) never reach the
    before-invoke hook, so they are caught via on_application_command_error and
    logged as 'command denied'. Audit entries deliberately ignore blacklists.
    """
    def __init__(self, client, config, database):
        """
        Initializes the cog and registers the global before-invoke hook on the client.
        """
        self.client = client
        self.config = config
        self.database = database
        self.tz = ZoneInfo(config.get_timezone())
        client.application_command_before_invoke(self._on_command_invoke)

    @staticmethod
    def _describe_invocation(interaction: nextcord.Interaction):
        """
        Extracts the full command name (including subcommands) and the leaf
        arguments from the raw interaction payload. Returns (name, args_dict).
        Argument values are the raw Discord values (snowflake IDs for
        user/channel/role options).
        """
        data = interaction.data or {}
        name_parts = [data.get("name", "?")]
        options = data.get("options") or []

        # Descend through subcommand groups (type 2) and subcommands (type 1).
        while len(options) == 1 and options[0].get("type") in (1, 2):
            name_parts.append(options[0]["name"])
            options = options[0].get("options") or []

        args = {opt.get("name"): opt.get("value") for opt in options}
        return " ".join(name_parts), args

    def _log_command(self, interaction: nextcord.Interaction, denied: bool = False):
        """
        Writes a single audit entry to the events table. Runs in a worker
        thread (synchronous DB call) — dispatch via asyncio.to_thread.
        """
        command_name, args = self._describe_invocation(interaction)

        about = f"/{command_name}"
        if args:
            about += " " + json.dumps(args, ensure_ascii=False, default=str)

        channel = interaction.channel
        guild = interaction.guild
        category = getattr(channel, "category", None)
        user = interaction.user

        self.database.put_event(
            user_id=user.id if user else None,
            user_name=user.name if user else None,
            is_bot=bool(user and user.bot),
            what="command denied" if denied else "command",
            about=about,
            date=datetime.now(self.tz),
            channel_id=getattr(channel, "id", None),
            channel_name=getattr(channel, "name", None),
            guild_id=guild.id if guild else None,
            guild_name=guild.name if guild else None,
            category_id=category.id if category else None,
            category_name=category.name if category else None,
        )

    async def _on_command_invoke(self, interaction: nextcord.Interaction):
        """Global before-invoke hook: logs every command that passed all checks."""
        await asyncio.to_thread(self._log_command, interaction)

    @commands.Cog.listener()
    async def on_application_command_error(self, interaction: nextcord.Interaction, error: Exception):
        """
        Logs attempts rejected by a check (e.g. missing operator role).
        The user-facing ephemeral reply is handled in main.py; this listener
        only records the attempt.
        """
        if isinstance(error, nextcord.errors.ApplicationCheckFailure):
            await asyncio.to_thread(self._log_command, interaction, True)
