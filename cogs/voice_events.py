import nextcord
from nextcord.ext import commands
from datetime import datetime
from zoneinfo import ZoneInfo

class VoiceEventsCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        self.voice_start_times = {} # Key: (user_id, guild_id), Value: {start_time, channel}
        self.tz = ZoneInfo("Europe/Warsaw")

    def _process_voice_session(self, member, guild_id, session_data):
        start_time = session_data['start_time']
        channel = session_data['channel']
        
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
