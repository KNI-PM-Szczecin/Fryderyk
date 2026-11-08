import asyncio
import io

import nextcord
from nextcord import Interaction, SlashOption
from nextcord.ext import commands, tasks

from decorators.cooldown import CogSharedCooldown
from utilities.gif import KlipyClient, caption_media, download, load_frames
from utilities.meme import MemeCatalog

MAX_TEXT = 150
COOLDOWN_MSG = "**Zwolnij!** Następny mem za **{s}s**."
QUEUE_POLL_S = 3
DEFAULT_UPLOAD_LIMIT = 10 * 1024 * 1024
MEDIA_TYPES = ("image/", "video/")


class MemeModal(nextcord.ui.Modal):
    """One text field per caption box of the chosen template."""

    def __init__(self, cog, template):
        super().__init__(title=f"Mem: {template.name}"[:45])
        self.cog = cog
        self.template = template
        self._inputs = []
        for i, box in enumerate(template.boxes):
            field = nextcord.ui.TextInput(
                label=(box.hint or f"Pole {i + 1}")[:45],
                style=nextcord.TextInputStyle.short,
                max_length=MAX_TEXT,
                required=False,
            )
            self._inputs.append(field)
            self.add_item(field)

    async def callback(self, interaction: Interaction):
        texts = [(f.value or "").strip() for f in self._inputs]
        await self.cog.send_meme(interaction, self.template, texts)


class CaptionModal(nextcord.ui.Modal):
    """Single caption for the 'Podpisz GIF-a' message context menu."""

    def __init__(self, cog, message):
        super().__init__(title="Podpisz GIF-a")
        self.cog = cog
        self.message = message
        self.text = nextcord.ui.TextInput(
            label="Podpis (nad GIF-em)",
            style=nextcord.TextInputStyle.short,
            max_length=MAX_TEXT,
            required=True,
        )
        self.add_item(self.text)

    async def callback(self, interaction: Interaction):
        await self.cog.caption_message(interaction, self.message, self.text.value or "")


def media_urls(message):
    """Animated/static media in a message: attachments first, then link embeds
    (Tenor/KLIPY/Giphy links unfurl as 'gifv' embeds whose video is an MP4)."""
    urls = []
    for a in message.attachments:
        if (a.content_type or "").startswith(MEDIA_TYPES):
            urls.append(a.url)
    for e in message.embeds:
        for part in (e.video, e.image, e.thumbnail):
            url = getattr(part, "url", None)
            if url and url not in urls:
                urls.append(url)
    return urls


def upload_limit(guild):
    """Bytes we may upload here, with headroom (boosted guilds allow more)."""
    limit = getattr(guild, "filesize_limit", None) or DEFAULT_UPLOAD_LIMIT
    return int(limit * 0.95)


