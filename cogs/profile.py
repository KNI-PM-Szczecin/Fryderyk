import aiohttp
import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption


class ProfileCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config

    @nextcord.slash_command(
        name="profile",
        description="Wyślij ID wybranego użytkownika do n8n",
        dm_permission=False,
        guild_ids=[1357420845970100335],
    )
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
        await interaction.response.defer(ephemeral=True)

        payload = {
            "user_id": member.id,
            "guild_id": interaction.guild.id,
            "requested_by": interaction.user.id,
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
