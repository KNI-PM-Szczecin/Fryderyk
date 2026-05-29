import nextcord
from nextcord.ext import commands
from nextcord import Interaction, SlashOption
from zoneinfo import ZoneInfo
from datetime import datetime
from utilities.baseUtils import DiscordUtils

class HistoryBackfillCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        self.tz = ZoneInfo("Europe/Warsaw")

    @nextcord.slash_command(
        name="backfill_history",
        description="Backfills message history and reactions into the database (Admin only)",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def backfill_history(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        
        guild = interaction.guild
        if not guild:
            await interaction.followup.send("This command can only be used in a guild.")
            return

        total_messages = 0
        total_reactions = 0
        channels_processed = 0

        # Iterate over all text channels and threads
        target_channels = [c for c in guild.channels if isinstance(c, (nextcord.TextChannel, nextcord.Thread, nextcord.VoiceChannel))]
        
        await interaction.followup.send(f"Starting backfill for {len(target_channels)} channels. This may take a while...")

        for channel in target_channels:
            try:
                # Check permissions to read history
                if not channel.permissions_for(guild.me).read_message_history:
                    continue

                async for message in channel.history(limit=None, oldest_first=True):
                    # 1. Log Message
                    parsed_content = DiscordUtils.parse_mentions(message)
                    
                    category_id = None
                    category_name = None
                    if hasattr(channel, 'category') and channel.category:
                        category_id = channel.category.id
                        category_name = channel.category.name

                    # Convert UTC time to Polish timezone
                    polish_date = message.created_at.astimezone(self.tz)
                    edit_date = message.edited_at.astimezone(self.tz) if message.edited_at else None

                    self.database.put_message(
                        discord_id=message.id,
                        user_id=message.author.id,
                        user_name=message.author.name,
                        message=parsed_content,
                        is_edited=bool(message.edited_at),
                        is_bot=message.author.bot,
                        date=polish_date,
                        edit_date=edit_date,
                        channel_id=channel.id,
                        channel_name=channel.name,
                        guild_id=guild.id,
                        guild_name=guild.name,
                        category_id=category_id,
                        category_name=category_name
                    )
                    total_messages += 1

                    # 2. Log Reactions as Events (if they can't be handled precisely, date is null)
                    for reaction in message.reactions:
                        try:
                            async for user in reaction.users():
                                self.database.put_event(
                                    user_id=user.id,
                                    user_name=user.name,
                                    is_bot=user.bot,
                                    what="reaction (backfilled)",
                                    about=f"reacted {reaction.emoji} to message id {message.id} (date unknown)",
                                    date=None, # Date unknown from history
                                    channel_id=channel.id,
                                    channel_name=channel.name,
                                    guild_id=guild.id,
                                    guild_name=guild.name,
                                    category_id=category_id,
                                    category_name=category_name
                                )
                                total_reactions += 1
                        except Exception as e:
                            print(f"[Backfill] Error fetching reaction users for msg {message.id}: {e}")

                channels_processed += 1
                print(f"[Backfill] Finished #{channel.name} ({total_messages} messages so far)")

            except Exception as e:
                print(f"[Backfill] Error processing channel {channel.name}: {e}")

        await interaction.followup.send(
            f"Backfill complete!\n"
            f"- Channels processed: {channels_processed}\n"
            f"- Messages logged: {total_messages}\n"
            f"- Reactions logged: {total_reactions}"
        )
