import time
import functools
import nextcord

class CogSharedCooldown:
    """
    A rate-limiting cooldown manager that supports a given rate (number of uses)
    per timeframe (per in seconds).
    """
    def __init__(self, rate: int, per: float):
        self.rate = rate
        self.per = per
        self._buckets = {}

    def get_retry_after(self, key: int):
        now = time.time()
        if key not in self._buckets:
            self._buckets[key] = [now]
            return None

        # Filter out timestamps that are older than the cooldown window
        self._buckets[key] = [t for t in self._buckets[key] if now - t < self.per]

        if len(self._buckets[key]) < self.rate:
            self._buckets[key].append(now)
            return None

        # Calculate time remaining until the oldest request expires from the window
        oldest = self._buckets[key][0]
        return self.per - (now - oldest)


def cog_cooldown(
    rate: int = None,
    per: float = None,
    message: str = "**Cooldown!** Fryderyk lubi wooolmo, poczekaj: **&value&s**.",
    per_guild: bool = True
):
    """
    Decorator to apply a cooldown to a slash command within a Cog.
    
    If rate and per are specified, it creates and uses a command-specific cooldown manager.
    Otherwise, it checks for a `cooldown_manager` attribute on the Cog instance.
    
    If per_guild is True and the command is invoked in a guild, the cooldown is shared 
    across all users in that guild. Otherwise, the cooldown is user-specific.
    """
    def decorator(func):
        @functools.wraps(func)
        async def wrapper(self, interaction: nextcord.Interaction, *args, **kwargs):
            # Determine which cooldown manager to use
            if rate is not None and per is not None:
                if not hasattr(self, "_dynamic_cooldown_managers"):
                    self._dynamic_cooldown_managers = {}
                
                manager_key = func.__name__
                if manager_key not in self._dynamic_cooldown_managers:
                    self._dynamic_cooldown_managers[manager_key] = CogSharedCooldown(rate, per)
                
                manager = self._dynamic_cooldown_managers[manager_key]
            else:
                manager = getattr(self, "cooldown_manager", None)

            if not manager:
                return await func(self, interaction, *args, **kwargs)

            # Determine key (guild ID if per_guild and in a guild, user ID otherwise)
            if per_guild and interaction.guild_id:
                bucket_key = interaction.guild_id
            else:
                bucket_key = interaction.user.id

            retry_after = manager.get_retry_after(bucket_key)

            if retry_after:
                parsed_message = message.replace("&value&", f"{retry_after:.1f}")

                # Check if interaction has already been deferred or responded to
                if interaction.response.is_done():
                    return await interaction.followup.send(parsed_message, ephemeral=True)
                else:
                    return await interaction.response.send_message(parsed_message, ephemeral=True)

            return await func(self, interaction, *args, **kwargs)
        return wrapper
    return decorator
