import asyncio
import time
import nextcord
from nextcord.ext import commands
from nextcord import Interaction
from zoneinfo import ZoneInfo
from utilities.baseUtils import DiscordUtils

MAX_REACTIONS_PER_MESSAGE = 50
YIELD_EVERY_N_MESSAGES = 50
PROGRESS_EDIT_INTERVAL_S = 3.0


class HistoryBackfillCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        self.tz = ZoneInfo(config.get_timezone())

    @nextcord.slash_command(
        name="backfill_history",
        description="Backfills message history and reactions into the database (Admin only)",
        default_member_permissions=nextcord.Permissions(administrator=True)
    )
    async def backfill_history(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)

        guild = interaction.guild
        if not guild:
            await interaction.followup.send(
                "This command can only be used in a guild.",
                ephemeral=True,
            )
            return

        target_channels = [
            c for c in guild.channels
            if isinstance(c, (nextcord.TextChannel, nextcord.Thread))
        ]
        total_channels = len(target_channels)

        progress_msg = await interaction.followup.send(
            f"Starting backfill for {total_channels} channels...",
            ephemeral=True,
            wait=True,
        )

        total_messages = 0
        total_skipped = 0
        total_reactions = 0
        channels_done = 0      # every channel iterated (drives %)
        channels_processed = 0  # channels actually walked (skip perm-less / errored)
        last_edit_at = 0.0

        async def push_progress(current_channel_name, per_channel_inserted, per_channel_skipped, force=False):
            nonlocal last_edit_at
            now_t = time.monotonic()
            if not force and (now_t - last_edit_at) < PROGRESS_EDIT_INTERVAL_S:
                return
            pct = (channels_done / total_channels * 100) if total_channels else 100.0
            text = (
                f"Backfill in progress... **{pct:.1f}%**\n"
                f"- Channels: {channels_done}/{total_channels}\n"
                f"- Current: #{current_channel_name or '-'} "
                f"({per_channel_inserted} new, {per_channel_skipped} skipped)\n"
                f"- Running total: {total_messages} new, {total_skipped} skipped, "
                f"{total_reactions} reactions"
            )
            try:
                await progress_msg.edit(content=text)
                last_edit_at = now_t
            except Exception as e:
                # Edit failures (rate limit, expired interaction token) are non-fatal.
                print(f"[Backfill] Progress edit failed: {e}")

        for channel in target_channels:
            # Skip blacklisted channels
            is_blacklisted = await asyncio.to_thread(
                self.database.is_blacklisted, guild.id, channel.id
            )
            if is_blacklisted:
                channels_done += 1
                continue

            per_channel_inserted = 0
            per_channel_skipped = 0
            walked = False
            try:
                if not channel.permissions_for(guild.me).read_message_history:
                    continue

                walked = True
                async for message in channel.history(limit=None, oldest_first=True):
                    already_in_db = await asyncio.to_thread(
                        self.database.message_exists, message.id
                    )
                    if already_in_db:
                        per_channel_skipped += 1
                        total_skipped += 1
                        if (per_channel_inserted + per_channel_skipped) % YIELD_EVERY_N_MESSAGES == 0:
                            await asyncio.sleep(0)
                            await push_progress(channel.name, per_channel_inserted, per_channel_skipped)
                        continue

                    parsed_content = DiscordUtils.parse_mentions(message)

                    category_id = None
                    category_name = None
                    if hasattr(channel, 'category') and channel.category:
                        category_id = channel.category.id
                        category_name = channel.category.name

                    polish_date = message.created_at.astimezone(self.tz)
                    edit_date = message.edited_at.astimezone(self.tz) if message.edited_at else None

                    await asyncio.to_thread(
                        self.database.put_message,
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
                    per_channel_inserted += 1
                    total_messages += 1

                    # Cap reactions per message — we don't need every reactor for analytics
                    # and full enumeration triggers heavy Discord pagination + rate limits.
                    reactions_logged = 0
                    for reaction in message.reactions:
                        if reactions_logged >= MAX_REACTIONS_PER_MESSAGE:
                            break
                        try:
                            async for user in reaction.users():
                                if reactions_logged >= MAX_REACTIONS_PER_MESSAGE:
                                    break
                                await asyncio.to_thread(
                                    self.database.put_event,
                                    user_id=user.id,
                                    user_name=user.name,
                                    is_bot=user.bot,
                                    what="reaction (backfilled)",
                                    about=f"reacted {reaction.emoji} to message id {message.id} (date unknown)",
                                    date=None,
                                    channel_id=channel.id,
                                    channel_name=channel.name,
                                    guild_id=guild.id,
                                    guild_name=guild.name,
                                    category_id=category_id,
                                    category_name=category_name
                                )
                                reactions_logged += 1
                                total_reactions += 1
                        except Exception as e:
                            print(f"[Backfill] Error fetching reaction users for msg {message.id}: {e}")

                    if (per_channel_inserted + per_channel_skipped) % YIELD_EVERY_N_MESSAGES == 0:
                        await asyncio.sleep(0)
                        await push_progress(channel.name, per_channel_inserted, per_channel_skipped)

                if walked:
                    channels_processed += 1
                print(
                    f"[Backfill] Finished #{channel.name} "
                    f"({per_channel_inserted} new, {per_channel_skipped} skipped; "
                    f"running total: {total_messages} new, {total_skipped} skipped)"
                )

            except Exception as e:
                print(f"[Backfill] Error processing channel {channel.name}: {e}")
            finally:
                channels_done += 1
                await push_progress(channel.name, per_channel_inserted, per_channel_skipped, force=True)

        final_text = (
            f"Backfill complete! **100%**\n"
            f"- Channels processed: {channels_processed}/{total_channels}\n"
            f"- Messages inserted: {total_messages}\n"
            f"- Messages skipped (already in DB): {total_skipped}\n"
            f"- Reactions logged: {total_reactions} "
            f"(capped at {MAX_REACTIONS_PER_MESSAGE} per message)"
        )
        try:
            await progress_msg.edit(content=final_text)
        except Exception as e:
            print(f"[Backfill] Final edit failed ({e}), trying followup.")
            try:
                await interaction.followup.send(final_text, ephemeral=True)
            except Exception as e2:
                print(f"[Backfill] Final followup also failed ({e2}). Summary: {final_text}")
