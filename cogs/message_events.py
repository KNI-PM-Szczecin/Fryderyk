import nextcord
from nextcord.ext import commands
from zoneinfo import ZoneInfo

class MessageEventsCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        self.tz = ZoneInfo("Europe/Warsaw")

    def _parse_mentions(self, message: nextcord.Message):
        content = message.content
        
        # Parse User mentions: <@123...> or <@!123...>
        for user in message.mentions:
            mention_str = f"<@{user.id}>"
            mention_str_nick = f"<@!{user.id}>"
            replacement = f"user:{user.display_name}"
            content = content.replace(mention_str, replacement).replace(mention_str_nick, replacement)
            
        # Parse Role mentions: <@&123...>
        for role in message.role_mentions:
            mention_str = f"<@&{role.id}>"
            replacement = f"role:{role.name}"
            content = content.replace(mention_str, replacement)
            
        # Parse Channel mentions: <#123...>
        for channel in message.channel_mentions:
            mention_str = f"<#{channel.id}>"
            replacement = f"channel:{channel.name}"
            content = content.replace(mention_str, replacement)
            
        return content

    @commands.Cog.listener()
    async def on_message(self, message: nextcord.Message):
        parsed_content = self._parse_mentions(message)
        
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
        # If content hasn't changed (e.g. only embeds loaded), skip
        if before.content == after.content:
            return

        parsed_content = self._parse_mentions(after)

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
        self.database.put_message(
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
