import nextcord
from nextcord.ext import commands
from utilities import baseUtils, Database
import os

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
