import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption

class LogBlacklistCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database

    @nextcord.slash_command(
        name="blacklist", 
        description="Zarządzanie czarną listą logowania",
        dm_permission=False,
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def blacklist(self, interaction: Interaction):
        pass

    @blacklist.subcommand(name="add", description="Dodaj kanał lub rolę do czarnej listy (nie będą logowane)")
    async def add(
        self, 
        interaction: Interaction,
        channel: nextcord.abc.GuildChannel = SlashOption(name="kanal", description="Kanał do zablokowania", required=False),
        role: nextcord.Role = SlashOption(name="rola", description="Rola do zablokowania", required=False)
    ):
        if not channel and not role:
            await interaction.response.send_message("Musisz wybrać kanał lub rolę.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        
        if channel:
            item_id = channel.id
            item_type = str(channel.type)
            item_name = channel.name
            self.database.put_blacklist_item(guild_id, item_id, item_type)
            await interaction.response.send_message(f"Kanał {item_name} został dodany do czarnej listy.", ephemeral=True)

        if role:
            item_id = role.id
            item_type = "role"
            item_name = role.name
            self.database.put_blacklist_item(guild_id, item_id, item_type)
            await interaction.response.send_message(f"Rola {item_name} została dodana do czarnej listy.", ephemeral=True)

    @blacklist.subcommand(name="remove", description="Usuń kanał lub rolę z czarnej listy")
    async def remove(
        self, 
        interaction: Interaction,
        channel: nextcord.abc.GuildChannel = SlashOption(name="kanal", description="Kanał do usunięcia", required=False),
        role: nextcord.Role = SlashOption(name="rola", description="Rola do usunięcia", required=False)
    ):
        if not channel and not role:
            await interaction.response.send_message("Musisz wybrać kanał lub rolę.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        
        if channel:
            self.database.delete_blacklist_item(guild_id, channel.id)
            await interaction.response.send_message(f"Kanał {channel.name} został usunięty z czarnej listy.", ephemeral=True)

        if role:
            self.database.delete_blacklist_item(guild_id, role.id)
            await interaction.response.send_message(f"Rola {role.name} została usunięta z czarnej listy.", ephemeral=True)

    @blacklist.subcommand(name="list", description="Lista zablokowanych kanałów i ról")
    async def list_blacklist(self, interaction: Interaction):
        guild_id = interaction.guild.id
        items = self.database.get_blacklist(guild_id)

        if not items:
            await interaction.response.send_message("Czarna lista jest pusta.", ephemeral=True)
            return

        response = "**Czarna lista logowania:**\n"
        for item_id, item_type in items:
            mention = f"<#{item_id}>" if "channel" in item_type else f"<@&{item_id}>"
            response += f"- {mention} ({item_type})\n"

        await interaction.response.send_message(response, ephemeral=True)