class MemeCog(commands.Cog):
    """
    Memes without image generation. Two kinds share one queue and one cog:

    * image memes - Imgflip templates with text in hand-measured boxes
      (utilities/meme.py): /mem, or the agent's "Zrób mema" tool;
    * GIF memes - a white caption bar above any animation (utilities/gif.py).
      The gif comes from a KLIPY search, an attachment or a link embed: /gif,
      the "Podpisz GIF-a" message context menu, or the agent's "Zrób gifa" tool.

    The agent tools (n8n "Wypowiedz sie") only INSERT into meme_requests; this
    cog polls every QUEUE_POLL_S seconds, claims rows atomically, renders and
    replies to the message that asked. Rows with repeat_of re-post an older meme
    (same template/captions, or the same recorded gif URL).

    Everything is gated per guild by the `meme` module; slash and context-menu
    commands are operator-only like every command.
    """

    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        self.catalog = MemeCatalog()
        key = config.get_klipy_key() if hasattr(config, "get_klipy_key") else ""
        self.klipy = KlipyClient(key)
        # Per guild (multi-guild invariant): 3 memes per 30 s per server, and a
        # separate budget for the agent so a looping LLM can't flood a channel.
        self.cooldown = CogSharedCooldown(rate=3, per=30.0)
        self.agent_cooldown = CogSharedCooldown(rate=3, per=60.0)

    @commands.Cog.listener()
    async def on_ready(self):
        # on_ready fires on every reconnect: the loop guard keeps one poller, and
        # templates() is a no-op while the cache is fresh.
        if not self.process_queue.is_running():
            self.process_queue.start()
        if not self.klipy.enabled:
            print("[meme] KLIPY_API_KEY not set - GIF search disabled")
        try:
            await self.catalog.templates()
        except Exception as e:
            print(f"[meme] catalog preload failed: {e}")

    def cog_unload(self):
        self.process_queue.cancel()

    # --- shared helpers ---

    def _module_off(self, guild_id):
        return not self.database.is_module_enabled(guild_id, "meme")

    async def render_gif(self, url_candidates, text, max_bytes):
        """Downloads the first decodable candidate and captions it. Returns (bytes, ext, url)."""
        last = None
        for url in url_candidates:
            try:
                data = await download(url)
                frames, durations = await asyncio.to_thread(load_frames, data)
                out, ext = await asyncio.to_thread(caption_media, frames, durations, text, max_bytes)
                return out, ext, url
            except Exception as e:
                last = e
        raise RuntimeError(f"no usable media ({type(last).__name__ if last else 'none found'})")

    async def search_gif(self, query, guild_id):
        items = await self.klipy.search(query, customer_id=f"guild-{guild_id}")
        url = KlipyClient.pick_url(items)
        if not url:
            raise LookupError("no gif found")
        return url

    # --- /mem (image templates) ---

    @nextcord.slash_command(
        name="mem",
        description="Zrób mema z szablonu Imgflip",
        contexts=[nextcord.InteractionContextType.guild],
    )
    async def mem(
        self,
        interaction: Interaction,
        szablon: str = SlashOption(
            name="szablon",
            description="Szablon mema (zacznij pisać, np. drake, gru, brain)",
            required=True,
            autocomplete=True,
        ),
    ):
        if self._module_off(interaction.guild.id):
            await interaction.response.send_message(
                "Moduł `meme` jest obecnie wyłączony (zobacz `/moduly status`).",
                ephemeral=True,
            )
            return

        # A modal must be the *first* response, within 3 s, so we cannot defer.
        # Normally the catalog is already cached; on a cold cache give it ~2 s.
        try:
            template = await asyncio.wait_for(self.catalog.resolve(szablon), timeout=2.0)
        except Exception as e:
            await interaction.response.send_message(
                f"Nie udało się pobrać listy szablonów z Imgflip ({type(e).__name__}). Spróbuj za chwilę.",
                ephemeral=True,
            )
            return

        if template is None:
            await interaction.response.send_message(
                f"Nie znam szablonu `{szablon}`. Wybierz z podpowiedzi.",
                ephemeral=True,
            )
            return

        await interaction.response.send_modal(MemeModal(self, template))

    @mem.on_autocomplete("szablon")
    async def mem_autocomplete(self, interaction: Interaction, szablon: str):
        templates = self.catalog.cached_templates()
        if not templates:
            try:
                await asyncio.wait_for(self.catalog.templates(), timeout=2.0)
            except Exception:
                await interaction.response.send_autocomplete({})
                return
        choices = {
            f"{t.name} ({len(t.boxes)} pola)"[:100]: t.id
            for t in self.catalog.search(szablon, limit=25)
        }
        await interaction.response.send_autocomplete(choices)

    async def send_meme(self, interaction: Interaction, template, texts):
        """Renders and posts the meme in reply to a (modal) interaction."""
        if not any(texts):
            await interaction.response.send_message("Pusty mem? Wpisz chociaż jeden podpis.", ephemeral=True)
            return

        retry = self.cooldown.get_retry_after(interaction.guild_id or interaction.user.id)
        if retry is not None:
            await interaction.response.send_message(COOLDOWN_MSG.format(s=round(retry, 1)), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            data = await self.catalog.render(template, texts)
        except Exception as e:
            print(f"[meme] render failed for {template.id}: {e}")
            await interaction.followup.send(f"Nie udało się zrobić mema: {type(e).__name__}.")
            return

        await interaction.followup.send(file=nextcord.File(io.BytesIO(data), filename="mem.jpg"))

    # --- /gif and "Podpisz GIF-a" ---

    @nextcord.slash_command(
        name="gif",
        description="Podpisany GIF: z wyszukiwarki KLIPY albo z załączonego pliku",
        contexts=[nextcord.InteractionContextType.guild],
    )
    async def gif(
        self,
        interaction: Interaction,
        tekst: str = SlashOption(name="tekst", description="Podpis nad GIF-em", required=True, max_length=MAX_TEXT),
        fraza: str = SlashOption(
            name="fraza", description="Czego szukać w KLIPY (najlepiej po angielsku, np. 'this is fine')",
            required=False, default=None, max_length=100,
        ),
        plik: nextcord.Attachment = SlashOption(
            name="plik", description="Własny GIF/obrazek/MP4 zamiast wyszukiwania", required=False, default=None,
        ),
    ):
        if self._module_off(interaction.guild.id):
            await interaction.response.send_message(
                "Moduł `meme` jest obecnie wyłączony (zobacz `/moduly status`).", ephemeral=True)
            return
        if not fraza and not plik:
            await interaction.response.send_message("Podaj `fraza` albo `plik`.", ephemeral=True)
            return
        if plik and not (plik.content_type or "").startswith(MEDIA_TYPES):
            await interaction.response.send_message("To nie wygląda na GIF, obrazek ani wideo.", ephemeral=True)
            return
        retry = self.cooldown.get_retry_after(interaction.guild_id)
        if retry is not None:
            await interaction.response.send_message(COOLDOWN_MSG.format(s=round(retry, 1)), ephemeral=True)
            return

        await interaction.response.defer()
        try:
            urls = [plik.url] if plik else [await self.search_gif(fraza, interaction.guild_id)]
            data, ext, _ = await self.render_gif(urls, tekst, upload_limit(interaction.guild))
        except LookupError:
            await interaction.followup.send(f"KLIPY nic nie znalazło dla „{fraza}”.")
            return
        except Exception as e:
            print(f"[meme] /gif failed: {e}")
            await interaction.followup.send(f"Nie udało się zrobić GIF-a: {e}.")
            return
        await interaction.followup.send(file=nextcord.File(io.BytesIO(data), filename=f"mem.{ext}"))

    @nextcord.message_command(name="Podpisz GIF-a", contexts=[nextcord.InteractionContextType.guild])
    async def podpisz_gif(self, interaction: Interaction, message: nextcord.Message):
        if self._module_off(interaction.guild.id):
            await interaction.response.send_message(
                "Moduł `meme` jest obecnie wyłączony (zobacz `/moduly status`).", ephemeral=True)
            return
        if not media_urls(message):
            await interaction.response.send_message("W tej wiadomości nie ma GIF-a ani obrazka.", ephemeral=True)
            return
        await interaction.response.send_modal(CaptionModal(self, message))

    async def caption_message(self, interaction: Interaction, message, text):
        retry = self.cooldown.get_retry_after(interaction.guild_id)
        if retry is not None:
            await interaction.response.send_message(COOLDOWN_MSG.format(s=round(retry, 1)), ephemeral=True)
            return
        await interaction.response.defer(ephemeral=True)
        try:
            data, ext, _ = await self.render_gif(media_urls(message), text, upload_limit(interaction.guild))
            # Posted as a reply to the original gif, not as the interaction response.
            await message.channel.send(
                file=nextcord.File(io.BytesIO(data), filename=f"mem.{ext}"),
                reference=message.to_reference(fail_if_not_exists=False),
                allowed_mentions=nextcord.AllowedMentions.none(),
            )
        except Exception as e:
            print(f"[meme] caption_message failed: {e}")
            await interaction.followup.send(f"Nie udało się: {e}.", ephemeral=True)
            return
        await interaction.followup.send("Gotowe.", ephemeral=True)

    # --- agent queue ---

    @tasks.loop(seconds=QUEUE_POLL_S)
    async def process_queue(self):
        try:
            requests = await asyncio.to_thread(self.database.claim_meme_requests, 5, 10, ("image", "gif"))
        except Exception as e:
            print(f"[meme] queue poll failed: {e}")
            return
        for req in requests or []:
            try:
                status, error, posted_id, media_url = await self._handle_request(req)
            except Exception as e:
                status, error, posted_id, media_url = "failed", f"{type(e).__name__}: {e}", None, None
            if status != "done":
                print(f"[meme] request {req['id']} {status}: {error}")
            await asyncio.to_thread(
                self.database.finish_meme_request, req["id"], status, error, posted_id, media_url
            )

    async def _handle_request(self, req):
        """Renders and posts one queued meme. Returns (status, error, posted_message_id, media_url)."""
        guild_id, channel_id = int(req["guild_id"]), int(req["channel_id"])
        if self._module_off(guild_id):
            return "failed", "module disabled", None, None
        if self.agent_cooldown.get_retry_after(guild_id) is not None:
            return "failed", "rate limited", None, None

        channel = self.client.get_channel(channel_id)
        if channel is None:
            channel = await self.client.fetch_channel(channel_id)
        # The row comes from n8n: never post into a guild other than the one it names.
        if getattr(getattr(channel, "guild", None), "id", None) != guild_id:
            return "failed", "channel not in guild", None, None

        reference = None
        if req.get("reply_to_message_id"):
            reference = nextcord.MessageReference(
                message_id=int(req["reply_to_message_id"]),
                channel_id=channel_id,
                guild_id=guild_id,
                fail_if_not_exists=False,
            )
        no_pings = nextcord.AllowedMentions.none()

        async def visible_fail(why, note):
            # The agent already told the user a meme is coming - say why it isn't.
            await channel.send(f"(mem nie wyszedł: {note})", reference=reference, allowed_mentions=no_pings)
            return "failed", why, None, None

        if req.get("repeat_of"):
            original = await asyncio.to_thread(self.database.get_meme_request, int(req["repeat_of"]), guild_id)
            if not original:
                return await visible_fail("repeat_of not found", f"nie mam mema #{req['repeat_of']}")
            keys = ("kind", "template", "captions", "gif_query", "media_url", "source_message_id")
            req = {**req, **{k: original[k] for k in keys}}

        captions = req.get("captions") or []
        if not isinstance(captions, list):
            captions = [captions]
        texts = [str(c or "").strip()[:MAX_TEXT] for c in captions]
        if not any(texts):
            return "failed", "no captions", None, None

        if (req.get("kind") or "image") == "gif":
            text = next(t for t in texts if t)
            # Candidates in order: the gif recorded on a previous run (repeats), the
            # message it came from (Discord attachment URLs expire, so re-read it),
            # and only for fresh requests a KLIPY search.
            urls = [req["media_url"]] if req.get("media_url") else []
            if req.get("source_message_id"):
                try:
                    source = await channel.fetch_message(int(req["source_message_id"]))
                    urls += [u for u in media_urls(source) if u not in urls]
                except nextcord.NotFound:
                    pass
                if not urls:
                    return await visible_fail("no media in source", "nie widzę tam GIF-a ani obrazka")
            if not urls and req.get("gif_query"):
                try:
                    urls = [await self.search_gif(str(req["gif_query"]), guild_id)]
                except LookupError:
                    return await visible_fail("no gif found", f"KLIPY nic nie znalazło dla „{str(req['gif_query'])[:60]}”")
            if not urls:
                return "failed", "no gif source", None, None
            data, ext, used = await self.render_gif(urls, text, upload_limit(channel.guild))
            sent = await channel.send(
                file=nextcord.File(io.BytesIO(data), filename=f"mem.{ext}"),
                reference=reference, allowed_mentions=no_pings,
            )
            return "done", None, sent.id, used

        template = await self.catalog.resolve(str(req.get("template") or ""))
        if template is None:
            return await visible_fail("unknown template", f"nie znam szablonu „{str(req.get('template'))[:80]}”")

        data = await self.catalog.render(template, texts)
        sent = await channel.send(
            file=nextcord.File(io.BytesIO(data), filename="mem.jpg"),
            reference=reference,
            allowed_mentions=no_pings,
        )
        return "done", None, sent.id, None
