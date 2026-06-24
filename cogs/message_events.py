import nextcord
from nextcord.ext import commands
from zoneinfo import ZoneInfo
from utilities.baseUtils import DiscordUtils

class MessageEventsCog(commands.Cog):
    """
    Discord Cog responsible for tracking and logging chat messages into the database.
    It automatically records both new messages and message edits, while respecting 
    configured blacklists for specific channels or roles.
    """
    def __init__(self, client, config, database):
        """
        Initializes the MessageEventsCog with the bot, config, and database connection.
        Sets the default timezone to Europe/Warsaw for timestamps.
        """
        self.client = client
        self.config = config
        self.database = database
        self.tz = ZoneInfo("Europe/Warsaw")

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message):
        # Skip ephemeral messages authored by bots (e.g. our own backfill
        # progress updates) — they're not real chat content.
        """
        Event listener triggered on every new message in the server.
        Parses mentions, applies blacklist rules, assigns the local timezone, 
        and inserts the message record into the database.
        """
        if message.author.bot and message.flags.ephemeral:
            return

        if not message.guild:
            return

        # Check if channel is blacklisted
        if self.database.is_blacklisted(message.guild.id, message.channel.id):
            return

        # Check if any of author's roles are blacklisted
        if hasattr(message.author, 'roles'):
            for role in message.author.roles:
                if self.database.is_blacklisted(message.guild.id, role.id):
                    return

        parsed_content = DiscordUtils.parse_mentions(message)

        # Determine category and guild details
        category_id = None
        category_name = None
        if hasattr(message.channel, 'category') and message.channel.category:
            category_id = message.channel.category.id
            category_name = message.channel.category.name

        guild_id = message.guild.id if message.guild else None
        guild_name = message.guild.name if message.guild else None

        # Convert UTC time to Polish timezone
        polish_date = message.created_at.astimezone(self.tz)

        # Log new message
        self.database.put_message(
            discord_id=message.id,
            user_id=message.author.id,
            user_name=message.author.name,
            message=parsed_content,
            is_edited=False,
            is_bot=message.author.bot,
            date=polish_date,
            edit_date=None,
            channel_id=message.channel.id,
            channel_name=message.channel.name,
            guild_id=guild_id,
            guild_name=guild_name,
            category_id=category_id,
            category_name=category_name
        )

    @commands.Cog.listener()
    async def on_message_edit(self, before: nextcord.Message, after: nextcord.Message):
        # Skip ephemeral messages authored by bots (mirrors the on_message guard).
        """
        Event listener triggered when a message is edited.
        Logs the edited version as a distinct new entry in the database (with is_edited=True) 
        if the actual text content was changed, while still respecting blacklist rules.
        """
        if after.author.bot and after.flags.ephemeral:
            return

        if not after.guild:
            return

        # Check if channel is blacklisted
        if self.database.is_blacklisted(after.guild.id, after.channel.id):
            return

        # Check if any of author's roles are blacklisted
        if hasattr(after.author, 'roles'):
            for role in after.author.roles:
                if self.database.is_blacklisted(after.guild.id, role.id):
                    return

        # If content hasn't changed (e.g. only embeds loaded), skip
        if before.content == after.content:
            return

        parsed_content = DiscordUtils.parse_mentions(after)

        category_id = None
        category_name = None
        if hasattr(after.channel, 'category') and after.channel.category:
            category_id = after.channel.category.id
            category_name = after.channel.category.name

        guild_id = after.guild.id if after.guild else None
        guild_name = after.guild.name if after.guild else None

        # Convert UTC times to Polish timezone
        polish_date = after.created_at.astimezone(self.tz)
        edit_time = after.edited_at or nextcord.utils.utcnow()
        polish_edit_date = edit_time.astimezone(self.tz)

        # Log edited message as a new entry with is_edited=True
        # We pass discord_id=None to allow multiple rows for the same message in case of multiple edits
        self.database.put_message(
            discord_id=None,
            user_id=after.author.id,
            user_name=after.author.name,
            message=parsed_content,
            is_edited=True,
            is_bot=after.author.bot,
            date=polish_date,
            edit_date=polish_edit_date,
            channel_id=after.channel.id,
            channel_name=after.channel.name,
            guild_id=guild_id,
            guild_name=guild_name,
            category_id=category_id,
            category_name=category_name
        )
