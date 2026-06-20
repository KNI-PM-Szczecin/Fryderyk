import nextcord
from nextcord.ext import commands
from datetime import datetime
from zoneinfo import ZoneInfo

class VoiceEventsCog(commands.Cog):
    """
    Discord Cog responsible for tracking and logging users' voice channel sessions.
    Calculates the duration spent in voice channels and records it in the database, 
    while respecting blacklist rules and ignoring AFK channels.
    """
    def __init__(self, client, config, database):
        """
        Initializes the VoiceEventsCog with the bot, config, and database connection.
        Sets up an internal dictionary to track ongoing voice sessions in memory.
        """
        self.client = client
        self.config = config
        self.database = database
        self.voice_start_times = {} # Key: (user_id, guild_id), Value: {start_time, channel}
        self.tz = ZoneInfo("Europe/Warsaw")

    def _process_voice_session(self, member, guild_id, session_data):
        """
        Calculates the duration of a closed voice session and logs it to the database.
        Checks against configured blacklists (channels and roles) before inserting.
        """
        start_time = session_data['start_time']
        channel = session_data['channel']

        # Check if channel is blacklisted
        if self.database.is_blacklisted(guild_id, channel.id):
            return

        # Check if any of member's roles are blacklisted
        if hasattr(member, 'roles'):
            for role in member.roles:
                if self.database.is_blacklisted(guild_id, role.id):
                    return
        
        # Current time in Polish timezone
        now = datetime.now(self.tz)
        duration = int((now - start_time).total_seconds())
        
        if duration > 0:
            category_id = channel.category.id if channel.category else None
            category_name = channel.category.name if channel.category else None
            
            self.database.put_voice(
                user_id=member.id,
                user_name=member.name,
                is_bot=member.bot,
                time_on=duration,
                date_join=start_time,
                channel_id=channel.id,
                channel_name=channel.name,
                guild_id=guild_id,
                guild_name=member.guild.name,
                category_id=category_id,
                category_name=category_name
            )

    @commands.Cog.listener()
    async def on_voice_state_update(self, member: nextcord.Member, before: nextcord.VoiceState, after: nextcord.VoiceState):
        """
        Event listener triggered whenever a user's voice state changes (join, leave, move, mute, etc).
        It manages the lifecycle of a voice session: tracking start times when joining a valid channel,
        and processing/saving the session when the user leaves, moves to another channel, or goes AFK.
        """
        user_id = member.id
        guild_id = member.guild.id
        session_key = (user_id, guild_id)
        afk_channel = member.guild.afk_channel

        # 1. User left a channel or moved to AFK
        if before.channel is not None and (after.channel is None or after.channel == afk_channel):
            session_data = self.voice_start_times.pop(session_key, None)
            if session_data:
                self._process_voice_session(member, guild_id, session_data)

        # 2. User joined a channel (not AFK)
        elif after.channel is not None and after.channel != afk_channel:
            # If they were already in a channel, close the previous session first
            if before.channel is not None:
                session_data = self.voice_start_times.pop(session_key, None)
                if session_data:
                    self._process_voice_session(member, guild_id, session_data)

            # Start new session with current Polish time
            self.voice_start_times[session_key] = {
                'start_time': datetime.now(self.tz),
                'channel': after.channel
            }
