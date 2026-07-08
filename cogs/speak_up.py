import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption
from decorators import cog_cooldown
from utilities.baseUtils import post_webhook


class SpeakUpCog(commands.Cog):
    """
    Discord Cog that provides the '/zabierz_glos' slash command. 
    It allows users to request the bot to generate a response or opinion 
    based on the current channel's discussion context via an external n8n webhook.
    """
    def __init__(self, client, config, database):
        """
        Initializes the SpeakUpCog with the bot instance, config, and database connection.
        """
        self.client = client
        self.config = config
        self.database = database

    @nextcord.slash_command(
        name="zabierz_glos",
        description="Poproś Fryderyka, żeby wypowiedział się na temat dyskusji na tym kanale",
        contexts=[nextcord.InteractionContextType.guild],
    )
    @cog_cooldown(rate=1, per=20.0, message="**Zwolnij!** Fryderyk lubi wooolno, następne zabranie głosu możliwe za **&value&s**.", per_guild=True)
    async def zabierz_glos(
        self,
        interaction: Interaction,
        env: str = SlashOption(
            name="env",
            description="Środowisko webhooka (domyślnie production)",
            required=False,
            default="production",
            choices={"Test": "test", "Production": "production"},
        ),
    ):
        """
        Slash command limited to a specific guild that triggers the bot to "speak up".
        Sends a payload with the channel and user context to an n8n webhook,
        and is rate-limited by the cog_cooldown decorator. The test environment is admin-only.
        """
        await interaction.response.defer(ephemeral=True)

        if not self.database.is_module_enabled(interaction.guild.id, "speak_up"):
            await interaction.followup.send(
                "Moduł `/zabierz_glos` jest obecnie wyłączony (zobacz `/moduly status`).",
                ephemeral=True,
            )
            return

        if env == "test" and not interaction.user.guild_permissions.administrator:
            await interaction.followup.send(
                "Środowisko testowe jest dostępne tylko dla administratorów.",
                ephemeral=True,
            )
            return

        channel = interaction.channel
        payload = {
            "channel_id": str(channel.id),
            "channel_name": getattr(channel, "name", None),
            "guild_id": str(interaction.guild.id),
            "requested_by": str(interaction.user.id),
        }

        try:
            status = await post_webhook(self.config.get_n8n_url("speak", env), payload)
        except Exception as e:
            await interaction.followup.send(
                f"Nie udało się połączyć z webhookiem: {e}",
                ephemeral=True,
            )
            return

        if status < 300:
            await interaction.followup.send(
                f"Fryderyk zabiera głos na {channel.mention} (`{env}`).",
                ephemeral=True,
            )
        elif status == 404:
            await interaction.followup.send(
                "Fryderyk ma spanko 😴",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"Webhook zwrócił błąd: HTTP {status}.",
                ephemeral=True,
            )
