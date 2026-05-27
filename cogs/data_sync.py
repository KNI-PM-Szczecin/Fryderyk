import nextcord
from nextcord.ext import commands

class DataSyncCog(commands.Cog):
    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database

    async def _sync_user(self, member: nextcord.Member):
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

    async def _sync_guild(self, guild: nextcord.Guild):
        """Ensures guild information is up to date."""
        self.database.put_guild(guild.id, guild.name)

    async def _sync_roles(self, guild: nextcord.Guild):
        """Syncs all roles for a guild, ensuring roles removed in Discord are also handled if needed."""
        # Note: Current Database class doesn't have a clear_guild_roles, 
        # but we ensure all existing roles are present/updated.
        for role in guild.roles:
            self.database.put_role(role.id, guild.id, role.name)

    async def _sync_user_roles(self, member: nextcord.Member):
        """Syncs roles for a specific member, clearing old ones first for accuracy."""
        self.database.clear_user_roles(member.id)
        for role in member.roles:
            if role.is_default(): # Skip @everyone
                continue
            self.database.put_user_role(member.id, role.id)

    async def catch_up(self):
        """Performs a full synchronization to catch up with changes while the bot was offline."""
        print("DataSyncCog: Starting startup catch-up (validation)...")
        for guild in self.client.guilds:
            await self._sync_guild(guild)
            await self._sync_roles(guild)
            for member in guild.members:
                await self._sync_user(member)
                await self._sync_user_roles(member)
        print("DataSyncCog: Startup catch-up complete.")

    @commands.Cog.listener()
    async def on_ready(self):
        # Initial catch-up on startup
        await self.catch_up()

    # --- Runtime Data Integrity Listeners ---

    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        """Perform a full sync for a new guild the bot just joined."""
        await self._sync_guild(guild)
        await self._sync_roles(guild)
        for member in guild.members:
            await self._sync_user(member)
            await self._sync_user_roles(member)

    @commands.Cog.listener()
    async def on_guild_update(self, before: nextcord.Guild, after: nextcord.Guild):
        """Keep guild info in sync when it changes."""
        if before.name != after.name:
            await self._sync_guild(after)

    @commands.Cog.listener()
    async def on_member_join(self, member: nextcord.Member):
        """Sync new member data immediately."""
        await self._sync_user(member)
        await self._sync_user_roles(member)

    @commands.Cog.listener()
    async def on_member_remove(self, member: nextcord.Member):
        """Clear roles for a member who left."""
        self.database.clear_user_roles(member.id)

    @commands.Cog.listener()
    async def on_member_update(self, before: nextcord.Member, after: nextcord.Member):
        """Keep member roles and info in sync during runtime."""
        if before.roles != after.roles:
            await self._sync_user_roles(after)
        
        if (before.name != after.name or 
            getattr(before, 'global_name', None) != getattr(after, 'global_name', None) or
            before.avatar != after.avatar):
            await self._sync_user(after)

    @commands.Cog.listener()
    async def on_guild_join(self, guild: nextcord.Guild):
        """Perform a full sync for a new guild the bot just joined."""
        await self._sync_guild(guild)
        await self._sync_roles(guild)
        for member in guild.members:
            await self._sync_user(member)
            await self._sync_user_roles(member)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role: nextcord.Role):
        self.database.put_role(role.id, role.guild.id, role.name)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role: nextcord.Role):
        self.database.delete_role(role.id)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before: nextcord.Role, after: nextcord.Role):
        if before.name != after.name:
            self.database.put_role(after.id, after.guild.id, after.name)

    @commands.Cog.listener()
    async def on_user_update(self, before: nextcord.User, after: nextcord.User):
        """Sync global user changes."""
        self.database.put_user(
            after.id, 
            after.name, 
            getattr(after, 'global_name', after.display_name), 
            after.bot, 
            after.created_at, 
            str(after.avatar.url) if after.avatar else None,
            str(after.banner.url) if after.banner else None,
            after.public_flags.value
        )
