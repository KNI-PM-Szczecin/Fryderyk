import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption

# Registry of toggleable modules: key (stored in module_states) -> human label.
# Gated code calls database.is_module_enabled(guild_id, key); keys here and in
# the gated cogs must match. Deliberately NOT toggleable: data_sync (DB would
# desync), command_log (audit must always run), blacklist/module management,
# backfill, /version, /off.
MODULES = {
    "gif_react": "Losowe GIF-y (random_reaction)",
    "mention_webhook": "Webhook przy wzmiance (mention_trigger)",
    "message_log": "Logowanie wiadomości (message_events)",
    "voice_log": "Logowanie sesji głosowych (voice_events)",
    "event_log": "Logowanie eventów serwera (general_events)",
    "speak_up": "Komenda /zabierz_glos",
    "summarize": "Komenda /summarize",
    "profile": "Komenda /profile",
}

# SlashOption choices map display label -> stored key.
MODULE_CHOICES = {label: key for key, label in MODULES.items()}


class ModuleControlCog(commands.Cog):
    """
    Discord Cog for enabling/disabling individual bot modules per guild and
    inspecting their state. State is persisted in the module_states table
    (a row = disabled), so it survives restarts; checks hit an in-memory cache.
    """
    def __init__(self, client, config, database):
        """
        Initializes the ModuleControlCog with bot instance, config, and database connection.
        """
        self.client = client
        self.config = config
        self.database = database

    @nextcord.slash_command(
        name="moduly",
        description="Zarządzanie modułami Fryderyka",
        contexts=[nextcord.InteractionContextType.guild],
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def moduly(self, interaction: Interaction):
        """
        Base slash command group for managing bot modules.
        Restricted to server administrators.
        """

    @moduly.subcommand(name="status", description="Pokaż stan wszystkich modułów")
    async def status(self, interaction: Interaction):
        """
        Subcommand that lists every toggleable module with its current state.
        """
        lines = []
        for key, label in MODULES.items():
            enabled = self.database.is_module_enabled(interaction.guild.id, key)
            lines.append(f"{'✅' if enabled else '⛔'} `{key}` — {label}")
        await interaction.response.send_message("**Stan modułów Fryderyka:**\n" + "\n".join(lines), ephemeral=True)

    @moduly.subcommand(name="wylacz", description="Wyłącz wybrany moduł")
    async def wylacz(
        self,
        interaction: Interaction,
        modul: str = SlashOption(name="modul", description="Moduł do wyłączenia", required=True, choices=MODULE_CHOICES)
    ):
        """
        Subcommand that disables the selected module for this guild.
        """
        if not self.database.is_module_enabled(interaction.guild.id, modul):
            await interaction.response.send_message(f"Moduł `{modul}` jest już wyłączony.", ephemeral=True)
            return
        self.database.disable_module(interaction.guild.id, modul)
        await interaction.response.send_message(f"⛔ Moduł `{modul}` ({MODULES[modul]}) został wyłączony.", ephemeral=True)

    @moduly.subcommand(name="wlacz", description="Włącz wybrany moduł")
    async def wlacz(
        self,
        interaction: Interaction,
        modul: str = SlashOption(name="modul", description="Moduł do włączenia", required=True, choices=MODULE_CHOICES)
    ):
        """
        Subcommand that re-enables the selected module for this guild.
        """
        if self.database.is_module_enabled(interaction.guild.id, modul):
            await interaction.response.send_message(f"Moduł `{modul}` jest już włączony.", ephemeral=True)
            return
        self.database.enable_module(interaction.guild.id, modul)
        await interaction.response.send_message(f"✅ Moduł `{modul}` ({MODULES[modul]}) został włączony.", ephemeral=True)
