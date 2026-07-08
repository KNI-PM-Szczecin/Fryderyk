import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption
from decorators import cog_cooldown
from utilities.baseUtils import post_webhook


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
        self.database = database

    @nextcord.slash_command(
        name="profile",
        description="Wyślij ID wybranego użytkownika do n8n",
        contexts=[nextcord.InteractionContextType.guild],
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
            description="Środowisko webhooka (domyślnie production)",
            required=False,
            default="production",
            choices={"Test": "test", "Production": "production"},
        ),
    ):
        """
        Slash command limited to a specific guild that triggers user profile generation.
        Sends a payload containing the target user, the requesting user, and the channel
        context to an n8n webhook. Protected by a rate limit (cog_cooldown).
        The test environment is admin-only.
        """
        await interaction.response.defer(ephemeral=True)

        if not self.database.is_module_enabled(interaction.guild.id, "profile"):
            await interaction.followup.send(
                "Moduł `/profile` jest obecnie wyłączony (zobacz `/moduly status`).",
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
            "user_id": str(member.id),
            "guild_id": str(interaction.guild.id),
            "source_channel_id": str(source_channel.id) if source_channel else None,
            "source_channel_name": getattr(source_channel, "name", None),
            "requested_by": str(interaction.user.id),
        }

        try:
            status = await post_webhook(self.config.get_n8n_url("profile", env), payload)
        except Exception as e:
            await interaction.followup.send(
                f"Nie udało się połączyć z webhookiem: {e}",
                ephemeral=True,
            )
            return

        if status < 300:
            await interaction.followup.send(
                f"Wysłano profil użytkownika {member.mention} (`{env}`).",
                ephemeral=True,
            )
        else:
            await interaction.followup.send(
                f"Webhook zwrócił błąd: HTTP {status}.",
                ephemeral=True,
            )
