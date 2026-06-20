import aiohttp
import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption
from decorators import cog_cooldown


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

    @nextcord.slash_command(
        name="zabierz_glos",
        description="Poproś Fryderyka, żeby wypowiedział się na temat dyskusji na tym kanale",
        dm_permission=False,
        guild_ids=[1357420845970100335],
    )
    @cog_cooldown(rate=1, per=20.0, message="**Zwolnij!** Fryderyk lubi wooolno, następne zabranie głosu możliwe za **&value&s**.", per_guild=True)
    async def zabierz_glos(
        self,
        interaction: Interaction,
        env: str = SlashOption(
            name="env",
            description="Środowisko webhooka",
            required=True,
            choices={"Test": "test", "Production": "production"},
        ),
    ):
        """
        Slash command limited to a specific guild that triggers the bot to "speak up".
        Sends a payload with the channel and user context to an n8n webhook, 
        and is rate-limited by the cog_cooldown decorator.
        """
        await interaction.response.defer(ephemeral=True)

        channel = interaction.channel
        payload = {
            "channel_id": str(channel.id),
            "channel_name": getattr(channel, "name", None),
            "guild_id": str(interaction.guild.id),
            "requested_by": str(interaction.user.id),
        }

        url = self.config.get_n8n_speak_webhook_url(env)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status < 300:
                        await interaction.followup.send(
                            f"Fryderyk zabiera głos na {channel.mention} (`{env}`).",
                            ephemeral=True,
                        )
                    elif resp.status == 404:
                        await interaction.followup.send(
                            "Fryderyk ma spanko 😴",
                            ephemeral=True,
                        )
                    else:
                        await interaction.followup.send(
                            f"Webhook zwrócił błąd: HTTP {resp.status}.",
                            ephemeral=True,
                        )
        except Exception as e:
            await interaction.followup.send(
                f"Nie udało się połączyć z webhookiem: {e}",
                ephemeral=True,
            )
