import os
from datetime import datetime, timezone, timedelta

import nextcord
from nextcord.ext import commands
from nextcord import Interaction

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_git_info():
    """
    Reads the local `.git` directory to extract the latest commit hash and its timestamp.
    Used to dynamically determine the bot's current running version without needing env vars.
    Returns a tuple of (short_commit_hash, commit_datetime).
    """
    git_dir = os.path.join(REPO_ROOT, ".git")
    try:
        with open(os.path.join(git_dir, "HEAD")) as f:
            head = f.read().strip()

        if head.startswith("ref: "):
            ref_path = os.path.join(git_dir, head[5:])
            with open(ref_path) as f:
                commit_hash = f.read().strip()
        else:
            commit_hash = head

        reflog_path = os.path.join(git_dir, "logs", "HEAD")
        with open(reflog_path) as f:
            last_line = f.readlines()[-1]

        # format: <old> <new> <name> <email> <unix_ts> <tz_offset>\t<msg>
        meta = last_line.split("\t")[0].split()
        unix_ts = int(meta[-2])
        tz_sign = 1 if meta[-1][0] == "+" else -1
        tz_hours = int(meta[-1][1:3])
        tz_minutes = int(meta[-1][3:5])
        tz_offset = timedelta(hours=tz_hours, minutes=tz_minutes) * tz_sign
        commit_dt = datetime.fromtimestamp(unix_ts, tz=timezone(tz_offset))

        return commit_hash[:7], commit_dt
    except Exception:
        return None, None


class VersionCog(commands.Cog):
    """
    Discord Cog that provides the '/version' slash command to check the bot's current build version.
    """
    def __init__(self, client, config, database):
        """
        Initializes the VersionCog with the bot instance.
        """
        self.client = client

    @nextcord.slash_command(
        name="version",
        description="Pokaż aktualną wersję bota (ostatni commit)",
        dm_permission=False,
        guild_ids=[1357420845970100335],
    )
    async def version(self, interaction: Interaction):
        """
        Slash command limited to a specific guild that returns the bot's current version
        based on the latest git commit hash and date.
        """
        commit_hash, commit_dt = _read_git_info()

        if commit_hash is None:
            await interaction.response.send_message(
                "Nie można odczytać informacji o wersji.", ephemeral=True
            )
            return

        formatted_date = commit_dt.strftime("%Y-%m-%d %H:%M %Z")
        await interaction.response.send_message(
            f"`{commit_hash}` · {formatted_date}", ephemeral=True
        )
