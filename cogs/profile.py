import aiohttp
import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption
from decorators import cog_cooldown


class ProfileCog(commands.Cog):
    """
    Discord Cog that provides the '/profile' slash command. 
    It enables users to request a generated profile or summary for a specific server member 
    by sending the relevant user IDs to an external n8n webhook.
    """
    def __init__(self, client, config, database):
        """
        Initializes the ProfileCog with the bot instance, config, and database connection.
        """
        self.client = client
        self.config = config

    @nextcord.slash_command(
        name="profile",
        description="Wyślij ID wybranego użytkownika do n8n",
        dm_permission=False,
        guild_ids=[1357420845970100335],
    )
    @cog_cooldown(rate=1, per=20.0, message="**Zwolnij!** Fryderyk lubi wooolno, następne wygenerowanie profilu możliwe za **&value&s**.", per_guild=True)
    async def profile(
        self,
        interaction: Interaction,
        member: nextcord.Member = SlashOption(
            name="member",
            description="Użytkownik, dla którego chcesz wygenerować profil",
            required=True,
        ),
        env: str = SlashOption(
            name="env",
            description="Środowisko webhooka",
            required=True,
            choices={"Test": "test", "Production": "production"},
        ),
    ):
        """
        Slash command limited to a specific guild that triggers user profile generation.
        Sends a payload containing the target user, the requesting user, and the channel 
        context to an n8n webhook. Protected by a rate limit (cog_cooldown).
        """
        await interaction.response.defer(ephemeral=True)

        source_channel = interaction.channel
        payload = {
            "user_id": str(member.id),
            "guild_id": str(interaction.guild.id),
            "source_channel_id": str(source_channel.id) if source_channel else None,
            "source_channel_name": getattr(source_channel, "name", None),
            "requested_by": str(interaction.user.id),
        }

        url = self.config.get_n8n_profile_webhook_url(env)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status < 300:
                        await interaction.followup.send(
                            f"Wysłano profil użytkownika {member.mention} (`{env}`).",
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
