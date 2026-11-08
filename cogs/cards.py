import asyncio
import io
import re
from datetime import datetime
from zoneinfo import ZoneInfo

import nextcord
from nextcord import Interaction, SlashOption
from nextcord.ext import commands, tasks

from decorators.cooldown import CogSharedCooldown
from utilities import wrapped
from utilities.cards import EmojiStore, clean_text, pl_date, render_quote, render_wrapped_server, render_wrapped_user

QUEUE_POLL_S = 3
KINDS = ("quote", "wrapped")
TZ = ZoneInfo("Europe/Warsaw")


def _norm(text):
    return re.sub(r"[^0-9a-ząćęłńóśźż]", "", (text or "").lower())


def _channel_label(channel):
    return "#" + (getattr(channel, "name", "") or "kanał").split("┃")[-1]


class CardsCog(commands.Cog):
    """
    Image cards drawn with Pillow (utilities/cards.py):

    * quote cards - the REAL text of a Discord message (never LLM-written) with
      the author's avatar: "Zacytuj" message context menu, or the agent's
      "Zrób cytat" tool ("@Fryderyk zacytuj to" in reply to a message);
    * semester / all-time summary ("Wrapped") - personal or server stats from
      the logs (utilities/wrapped.py): /podsumowanie, or the agent's
      "Podsumowanie semestru" tool. "calosc" = since the server was created.
      Anyone may see anyone's card (owner's call).

    Agent requests arrive through meme_requests (kind 'quote' / 'wrapped'); this
    cog only claims those kinds, MemeCog claims image/gif. Channel names and
    quoted text in summaries come only from channels @everyone can read, since
    the cards are posted publicly. Gated by modules `quote` and `wrapped`.
    """

    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        self.emojis = EmojiStore()
        self.agent_cooldown = CogSharedCooldown(rate=3, per=60.0)
        self.cooldown = CogSharedCooldown(rate=3, per=30.0)

    @commands.Cog.listener()
    async def on_ready(self):
        if not self.process_queue.is_running():
            self.process_queue.start()

    def cog_unload(self):
        self.process_queue.cancel()

    # --- shared ---

    def _q(self, sql, params):
        return self.database.fetch_all_dict(sql, params, raise_errors=True)

    @staticmethod
    async def _read(asset, size=256):
        try:
            return await asset.with_size(size).read() if asset else None
        except Exception:
            return None

    @staticmethod
    def _public_channel_ids(guild):
        everyone = guild.default_role
        ids = [c.id for c in guild.channels if c.permissions_for(everyone).view_channel]
        ids += [t.id for t in guild.threads if t.parent and t.parent.permissions_for(everyone).view_channel]
        return ids

    def _names(self, guild, ids):
        names, missing = {}, []
        for uid in ids:
            m = guild.get_member(int(uid))
            if m:
                names[int(uid)] = m.display_name
            else:
                missing.append(int(uid))
        if missing:
            for r in self.database.fetch_all_dict(
                "SELECT user_id, coalesce(global_name, name) AS n FROM users WHERE user_id = ANY(%s)", (missing,)
            ):
                names[int(r["user_id"])] = r["n"]
        return names

    def _resolve_member(self, guild, raw, requested_by):
        """'' -> requester; digits/mention -> that id; 'serwer' -> None; else best nick match."""
        raw = (raw or "").strip()
        if not raw or raw.lower() in ("ja", "mnie", "moje", "me"):
            return guild.get_member(int(requested_by)) if requested_by else None, False
        if _norm(raw) in ("serwer", "server", "kolo", "koło", "wszyscy"):
            return None, True
        if _norm(raw) in ("ty", "ciebie", "siebie", "bot", "fryderyk"):
            return guild.me, False
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 15:
            return guild.get_member(int(digits)), False
        key = _norm(raw.lstrip("@"))
        best = None
        for m in guild.members:
            if m.bot and m.id != guild.me.id:   # Fryderyk may have a card, other bots not
                continue
            for cand in (m.display_name, m.name, m.global_name):
                c = _norm(cand)
                if not c:
                    continue
                if c == key:
                    return m, False
                if key and key in c and best is None:
                    best = m
        return best, False

    async def build_quote(self, message):
        text = clean_text(message.clean_content or "")
        if not text and message.attachments:
            text = "📎"
        if not text:
            raise ValueError("w tej wiadomości nie ma tekstu do zacytowania")
        avatar = await self._read(message.author.display_avatar)
        footer = f"{pl_date(message.created_at.astimezone(TZ))} · {_channel_label(message.channel)}"
        await self.emojis.prefetch([text, message.author.display_name])
        return await asyncio.to_thread(render_quote, text, message.author.display_name, avatar, footer, self.emojis)

    @staticmethod
    def _period(guild, period):
        """'obecny' | 'poprzedni' | 'calosc' (whole history since the server was created)."""
        now = datetime.now(TZ)
        if period == "calosc":
            return wrapped.all_time(guild.created_at, now)
        sem = wrapped.semester_for(now.date())
        return wrapped.previous_semester(sem) if period == "poprzedni" else sem

    async def build_wrapped(self, guild, member, period="obecny"):
        """member None -> server card. Returns (png bytes, filename)."""
        sem = self._period(guild, period)
        what = "w historii serwera" if sem.all_time else f"w semestrze „{sem.name}”"
        public = self._public_channel_ids(guild)
        if member is None:
            s = await asyncio.to_thread(wrapped.server_stats, self._q, guild.id, sem, public)
            if not s["messages"]:
                raise ValueError(f"{what} nie ma jeszcze żadnych wiadomości")
            ids = [u for u, _ in s["top_talkers"]] + [u for u, _ in s["top_voice"]]
            ids += [s["night_owl"][0]] if s.get("night_owl") else []
            ids += [s["best_message"]["author"]] if s.get("best_message") else []
            ids += [s["first_message"]["user_id"]] if s.get("first_message") else []
            names = await asyncio.to_thread(self._names, guild, ids)
            await self.emojis.prefetch([e for e, _ in s["top_emoji"]] + [(s.get("best_message") or {}).get("message"),
                                       (s.get("first_message") or {}).get("message")] + list(names.values()))
            icon = await self._read(guild.icon)
            png = await asyncio.to_thread(render_wrapped_server, s, guild.name, icon, names, self.emojis)
            return png, "podsumowanie-serwera.png"

        if member.bot and member.id != guild.me.id:
            raise ValueError("boty nie mają podsumowań (poza mną)")
        s = await asyncio.to_thread(wrapped.user_stats, self._q, guild.id, member.id, sem, public)
        if not s["messages"]:
            raise ValueError(f"{member.display_name} nic nie napisał(a) {what}")
        names = await asyncio.to_thread(self._names, guild, [s["duo"][0]] if s.get("duo") else [])
        await self.emojis.prefetch([e for e, _ in s["top_emoji_received"]] + [(s.get("best_message") or {}).get("message"), member.display_name] + list(names.values()))
        avatar = await self._read(member.display_avatar)
        png = await asyncio.to_thread(render_wrapped_user, s, member.display_name, avatar, names, self.emojis, guild.name)
        return png, "podsumowanie.png"

    # --- operator entry points ---

    @nextcord.message_command(name="Zacytuj", contexts=[nextcord.InteractionContextType.guild])
    async def zacytuj(self, interaction: Interaction, message: nextcord.Message):
        if not self.database.is_module_enabled(interaction.guild.id, "quote"):
            await interaction.response.send_message("Moduł `quote` jest wyłączony (zobacz `/moduly status`).", ephemeral=True)
            return
        retry = self.cooldown.get_retry_after(interaction.guild_id)
        if retry is not None:
            await interaction.response.send_message(f"**Zwolnij!** Następna karta za **{round(retry, 1)}s**.", ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            png = await self.build_quote(message)
            await message.channel.send(
                file=nextcord.File(io.BytesIO(png), filename="cytat.png"),
                reference=message.to_reference(fail_if_not_exists=False),
                allowed_mentions=nextcord.AllowedMentions.none(),
            )
        except Exception as e:
            await interaction.followup.send(f"Nie udało się: {e}", ephemeral=True)
            return
        await interaction.followup.send("Gotowe.", ephemeral=True)

    @nextcord.slash_command(
        name="podsumowanie",
        description="Podsumowanie semestru albo całej historii: osoby lub całego serwera",
        contexts=[nextcord.InteractionContextType.guild],
    )
    async def podsumowanie(
        self,
        interaction: Interaction,
        kto: nextcord.Member = SlashOption(name="kto", description="Czyje podsumowanie (puste = całego serwera)", required=False, default=None),
        semestr: str = SlashOption(name="semestr", description="Który okres", required=False, default="obecny",
                                   choices={"Obecny semestr": "obecny", "Poprzedni semestr": "poprzedni",
                                            "Od początku serwera": "calosc"}),
    ):
        if not self.database.is_module_enabled(interaction.guild.id, "wrapped"):
            await interaction.response.send_message("Moduł `wrapped` jest wyłączony (zobacz `/moduly status`).", ephemeral=True)
            return
        await interaction.response.defer()
        try:
            png, name = await self.build_wrapped(interaction.guild, kto, semestr)
        except Exception as e:
            await interaction.followup.send(f"Nie udało się: {e}")
            return
        await interaction.followup.send(file=nextcord.File(io.BytesIO(png), filename=name))

    # --- agent queue ---

    @tasks.loop(seconds=QUEUE_POLL_S)
    async def process_queue(self):
        try:
            requests = await asyncio.to_thread(self.database.claim_meme_requests, 5, 10, KINDS)
        except Exception as e:
            print(f"[cards] queue poll failed: {e}")
            return
        for req in requests or []:
            try:
                status, error, posted_id = await self._handle(req)
            except Exception as e:
                status, error, posted_id = "failed", f"{type(e).__name__}: {e}", None
            if status != "done":
                print(f"[cards] request {req['id']} {status}: {error}")
            await asyncio.to_thread(self.database.finish_meme_request, req["id"], status, error, posted_id)

    async def _handle(self, req):
        guild_id, channel_id = int(req["guild_id"]), int(req["channel_id"])
        module = "quote" if req["kind"] == "quote" else "wrapped"
        if not self.database.is_module_enabled(guild_id, module):
            return "failed", "module disabled", None
        channel = self.client.get_channel(channel_id) or await self.client.fetch_channel(channel_id)
        guild = getattr(channel, "guild", None)
        if getattr(guild, "id", None) != guild_id:
            return "failed", "channel not in guild", None

        reference = None
        if req.get("reply_to_message_id"):
            reference = nextcord.MessageReference(
                message_id=int(req["reply_to_message_id"]), channel_id=channel_id,
                guild_id=guild_id, fail_if_not_exists=False,
            )
        no_pings = nextcord.AllowedMentions.none()

        async def visible_fail(why, note):
            await channel.send(f"({note})", reference=reference, allowed_mentions=no_pings)
            return "failed", why, None

        retry = self.agent_cooldown.get_retry_after(guild_id)
        if retry is not None:
            return await visible_fail("rate limited", f"za dużo kart naraz, poproś ponownie za {max(1, round(retry))} s")

        try:
            if req["kind"] == "quote":
                if not req.get("source_message_id"):
                    return await visible_fail("no source", "odpowiedz na wiadomość, którą mam zacytować")
                try:
                    source = await channel.fetch_message(int(req["source_message_id"]))
                except nextcord.NotFound:
                    return await visible_fail("source gone", "nie widzę już tej wiadomości")
                png, filename = await self.build_quote(source), "cytat.png"
            else:
                member, server = self._resolve_member(guild, req.get("target"), req.get("requested_by"))
                if member is None and not server:
                    return await visible_fail("unknown member", f"nie wiem, kto to „{str(req.get('target'))[:40]}”")
                png, filename = await self.build_wrapped(guild, member, req.get("semester") or "obecny")
        except ValueError as e:
            return await visible_fail("nothing to show", str(e))

        sent = await channel.send(file=nextcord.File(io.BytesIO(png), filename=filename),
                                  reference=reference, allowed_mentions=no_pings)
        return "done", None, sent.id
