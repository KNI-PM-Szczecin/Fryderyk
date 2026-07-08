import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption
from decorators import cog_cooldown
from utilities.baseUtils import post_webhook


class SummarizeCog(commands.Cog):
    """
    Discord Cog that provides the '/summarize' slash command. 
    It allows users to trigger a channel summary generation by sending a payload 
    to an external n8n webhook, which handles the actual summarization logic.
    """
    def __init__(self, client, config, database):
        """
        Initializes the SummarizeCog with the bot instance, config, and database connection.
        """
        self.client = client
        self.config = config
        self.database = database

    @nextcord.slash_command(
        name="summarize",
        description="Wyślij żądanie podsumowania kanału do n8n",
        contexts=[nextcord.InteractionContextType.guild],
    )
    @cog_cooldown(rate=1, per=20.0, message="**Zwolnij!** Fryderyk lubi wooolno, następne podsumowanie możliwe za **&value&s**.", per_guild=True)
    async def summarize(
        self,
        interaction: Interaction,
        channel: nextcord.TextChannel = SlashOption(
            name="channel",
            description="Kanał do podsumowania",
            required=True,
        ),
        env: str = SlashOption(
            name="env",
            description="Środowisko webhooka (domyślnie production)",
            required=False,
            default="production",
            choices={"Test": "test", "Production": "production"},
        ),
    ):
        """
        Slash command limited to a specific guild that triggers a channel summary.
        Sends a payload containing the target channel and the requesting user to an n8n webhook.
        Protected by a rate limit (cog_cooldown). The test environment is admin-only.
        """
        await interaction.response.defer(ephemeral=True)

        if not self.database.is_module_enabled(interaction.guild.id, "summarize"):
            await interaction.followup.send(
                "Moduł `/summarize` jest obecnie wyłączony (zobacz `/moduly status`).",
                ephemeral=True,
            )
            return

        if env == "test" and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "Środowisko testowe jest dostępne tylko dla administratorów.",
                ephemeral=True,
            )
            return

        source_channel = interaction.channel
        payload = {
            "channel_id": str(channel.id),
            "channel_name": channel.name,
            "guild_id": str(interaction.guild.id),
            "source_channel_id": str(source_channel.id) if source_channel else None,
            "source_channel_name": getattr(source_channel, "name", None),
            "requested_by": str(interaction.user.id),
        }

        try:
            status = await post_webhook(self.config.get_n8n_url("summarize", env), payload)
        except Exception as e:
            await interaction.followup.send(
                f"Nie udało się połączyć z webhookiem: {e}",
                ephemeral=True,
            )
            return

        if status < 300:
            await interaction.followup.send(
                f"Wysłano żądanie podsumowania dla {channel.mention} (`{env}`).",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"Webhook zwrócił błąd: HTTP {status}.",
                ephemeral=True,
            )
