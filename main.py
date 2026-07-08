"""
Entry point for the Fryderyk Discord bot.

Wires together configuration (`ConfigReader`), the PostgreSQL layer (`Database`),
and the cog auto-loader (`baseUtils.Loader`), then starts the nextcord client.
Cogs are discovered from the `cogs/` package by naming convention — see the loader
and CLAUDE.md for the contract.
"""
import traceback
import nextcord
from nextcord.ext import commands
from utilities import baseUtils, Database

def main():
    """
    Initializes and starts the Discord bot.
    It reads the configuration, connects to the database, sets up necessary intents,
    loads all extensions (cogs) via the Loader, and runs the bot with the provided token.
    """
    config = baseUtils.ConfigReader()
    database = Database.Database(config.get_db_config())

    intents = nextcord.Intents.default()
    intents.message_content = True
    intents.members = True

    client = commands.Bot(intents=intents)

    payload = {
        'client': client,
        'config': config,
        'database': database
    }

    baseUtils.Loader(payload)

    operator_role_id = baseUtils.get_operator_role_id()

    @client.application_command_check
    def require_operator_role(interaction: nextcord.Interaction) -> bool:
        """
        Global check: every slash command requires the operator role
        (OPERATOR_ROLE_ID). Runs before any per-command checks.
        """
        roles = getattr(interaction.user, "roles", None) or []
        return any(role.id == operator_role_id for role in roles)

    @client.event
    async def on_application_command_error(interaction: nextcord.Interaction, error: Exception):
        """
        Turns check failures into a friendly ephemeral message instead of the
        default silent "application did not respond"; other errors keep the
        default traceback logging.
        """
        if isinstance(error, nextcord.errors.ApplicationCheckFailure):
            message = "Ta komenda wymaga roli operatora Fryderyka."
            try:
                if interaction.response.is_done():
                    await interaction.followup.send(message, ephemeral=True)
                else:
                    await interaction.response.send_message(message, ephemeral=True)
            except Exception as e:
                print(f"[AppCommand ERR] Could not send check-failure response: {e}")
            return
        print(f"[AppCommand ERR] Command failed: {error!r}")
        traceback.print_exception(type(error), error, error.__traceback__)

    @client.event
    async def on_ready():
        """
        Event triggered when the bot successfully connects to Discord and is ready to operate.
        Prints the bot's username and ID to the console.
        """
        print(f'Logged in as {client.user} (ID: {client.user.id})')
        print('------')

    client.run(config.get_bot_token())

if __name__ == "__main__":
    main()
