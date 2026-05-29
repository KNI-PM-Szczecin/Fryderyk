import nextcord
from nextcord.ext import commands
from datetime import datetime
from zoneinfo import ZoneInfo

class GeneralEventsCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        self.tz = ZoneInfo("Europe/Warsaw")

    def _log_event(self, user_id, user_name, what, about, channel=None, guild=None, is_bot=False):
        channel_id = channel.id if channel else None
        channel_name = channel.name if channel else None
        category_id = channel.category.id if channel and hasattr(channel, 'category') and channel.category else None
        category_name = channel.category.name if channel and hasattr(channel, 'category') and channel.category else None
        guild_id = guild.id if guild else (channel.guild.id if channel else None)
        guild_name = guild.name if guild else (channel.guild.name if channel else None)

        # Current time in Polish timezone
        now = datetime.now(self.tz)

        self.database.put_event(
            user_id, user_name, is_bot, what, about, now, channel_id, channel_name,
            guild_id, guild_name, category_id, category_name
        )

    @commands.Cog.listener()
    async def on_ready(self):
        print(f"GeneralEventsCog: Bot is ready and listening for all events.")
        self._log_event(self.client.user.id, self.client.user.name, "bot start", f"logged in as {self.client.user}", is_bot=True)

    # --- REACTION EVENTS ---
    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: nextcord.RawReactionActionEvent):
        user = self.client.get_user(payload.user_id)
        user_name = user.name if user else f"Unknown({payload.user_id})"
        is_bot = user.bot if user else False
        guild = self.client.get_guild(payload.guild_id) if payload.guild_id else None

        what = "reaction"
        about = f"added {payload.emoji} to message id {payload.message_id}"
        self._log_event(payload.user_id, user_name, what, about, guild=guild, is_bot=is_bot)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: nextcord.RawReactionActionEvent):
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
        self._log_event(None, None, "bot joined guild", f"joined guild id {guild.id} ({guild.name})", guild=guild, is_bot=True)

    @commands.Cog.listener()
    async def on_guild_remove(self, guild: nextcord.Guild):
        self._log_event(None, None, "bot left guild", f"left guild id {guild.id} ({guild.name})", guild=guild, is_bot=True)

    # --- CHANNEL EVENTS ---
    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel: nextcord.abc.GuildChannel):
        what = "channel create"
        about = f"id {channel.id} ({channel.name}), type: {channel.type}"
        self._log_event(None, None, what, about, channel=channel)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel: nextcord.abc.GuildChannel):
        what = "channel delete"
        about = f"id {channel.id} ({channel.name})"
        self._log_event(None, None, what, about, channel=channel)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before: nextcord.abc.GuildChannel, after: nextcord.abc.GuildChannel):
        if before.name != after.name:
            what = "channel rename"
            about = f"channel {after.id}: from '{before.name}' to '{after.name}'"
            self._log_event(None, None, what, about, channel=after)

    # --- MEMBER EVENTS (TIMEOUTS / MODERATION) ---
    @commands.Cog.listener()
    async def on_member_join(self, member: nextcord.Member):
        what = "user join"
        about = f"joined guild id {member.guild.id}"
        self._log_event(member.id, member.name, what, about, guild=member.guild, is_bot=member.bot)

    @commands.Cog.listener()
    async def on_member_remove(self, member: nextcord.Member):
        what = "user leave"
        about = f"left guild id {member.guild.id}"
        self._log_event(member.id, member.name, what, about, guild=member.guild, is_bot=member.bot)

    @commands.Cog.listener()
    async def on_member_update(self, before: nextcord.Member, after: nextcord.Member):
        # Tracking Timeouts (Communication Disabled)
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
        what = "ban"
        about = f"user {user.id} ({user.name}) was banned from guild {guild.id}"
        self._log_event(user.id, user.name, what, about, guild=guild, is_bot=user.bot)

    @commands.Cog.listener()
    async def on_member_unban(self, guild: nextcord.Guild, user: nextcord.User):
        what = "unban"
        about = f"user {user.id} ({user.name}) was unbanned from guild {guild.id}"
        self._log_event(user.id, user.name, what, about, guild=guild, is_bot=user.bot)

    # --- ROLE EVENTS ---
    @commands.Cog.listener()
    async def on_guild_role_create(self, role: nextcord.Role):
        what = "role create"
        about = f"id {role.id} ({role.name}) on guild {role.guild.id}"
        self._log_event(None, None, what, about, guild=role.guild)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: nextcord.Role):
        what = "role delete"
        about = f"id {role.id} ({role.name}) on guild {role.guild.id}"
        self._log_event(None, None, what, about, guild=role.guild)

    # --- MESSAGE DELETE EVENTS ---
    @commands.Cog.listener()
    async def on_message_delete(self, message: nextcord.Message):
        what = "message delete"
        about = f"id: {message.id}, author: {message.author.id}, content: {message.content[:100]}"
        self._log_event(message.author.id, message.author.name, what, about, channel=message.channel, is_bot=message.author.bot)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages: list[nextcord.Message]):
        if not messages:
            return
        channel = messages[0].channel
        what = "bulk message delete"
        about = f"count: {len(messages)} in channel {channel.id}"
        self._log_event(None, None, what, about, channel=channel)
