import nextcord
from nextcord.ext import commands
from utilities import baseUtils, Database
import os

def main():
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
        print(f'Logged in as {client.user} (ID: {client.user.id})')
        print('------')

    client.run(config.get_bot_token())

if __name__ == "__main__":
    main()
