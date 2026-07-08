import nextcord
from nextcord.ext import commands
from nextcord.ext import application_checks

from utilities.baseUtils import get_operator_role_id


class ShutdownCog(commands.Cog):
    """
    Discord Cog that provides the '/off' slash command to shut the bot down.
    Restricted to members with the operator role (OPERATOR_ROLE_ID env var).

    Note: with `--restart unless-stopped` on the container, exiting the process
    effectively restarts the bot rather than stopping it for good.
    """
    def __init__(self, client, config, database):
        self.client = client
        self.config = config

    @nextcord.slash_command(
        name="off",
        description="Wyłącza Fryderyka",
        contexts=[nextcord.InteractionContextType.guild],
    )
    @application_checks.has_role(get_operator_role_id())
    async def shutdown_slash(self, interaction: nextcord.Interaction):
        await interaction.response.send_message("Wyłączam się. Do zobaczenia! 👋", ephemeral=True)
        print(f"[Shutdown] /off invoked by {interaction.user} ({interaction.user.id}). Closing client...")
        await self.client.close()
