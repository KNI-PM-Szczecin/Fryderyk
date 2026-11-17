import asyncio
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import nextcord
from nextcord import Interaction, SlashOption
from nextcord.ext import commands, tasks

TZ = ZoneInfo("Europe/Warsaw")
RUN_HOUR = 3   # daily review after 03:00 Warsaw, when nobody is chatting

# One "active day" per person per Warsaw calendar day: enough messages OR enough
# voice time that day. Counting days instead of messages rewards being around
# regularly rather than spamming. Humans only; blacklisted channels are not
# logged, so they don't count either.
ACTIVITY_SQL = """
WITH d AS (
    SELECT user_id, (date AT TIME ZONE 'Europe/Warsaw')::date AS day, count(*) AS msgs, 0::bigint AS secs
    FROM messages
    WHERE guild_id = %(g)s AND date >= %(since)s AND NOT is_bot AND NOT is_edited
    GROUP BY 1, 2
    UNION ALL
    SELECT user_id, (date_join AT TIME ZONE 'Europe/Warsaw')::date, 0, sum(time_on)::bigint
    FROM voice
    WHERE guild_id = %(g)s AND date_join >= %(since)s AND NOT is_bot
    GROUP BY 1, 2
), per_day AS (
    SELECT user_id, day, sum(msgs) AS msgs, sum(secs) AS secs FROM d GROUP BY 1, 2
)
SELECT user_id,
       count(*) FILTER (WHERE msgs >= %(min_msgs)s OR secs >= %(min_secs)s) AS days,
       sum(msgs) AS msgs,
       sum(secs) AS secs
FROM per_day GROUP BY user_id
"""


def _pl_days(n):
    return "1 dzień" if n == 1 else f"{n} dni"


