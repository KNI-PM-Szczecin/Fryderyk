import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption

class LogBlacklistCog(commands.Cog):
    """
    Discord Cog responsible for managing blacklists for specific bot features 
    (like message logging or random GIF reactions) via slash commands.
    """
    def __init__(self, client, config, database):
        """
        Initializes the LogBlacklistCog with bot instance, config, and database connection.
        """
        self.client = client
        self.config = config
        self.database = database

    @nextcord.slash_command(
        name="blacklist", 
        description="Zarządzanie czarną listą logowania",
        contexts=[nextcord.InteractionContextType.guild],
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def blacklist(self, interaction: Interaction):
        """
        Base slash command group for managing feature blacklists.
        Restricted to server administrators.
        """
        pass

    @blacklist.subcommand(name="add", description="Dodaj kanał lub rolę do czarnej listy")
    async def add(
        self, 
        interaction: Interaction,
        funkcja: str = SlashOption(name="funkcja", description="Funkcja do zablokowania", choices={"Logowanie wiadomości": "log", "Wysyłanie GIF-ów": "gif_react"}, required=True),
        channel: nextcord.abc.GuildChannel = SlashOption(name="kanal", description="Kanał do zablokowania", required=False),
        role: nextcord.Role = SlashOption(name="rola", description="Rola do zablokowania", required=False)
    ):
        """
        Subcommand to add a specific channel or role to the blacklist for a selected feature.
        Saves the configuration in the database.
        """
        if not channel and not role:
            await interaction.response.send_message("Musisz wybrać kanał lub rolę.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        db_put = self.database.put_blacklist_item if funkcja == "log" else self.database.put_gif_blacklist_item
        
        if channel:
            item_id = channel.id
            item_type = str(channel.type)
            item_name = channel.name
            db_put(guild_id, item_id, item_type)
            await interaction.response.send_message(f"Kanał {item_name} został dodany do czarnej listy dla funkcji: {funkcja}.", ephemeral=True)

        if role:
            item_id = role.id
            item_type = "role"
            item_name = role.name
            db_put(guild_id, item_id, item_type)
            await interaction.response.send_message(f"Rola {item_name} została dodana do czarnej listy dla funkcji: {funkcja}.", ephemeral=True)

    @blacklist.subcommand(name="remove", description="Usuń kanał lub rolę z czarnej listy")
    async def remove(
        self, 
        interaction: Interaction,
        funkcja: str = SlashOption(name="funkcja", description="Funkcja z której usuwamy blokadę", choices={"Logowanie wiadomości": "log", "Wysyłanie GIF-ów": "gif_react"}, required=True),
        channel: nextcord.abc.GuildChannel = SlashOption(name="kanal", description="Kanał do usunięcia", required=False),
        role: nextcord.Role = SlashOption(name="rola", description="Rola do usunięcia", required=False)
    ):
        """
        Subcommand to remove a specific channel or role from the blacklist for a selected feature.
        Deletes the configuration from the database.
        """
        if not channel and not role:
            await interaction.response.send_message("Musisz wybrać kanał lub rolę.", ephemeral=True)
            return

        guild_id = interaction.guild.id
        db_delete = self.database.delete_blacklist_item if funkcja == "log" else self.database.delete_gif_blacklist_item
        
        if channel:
            db_delete(guild_id, channel.id)
            await interaction.response.send_message(f"Kanał {channel.name} został usunięty z czarnej listy dla funkcji: {funkcja}.", ephemeral=True)

        if role:
            db_delete(guild_id, role.id)
            await interaction.response.send_message(f"Rola {role.name} została usunięta z czarnej listy dla funkcji: {funkcja}.", ephemeral=True)

    @blacklist.subcommand(name="list", description="Lista zablokowanych kanałów i ról")
    async def list_blacklist(
        self, 
        interaction: Interaction,
        funkcja: str = SlashOption(name="funkcja", description="Funkcja dla której sprawdzamy listę", choices={"Logowanie wiadomości": "log", "Wysyłanie GIF-ów": "gif_react"}, required=True)
    ):
        """
        Subcommand that lists all channels and roles currently blacklisted for a selected feature.
        """
        guild_id = interaction.guild.id
        db_get = self.database.get_blacklist if funkcja == "log" else self.database.get_gif_blacklist
        items = db_get(guild_id)

        if not items:
            await interaction.response.send_message(f"Czarna lista dla funkcji '{funkcja}' jest pusta.", ephemeral=True)
            return

        response = f"**Czarna lista dla funkcji '{funkcja}':**\n"
        for item_id, item_type in items:
            mention = f"<@&{item_id}>" if item_type == "role" else f"<#{item_id}>"
            response += f"- {mention} ({item_type})\n"

        await interaction.response.send_message(response, ephemeral=True)
