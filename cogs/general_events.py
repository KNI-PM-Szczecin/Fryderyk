import nextcord
from nextcord.ext import commands
from datetime import datetime
from zoneinfo import ZoneInfo

class GeneralEventsCog(commands.Cog):
    """
    Discord Cog responsible for catching and logging a wide variety of general server events
    (reactions, channel/role changes, bans, timeouts, message deletions) into the database.
    """
    def __init__(self, client, config, database):
        """
        Initializes the GeneralEventsCog with the bot, configuration, and database instances.
        """
        self.client = client
        self.config = config
        self.database = database
        self.tz = ZoneInfo("Europe/Warsaw")

    def _log_event(self, user_id, user_name, what, about, channel=None, guild=None, is_bot=False):
        """
        Core helper method to format and insert an event into the database.
        It respects configured blacklists for both channels and user roles before logging.
        """
        guild_id = guild.id if guild else (channel.guild.id if channel else None)
        channel_id = channel.id if channel else None

        if guild_id:
            # Check if channel is blacklisted
            if channel_id and self.database.is_blacklisted(guild_id, channel_id):
                return

            # Check if user roles are blacklisted
            if user_id:
                guild_obj = guild or (channel.guild if channel else self.client.get_guild(guild_id))
                if guild_obj:
                    member = guild_obj.get_member(user_id)
                    if member:
                        for role in member.roles:
                            if self.database.is_blacklisted(guild_id, role.id):
                                return

        channel_name = channel.name if channel else None
        category_id = channel.category.id if channel and hasattr(channel, 'category') and channel.category else None
        category_name = channel.category.name if channel and hasattr(channel, 'category') and channel.category else None
        guild_name = guild.name if guild else (channel.guild.name if channel else None)

        # Current time in Polish timezone
        now = datetime.now(self.tz)

        self.database.put_event(
            user_id, user_name, is_bot, what, about, now, channel_id, channel_name,
            guild_id, guild_name, category_id, category_name
        )

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Event listener triggered when the bot is fully ready.
        Logs the bot's startup event into the database.
        """
        print(f"GeneralEventsCog: Bot is ready and listening for all events.")
        self._log_event(self.client.user.id, self.client.user.name, "bot start", f"logged in as {self.client.user}", is_bot=True)

    # --- REACTION EVENTS ---
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: nextcord.RawReactionActionEvent):
        """
        Event listener for when a user adds a reaction to a message.
        Logs the specific emoji and message ID.
        """
        user = self.client.get_user(payload.user_id)
        user_name = user.name if user else f"Unknown({payload.user_id})"
        is_bot = user.bot if user else False
        guild = self.client.get_guild(payload.guild_id) if payload.guild_id else None

        what = "reaction"
        about = f"added {payload.emoji} to message id {payload.message_id}"
        self._log_event(payload.user_id, user_name, what, about, guild=guild, is_bot=is_bot)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: nextcord.RawReactionActionEvent):
        """
        Event listener for when a user removes a reaction from a message.
        Logs the specific emoji and message ID.
        """
        user = self.client.get_user(payload.user_id)
        user_name = user.name if user else f"Unknown({payload.user_id})"
        is_bot = user.bot if user else False
        guild = self.client.get_guild(payload.guild_id) if payload.guild_id else None

        what = "reaction"
        about = f"removed {payload.emoji} from message id {payload.message_id}"
        self._log_event(payload.user_id, user_name, what, about, guild=guild, is_bot=is_bot)

    # --- GUILD EVENTS ---
    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        """
        Event listener triggered when the bot joins a new guild.
        """
        self._log_event(None, None, "bot joined guild", f"joined guild id {guild.id} ({guild.name})", guild=guild, is_bot=True)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        """
        Event listener triggered when the bot leaves or is kicked from a guild.
        """
        self._log_event(None, None, "bot left guild", f"left guild id {guild.id} ({guild.name})", guild=guild, is_bot=True)

    # --- CHANNEL EVENTS ---
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: nextcord.abc.GuildChannel):
        """
        Event listener for channel creation. Logs the new channel ID and type.
        """
        what = "channel create"
        about = f"id {channel.id} ({channel.name}), type: {channel.type}"
        self._log_event(None, None, what, about, channel=channel)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: nextcord.abc.GuildChannel):
        """
        Event listener for channel deletion. Logs the deleted channel ID.
        """
        what = "channel delete"
        about = f"id {channel.id} ({channel.name})"
        self._log_event(None, None, what, about, channel=channel)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: nextcord.abc.GuildChannel, after: nextcord.abc.GuildChannel):
        """
        Event listener for channel updates. Specifically tracks and logs channel renames.
        """
        if before.name != after.name:
            what = "channel rename"
            about = f"channel {after.id}: from '{before.name}' to '{after.name}'"
            self._log_event(None, None, what, about, channel=after)

    # --- MEMBER EVENTS (TIMEOUTS / MODERATION) ---
    @commands.Cog.listener()
    async def on_member_join(self, member: nextcord.Member):
        """
        Event listener for a member joining the server.
        """
        what = "user join"
        about = f"joined guild id {member.guild.id}"
        self._log_event(member.id, member.name, what, about, guild=member.guild, is_bot=member.bot)

    @commands.Cog.listener()
    async def on_member_remove(self, member: nextcord.Member):
        """
        Event listener for a member leaving the server.
        """
        what = "user leave"
        about = f"left guild id {member.guild.id}"
        self._log_event(member.id, member.name, what, about, guild=member.guild, is_bot=member.bot)

    @commands.Cog.listener()
    async def on_member_update(self, before: nextcord.Member, after: nextcord.Member):
        # Tracking Timeouts (Communication Disabled)
        """
        Event listener for member updates. Tracks and logs moderation actions 
        specifically when a user is timed out (communication disabled) or when a timeout is removed.
        """
        if before.communication_disabled_until != after.communication_disabled_until:
            if after.communication_disabled_until:
                what = "timeout"
                about = f"user timed out until {after.communication_disabled_until}"
                self._log_event(after.id, after.name, what, about, guild=after.guild, is_bot=after.bot)
            else:
                what = "timeout remove"
                about = "user timeout removed"
                self._log_event(after.id, after.name, what, about, guild=after.guild, is_bot=after.bot)

    @commands.Cog.listener()
    async def on_member_ban(self, guild: nextcord.Guild, user: nextcord.User):
        """
        Event listener for when a member is banned from the server.
        """
        what = "ban"
        about = f"user {user.id} ({user.name}) was banned from guild {guild.id}"
        self._log_event(user.id, user.name, what, about, guild=guild, is_bot=user.bot)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: nextcord.Guild, user: nextcord.User):
        """
        Event listener for when a member is unbanned from the server.
        """
        what = "unban"
        about = f"user {user.id} ({user.name}) was unbanned from guild {guild.id}"
        self._log_event(user.id, user.name, what, about, guild=guild, is_bot=user.bot)

    # --- ROLE EVENTS ---
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: nextcord.Role):
        """
        Event listener for the creation of a new role in the server.
        """
        what = "role create"
        about = f"id {role.id} ({role.name}) on guild {role.guild.id}"
        self._log_event(None, None, what, about, guild=role.guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: nextcord.Role):
        """
        Event listener for the deletion of a role from the server.
        """
        what = "role delete"
        about = f"id {role.id} ({role.name}) on guild {role.guild.id}"
        self._log_event(None, None, what, about, guild=role.guild)

    # --- MESSAGE DELETE EVENTS ---
    @commands.Cog.listener()
    async def on_message_delete(self, message: nextcord.Message):
        """
        Event listener for a single message deletion. Logs the message ID and a snippet of its content.
        """
        what = "message delete"
        about = f"id: {message.id}, author: {message.author.id}, content: {message.content[:100]}"
        self._log_event(message.author.id, message.author.name, what, about, channel=message.channel, is_bot=message.author.bot)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[nextcord.Message]):
        """
        Event listener for bulk message deletions (e.g., from a purge command). 
        Logs the number of messages deleted.
        """
        if not messages:
            return
        channel = messages[0].channel
        what = "bulk message delete"
        about = f"count: {len(messages)} in channel {channel.id}"
        self._log_event(None, None, what, about, channel=channel)