class ActivityOrderCog(commands.Cog):
    """
    "Order aktywności": a Discord role handed out and taken back automatically
    based on activity over a rolling window (default: 30 days).

    * an active day = >= min_messages messages or >= min_voice_minutes on voice;
    * gain the role at >= gain_days active days, lose it below keep_days (the gap
      stops the role flapping after a few quiet days);
    * reviewed once a day after 03:00 Warsaw (or as soon as the bot is back if
      it was down then); changes are posted to the log channel without pings.

    Opt-in per guild: nothing happens until /order ustawienia sets a role
    (row in activity_order_settings). Gated by module `order`. The bot needs
    Manage Roles and its top role above the order role.
    """

    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        self._lock = asyncio.Lock()

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.daily.is_running():
            self.daily.start()

    def cog_unload(self):
        self.daily.cancel()

    # nextcord's tasks.loop(time=...) only accepts datetime.timezone (no DST), so
    # instead poll: once it is past RUN_HOUR in Warsaw and today's review hasn't
    # run, run it. This also catches up when the bot was down at 03:00.
    @tasks.loop(minutes=10)
    async def daily(self):
        now = datetime.now(TZ)
        if now.hour < RUN_HOUR:
            return
        for guild_id in await asyncio.to_thread(self.database.get_order_guilds):
            s = await asyncio.to_thread(self.database.get_order_settings, guild_id)
            last = s.get("last_run") if s else None
            if last is not None and last.astimezone(TZ).date() >= now.date():
                continue
            guild = self.client.get_guild(guild_id)
            if guild:
                await self._safe_review(guild)

    async def _safe_review(self, guild):
        try:
            await self.review(guild)
        except Exception as e:
            print(f"[order] review failed for {guild.id}: {type(e).__name__}: {e}")

    # --- core ---

    def _activity(self, guild_id, s):
        today = datetime.now(TZ).replace(hour=0, minute=0, second=0, microsecond=0)
        since = today - timedelta(days=int(s["window_days"]) - 1)   # window includes today
        rows = self.database.fetch_all_dict(ACTIVITY_SQL, {
            "g": guild_id, "since": since,
            "min_msgs": int(s["min_messages"]), "min_secs": int(s["min_voice_minutes"]) * 60,
        }, raise_errors=True)
        return {int(r["user_id"]): (int(r["days"]), int(r["msgs"]), int(r["secs"])) for r in rows}

    def _role_problem(self, guild, role):
        if role is None:
            return "nie znajduję roli orderu (ustaw ją przez `/order ustawienia rola:`)"
        me = guild.me
        if not me.guild_permissions.manage_roles:
            return "nie mam uprawnienia „Zarządzanie rolami”"
        if role >= me.top_role:
            return f"rola {role.mention} jest wyżej niż moja, przesuń moją rolę nad nią"
        if role.managed:
            return f"rola {role.mention} jest zarządzana przez integrację"
        return None

    async def plan(self, guild):
        """Returns (settings, role, activity, to_add, to_remove) without changing anything."""
        s = await asyncio.to_thread(self.database.get_order_settings, guild.id)
        if not s or not s.get("role_id"):
            raise ValueError("order nie jest skonfigurowany, użyj `/order ustawienia`")
        role = guild.get_role(int(s["role_id"]))
        act = await asyncio.to_thread(self._activity, guild.id, s)
        to_add, to_remove = [], []
        if role is not None:
            for m in guild.members:
                if m.bot:
                    continue
                days = act.get(m.id, (0, 0, 0))[0]
                has = role in m.roles
                if has and days < int(s["keep_days"]):
                    to_remove.append((m, days))
                elif not has and days >= int(s["gain_days"]):
                    to_add.append((m, days))
        to_add.sort(key=lambda x: -x[1])
        to_remove.sort(key=lambda x: x[1])
        return s, role, act, to_add, to_remove

    async def review(self, guild, dry_run=False):
        """Applies the plan; returns (added, removed, failed, problem)."""
        async with self._lock:
            if not self.database.is_module_enabled(guild.id, "order"):
                return [], [], [], "moduł `order` jest wyłączony"
            s, role, act, to_add, to_remove = await self.plan(guild)
            problem = self._role_problem(guild, role)
            if dry_run:
                return to_add, to_remove, [], problem
            if problem:
                await asyncio.to_thread(self.database.mark_order_run, guild.id)   # no repeat on every reconnect
                await self._post(guild, s, f"🎖️ **Order aktywności**: nie mogę zaktualizować roli, {problem}.")
                return [], [], [], problem

            window = int(s["window_days"])
            added, removed, failed = [], [], []
            for m, days in to_add:
                try:
                    await m.add_roles(role, reason=f"Order aktywności: {days} aktywnych dni w {window} dniach")
                    added.append((m, days))
                except nextcord.HTTPException as e:
                    failed.append((m, str(e)))
            for m, days in to_remove:
                try:
                    await m.remove_roles(role, reason=f"Order aktywności: tylko {days} aktywnych dni w {window} dniach")
                    removed.append((m, days))
                except nextcord.HTTPException as e:
                    failed.append((m, str(e)))
            await asyncio.to_thread(self.database.mark_order_run, guild.id)

            if added or removed or failed:
                lines = [f"🎖️ **Order aktywności**: przegląd z {datetime.now(TZ):%d.%m.%Y} (ostatnie {window} dni)"]
                if added:
                    lines.append("**Przyznany:** " + ", ".join(f"{m.mention} ({_pl_days(d)})" for m, d in added))
                if removed:
                    lines.append("**Odebrany:** " + ", ".join(f"{m.mention} ({_pl_days(d)})" for m, d in removed))
                if failed:
                    lines.append("**Nie udało się:** " + ", ".join(m.mention for m, _ in failed))
                lines.append(f"Order ma teraz {len(role.members)} os.")
                await self._post(guild, s, "\n".join(lines))
            return added, removed, failed, None

    async def _post(self, guild, s, text):
        cid = s.get("log_channel_id")
        channel = guild.get_channel(int(cid)) if cid else None
        if channel is None:
            print(f"[order] {guild.id}: {text}")
            return
        try:
            await channel.send(text[:2000], allowed_mentions=nextcord.AllowedMentions.none())
        except nextcord.HTTPException as e:
            print(f"[order] cannot post to {cid}: {e}")

    # --- commands (operator-only like every command) ---

    @nextcord.slash_command(name="order", description="Order aktywności",
                            contexts=[nextcord.InteractionContextType.guild])
    async def order(self, interaction: Interaction):
        pass

    @order.subcommand(name="status", description="Kto ma order, kto by go dostał lub stracił, kto jest blisko")
    async def status(self, interaction: Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            s, role, act, to_add, to_remove = await self.plan(interaction.guild)
        except Exception as e:
            await interaction.followup.send(f"Nie udało się: {e}", ephemeral=True)
            return
        gain, keep, window = int(s["gain_days"]), int(s["keep_days"]), int(s["window_days"])
        holders = [m for m in role.members if not m.bot] if role else []
        has_ids = {m.id for m in holders}
        near = sorted(((m, act.get(m.id, (0,))[0]) for m in interaction.guild.members
                       if not m.bot and m.id not in has_ids and gain - 3 <= act.get(m.id, (0,))[0] < gain),
                      key=lambda x: -x[1])
        cid = s.get("log_channel_id")
        problem = self._role_problem(interaction.guild, role)
        enabled = self.database.is_module_enabled(interaction.guild.id, "order")
        lines = [
            f"**Rola:** {role.mention if role else '—'} · **kanał:** {f'<#{cid}>' if cid else '—'}"
            + ("" if enabled else " · moduł `order` **wyłączony**"),
            f"**Zasady:** dzień aktywności = ≥{s['min_messages']} wiadomości albo ≥{s['min_voice_minutes']} min na voice; "
            f"order od {_pl_days(gain)} w ostatnich {window}, traci się poniżej {_pl_days(keep)}.",
            f"**Ma order ({len(holders)}):** " + (", ".join(
                f"{m.mention} {act.get(m.id, (0,))[0]}" for m in sorted(holders, key=lambda m: -act.get(m.id, (0,))[0])) or "nikt"),
            f"**Dostałby teraz ({len(to_add)}):** " + (", ".join(f"{m.mention} {d}" for m, d in to_add) or "nikt"),
            f"**Straciłby teraz ({len(to_remove)}):** " + (", ".join(f"{m.mention} {d}" for m, d in to_remove) or "nikt"),
            f"**Blisko:** " + (", ".join(f"{m.mention} {d}" for m, d in near[:15]) or "nikt"),
        ]
        if s.get("last_run"):
            lines.append(f"Ostatni przegląd: {s['last_run'].astimezone(TZ):%d.%m.%Y %H:%M}; następny o 3:00.")
        if problem:
            lines.append(f"⚠️ {problem}")
        await interaction.followup.send("\n".join(lines)[:2000], ephemeral=True,
                                        allowed_mentions=nextcord.AllowedMentions.none())

    @order.subcommand(name="przelicz", description="Przelicz order teraz (proba: tylko pokaż zmiany)")
    async def przelicz(
        self, interaction: Interaction,
        proba: bool = SlashOption(name="proba", description="Tylko pokaż, co by się zmieniło", required=False, default=False),
    ):
        await interaction.response.defer(ephemeral=True)
        try:
            added, removed, failed, problem = await self.review(interaction.guild, dry_run=proba)
        except Exception as e:
            await interaction.followup.send(f"Nie udało się: {e}", ephemeral=True)
            return
        head = "Próba, nic nie zmieniłem." if proba else "Gotowe."
        lines = [head,
                 f"**{'Dostałby' if proba else 'Przyznany'} ({len(added)}):** " + (", ".join(f"{m.mention} {d}" for m, d in added) or "nikt"),
                 f"**{'Straciłby' if proba else 'Odebrany'} ({len(removed)}):** " + (", ".join(f"{m.mention} {d}" for m, d in removed) or "nikt")]
        if failed:
            lines.append("**Nie udało się:** " + ", ".join(f"{m.mention} ({e[:60]})" for m, e in failed))
        if problem:
            lines.append(f"⚠️ {problem}")
        await interaction.followup.send("\n".join(lines)[:2000], ephemeral=True,
                                        allowed_mentions=nextcord.AllowedMentions.none())

    @order.subcommand(name="ustawienia", description="Rola, kanał i progi orderu")
    async def ustawienia(
        self, interaction: Interaction,
        rola: nextcord.Role = SlashOption(name="rola", description="Rola orderu", required=False, default=None),
        kanal: nextcord.abc.GuildChannel = SlashOption(name="kanal", description="Gdzie pisać o zmianach",
                                                       channel_types=[nextcord.ChannelType.text], required=False, default=None),
        zdobycie: int = SlashOption(name="zdobycie", description="Ile aktywnych dni, żeby dostać order",
                                    required=False, default=None, min_value=1, max_value=90),
        utrata: int = SlashOption(name="utrata", description="Poniżej ilu aktywnych dni order przepada",
                                  required=False, default=None, min_value=0, max_value=90),
        okno: int = SlashOption(name="okno", description="Z ilu ostatnich dni liczyć (domyślnie 30)",
                                required=False, default=None, min_value=7, max_value=90),
        wiadomosci: int = SlashOption(name="wiadomosci", description="Ile wiadomości robi dzień aktywnym (domyślnie 3)",
                                      required=False, default=None, min_value=1, max_value=50),
        voice: int = SlashOption(name="voice", description="Ile minut na voice robi dzień aktywnym (domyślnie 15)",
                                 required=False, default=None, min_value=1, max_value=240),
    ):
        current = await asyncio.to_thread(self.database.get_order_settings, interaction.guild.id) or {}
        gain = zdobycie if zdobycie is not None else current.get("gain_days", 8)
        keep = utrata if utrata is not None else current.get("keep_days", 4)
        window = okno if okno is not None else current.get("window_days", 30)
        if not keep <= gain <= window:
            await interaction.response.send_message(
                f"Progi muszą spełniać utrata ≤ zdobycie ≤ okno (teraz: {keep} ≤ {gain} ≤ {window}).", ephemeral=True)
            return
        if rola is not None and (rola.is_default() or rola.managed):
            await interaction.response.send_message("Tej roli nie mogę używać jako orderu.", ephemeral=True)
            return
        await asyncio.to_thread(
            self.database.put_order_settings, interaction.guild.id,
            role_id=rola.id if rola else None, log_channel_id=kanal.id if kanal else None,
            gain_days=zdobycie, keep_days=utrata, window_days=okno,
            min_messages=wiadomosci, min_voice_minutes=voice,
        )
        await interaction.response.send_message(
            "Zapisane. Sprawdź `/order status`, a `/order przelicz proba:True` pokaże zmiany przed pierwszym przeglądem.",
            ephemeral=True)
