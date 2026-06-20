import datetime
import random
import os
from zoneinfo import ZoneInfo

class DynamicProbability:
    """
    Manages a dynamically scaling probability system designed to guarantee events 
    (like random GIF reactions) over time. It increases the chance based on time elapsed 
    without an event, specific 'premium' hours, and custom consecutive day multipliers.
    """
    def __init__(self, base_sequence, premium_hours=None, premium_multiplier=2.0, reset_hour=4, daily_boost_multiplier=1.5):
        """
        Class for calculating dynamic probability.
        
        :param base_sequence: List of chances, e.g., [50, 75, 1000] means 1/50 for the first time, 
                              1/75 for the second time, and then 1/1000 for each subsequent time until reset.
        :param premium_hours: List of hours (0-23) during which the chance is increased (e.g., [18, 19, 20]).
        :param premium_multiplier: Multiplier for premium hours (e.g., 2.0 = 2x higher chance = chance denominator / 2).
        :param reset_hour: The hour when the counter resets to the beginning (e.g., 4 means 4:00 AM).
        :param daily_boost_multiplier: Multiplier applied for each consecutive day without a triggered GIF.
        """
        self.base_sequence = base_sequence
        self.premium_hours = premium_hours or []
        self.premium_multiplier = premium_multiplier
        self.reset_hour = reset_hour
        self.daily_boost_multiplier = daily_boost_multiplier
        
        # Get timezone from env or default to Europe/Warsaw according to bot's convention
        tz_str = os.getenv("TIMEZONE", "Europe/Warsaw")
        self.timezone = ZoneInfo(tz_str)
        
        self.trigger_count = 0
        self.days_without_trigger = 0
        self.last_reset_date = self._get_current_reset_date()

    def _get_current_reset_date(self):
        """Calculates the current 'reset date' based on the current time and reset hour."""
        now = datetime.datetime.now(self.timezone)
        if now.hour < self.reset_hour:
            # If we are before the reset hour, the reference date is still yesterday
            return (now - datetime.timedelta(days=1)).date()
        return now.date()

    def _check_reset(self):
        """Checks if the reset hour has passed since the last use and resets the counter if necessary."""
        current_reset_date = self._get_current_reset_date()
        if current_reset_date != self.last_reset_date:
            days_passed = (current_reset_date - self.last_reset_date).days
            if days_passed > 0:
                if self.trigger_count == 0:
                    self.days_without_trigger += days_passed
                else:
                    # If we had a trigger today, but multiple days passed (e.g., bot was offline),
                    # only the days after the trigger count as 'days without trigger'.
                    self.days_without_trigger = days_passed - 1
            
            self.trigger_count = 0
            self.last_reset_date = current_reset_date

    def get_current_chance(self, extra_multiplier=1.0):
        """
        Returns the current probability denominator (e.g., 50 for a 1/50 chance).
        Takes multipliers into account (premium hours and the one provided as an argument).
        """
        self._check_reset()
        
        if self.trigger_count < len(self.base_sequence):
            chance = self.base_sequence[self.trigger_count]
        else:
            chance = self.base_sequence[-1]
            
        now = datetime.datetime.now(self.timezone)
        
        # Intra-day growth for the first GIF to guarantee at least one trigger per day
        if self.trigger_count == 0:
            hours_passed = (now.hour - self.reset_hour) % 24
            # Smoothly reduce the chance denominator from its base value down to 2 over 23 hours
            max_reduction = chance - 2
            if max_reduction > 0:
                reduction = int(max_reduction * (hours_passed / 23.0))
                chance -= reduction
                chance = max(2, chance)
        
        multiplier = extra_multiplier
        
        if now.hour in self.premium_hours:
            multiplier *= self.premium_multiplier
            
        # Apply the boost for consecutive days without a trigger
        if self.days_without_trigger > 0:
            multiplier *= (self.daily_boost_multiplier ** self.days_without_trigger)
            
        # We decrease the chance denominator to increase the probability
        # e.g., chance = 50, multiplier = 2.0 -> final_chance = 25 (which means 1/25)
        final_chance = max(1, int(chance / multiplier))
        return final_chance

    def trigger(self):
        """Increases the counter after a successful event (e.g., a successful roll)."""
        self.trigger_count += 1

    def should_trigger(self, extra_multiplier=1.0):
        """
        Checks if the event should occur and increases the counter on success.
        Returns True if the event was rolled, False otherwise.
        """
        chance = self.get_current_chance(extra_multiplier)
        if random.randint(1, chance) == 1:
            self.trigger()
            return True
        return False
