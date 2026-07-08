import nextcord
from nextcord.ext import commands

from utilities.baseUtils import DiscordUtils, post_webhook


class MentionTriggerCog(commands.Cog):
    """Fires an n8n webhook whenever the bot is mentioned in a guild message."""

    def __init__(self, client, config, database):
        """
        Initializes the MentionTriggerCog with the bot, config, and database connection.
        """
        self.client = client
        self.config = config
        self.database = database

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message):
        """
        Event listener triggered on every new message in the server.
        If the bot is mentioned in a non-blacklisted channel, it extracts the message
        context and sends an HTTP POST request to the configured n8n webhook URLs.
        Other bots can trigger this (so the bot can talk with other bots); only the
        bot's own messages are ignored to avoid an immediate self-loop.
        """
        # Ignore only our own messages to avoid a self-loop; other bots are allowed.
        if self.client.user and message.author.id == self.client.user.id:
            return

        # Only guild messages carry channel/guild context for the webhook.
        if not message.guild:
            return

        # Only react when the bot is actually mentioned.
        if not self.client.user or self.client.user not in message.mentions:
            return

        if not self.database.is_module_enabled(message.guild.id, "mention_webhook"):
            return

        # Respect the same blacklist rules used for message logging.
        if self.database.is_context_blacklisted(message.guild.id, message.channel.id, message.author):
            return

        parsed_content = DiscordUtils.parse_mentions(message)

        payload = {
            "channel_id": str(message.channel.id),
            "channel_name": getattr(message.channel, "name", None),
            "guild_id": str(message.guild.id),
            "user_id": str(message.author.id),
            "user_name": message.author.name,
            "content": parsed_content,
        }

        # Which environments to notify is configurable via N8N_MENTION_ENVS
        # (comma-separated, default: production only).
        for env in self.config.get_n8n_mention_envs():
            try:
                status = await post_webhook(self.config.get_n8n_url("mention", env), payload)
                if status < 300:
                    print(f"[mention_trigger] webhook ok ({env}): HTTP {status}")
                else:
                    print(f"[mention_trigger] webhook error ({env}): HTTP {status}")
            except Exception as e:
                print(f"[mention_trigger] webhook failed ({env}): {e}")
