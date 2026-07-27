import asyncio
import nextcord
from nextcord.ext import commands

class DataSyncCog(commands.Cog):
    """
    Discord Cog responsible for synchronizing bot state (guilds, members, roles)
    with the local database. Runs an initial catch-up on startup and listens to
    various Discord events to maintain data integrity in real-time.

    All DB writes are synchronous psycopg2 calls, so the helpers below are plain
    functions and every listener dispatches them through asyncio.to_thread —
    otherwise a large sweep (startup catch-up, guild join) would block the
    Discord heartbeat.
    """
    def __init__(self, client, config, database):
        """
        Initializes the DataSyncCog with bot instance, config, and database connection.
        """
        self.client = client
        self.config = config
        self.database = database
        self._catch_up_done = False

    def _sync_user(self, member: nextcord.Member):
        """Ensures user information is up to date in the database."""
        self.database.put_user(
            member.id,
            member.name,
            getattr(member, 'global_name', member.display_name),
            member.bot,
            member.created_at,
            str(member.avatar.url) if member.avatar else None,
            str(member.banner.url) if member.banner else None,
            member.public_flags.value
        )

    def _sync_guild(self, guild: nextcord.Guild):
        """Ensures guild information is up to date."""
        self.database.put_guild(guild.id, guild.name)

    def _sync_roles(self, guild: nextcord.Guild):
        """Syncs all roles for a guild, ensuring roles removed in Discord are also handled if needed."""
        for role in guild.roles:
            self.database.put_role(role.id, guild.id, role.name)

    def _sync_user_roles(self, member: nextcord.Member):
        """
        Syncs roles for a specific member, clearing old ones first for accuracy.
        The clear is scoped to this guild — the same user may be on other guilds
        the bot serves, and their roles there must not be wiped by this sweep.
        """
        self.database.clear_user_roles(member.id, member.guild.id)
        for role in member.roles:
            if role.is_default(): # Skip @everyone
                continue
            self.database.put_user_role(member.id, role.id)

    def _sync_guild_full(self, guild: nextcord.Guild):
        """Full sync of a single guild: its info, roles, and every member."""
        self._sync_guild(guild)
        self._sync_roles(guild)
        for member in list(guild.members):
            self._sync_user(member)
            self._sync_user_roles(member)

    def _catch_up(self):
        """Performs a full synchronization to catch up with changes while the bot was offline."""
        print("DataSyncCog: Starting startup catch-up (validation)...")
        for guild in list(self.client.guilds):
            self._sync_guild_full(guild)
        print("DataSyncCog: Startup catch-up complete.")

    @commands.Cog.listener()
    async def on_ready(self):
        """
        Triggered when the bot connects to Discord. Initiates the global data
        catch-up process once per process — on_ready fires again on every
        reconnect and the full sweep must not be repeated.
        """
        if self._catch_up_done:
            return
        self._catch_up_done = True
        await asyncio.to_thread(self._catch_up)

    # --- Runtime Data Integrity Listeners ---

    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        """Perform a full sync for a new guild the bot just joined."""
        await asyncio.to_thread(self._sync_guild_full, guild)

    @commands.Cog.listener()
    async def on_guild_update(self, before: nextcord.Guild, after: nextcord.Guild):
        """Keep guild info in sync when it changes."""
        if before.name != after.name:
            await asyncio.to_thread(self._sync_guild, after)

    @commands.Cog.listener()
    async def on_member_join(self, member: nextcord.Member):
        """Sync new member data immediately."""
        await asyncio.to_thread(self._sync_user, member)
        await asyncio.to_thread(self._sync_user_roles, member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: nextcord.Member):
        """Clear this guild's roles for a member who left (other guilds keep theirs)."""
        await asyncio.to_thread(self.database.clear_user_roles, member.id, member.guild.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: nextcord.Member, after: nextcord.Member):
        """Keep member roles and info in sync during runtime."""
        if before.roles != after.roles:
            await asyncio.to_thread(self._sync_user_roles, after)

        if (before.name != after.name or
            getattr(before, 'global_name', None) != getattr(after, 'global_name', None) or
            before.avatar != after.avatar):
            await asyncio.to_thread(self._sync_user, after)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: nextcord.Role):
        """
        Listens for newly created roles in a guild and inserts them into the database.
        """
        await asyncio.to_thread(self.database.put_role, role.id, role.guild.id, role.name)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: nextcord.Role):
        """
        Listens for role deletions in a guild and removes them from the database.
        """
        await asyncio.to_thread(self.database.delete_role, role.id)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: nextcord.Role, after: nextcord.Role):
        """
        Listens for role updates in a guild and syncs changes (like name edits) to the database.
        """
        if before.name != after.name:
            await asyncio.to_thread(self.database.put_role, after.id, after.guild.id, after.name)

    @commands.Cog.listener()
    async def on_user_update(self, before: nextcord.User, after: nextcord.User):
        """Sync global user changes."""
        await asyncio.to_thread(self._sync_user, after)
