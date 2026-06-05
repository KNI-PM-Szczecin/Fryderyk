import aiohttp
import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption


class SummarizeCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config

    @nextcord.slash_command(
        name="summarize",
        description="Wyślij żądanie podsumowania kanału do n8n",
        dm_permission=False,
        guild_ids=[1357420845970100335],
    )
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
            description="Środowisko webhooka",
            required=True,
            choices={"Test": "test", "Production": "production"},
        ),
    ):
        await interaction.response.defer(ephemeral=True)

        source_channel = interaction.channel
        payload = {
            "channel_id": str(channel.id),
            "channel_name": channel.name,
            "guild_id": str(interaction.guild.id),
            "source_channel_id": str(source_channel.id) if source_channel else None,
            "source_channel_name": getattr(source_channel, "name", None),
            "requested_by": str(interaction.user.id),
        }

        url = self.config.get_n8n_webhook_url(env)
        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload) as resp:
                    if resp.status < 300:
                        await interaction.followup.send(
                            f"Wysłano żądanie podsumowania dla {channel.mention} (`{env}`).",
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
