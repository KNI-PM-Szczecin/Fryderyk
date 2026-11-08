import asyncio
import io

import nextcord
from nextcord import Interaction, SlashOption
from nextcord.ext import commands, tasks

from decorators.cooldown import CogSharedCooldown
from utilities.meme import MemeCatalog

MAX_TEXT = 150
COOLDOWN_MSG = "**Zwolnij!** Następny mem za **{s}s**."
QUEUE_POLL_S = 3


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


class MemeCog(commands.Cog):
    """
    Captions Imgflip templates with text drawn by Pillow (no image generation).
    Two entry points share utilities/meme.py:

    * /mem - operator picks a template via autocomplete and fills the captions
      in a modal; the meme is posted publicly in the channel.
    * meme_requests queue - the n8n agent ("Wypowiedz sie") has a "Zrób mema"
      tool that inserts a pending row (template + captions + where to post). This
      cog polls the table every QUEUE_POLL_S seconds, claims rows atomically,
      renders and posts them as a reply to the message that asked for it.

    Both paths are gated per guild by the `meme` module.
    """

    def __init__(self, client, config, database):
        self.client = client
        self.config = config
        self.database = database
        self.catalog = MemeCatalog()
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
        try:
            await self.catalog.templates()
        except Exception as e:
            print(f"[meme] catalog preload failed: {e}")

    def cog_unload(self):
        self.process_queue.cancel()

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
        if not self.database.is_module_enabled(interaction.guild.id, "meme"):
            await interaction.response.send_message(
                "Moduł `/mem` jest obecnie wyłączony (zobacz `/moduly status`).",
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

    # --- agent queue ---

    @tasks.loop(seconds=QUEUE_POLL_S)
    async def process_queue(self):
        try:
            requests = await asyncio.to_thread(self.database.claim_meme_requests)
        except Exception as e:
            print(f"[meme] queue poll failed: {e}")
            return
        for req in requests or []:
            try:
                status, error, posted_id = await self._handle_request(req)
            except Exception as e:
                status, error, posted_id = "failed", f"{type(e).__name__}: {e}", None
            if status != "done":
                print(f"[meme] request {req['id']} {status}: {error}")
            await asyncio.to_thread(self.database.finish_meme_request, req["id"], status, error, posted_id)

    async def _handle_request(self, req):
        """Renders and posts one queued meme. Returns (status, error, posted_message_id)."""
        guild_id, channel_id = int(req["guild_id"]), int(req["channel_id"])
        if not self.database.is_module_enabled(guild_id, "meme"):
            return "failed", "module disabled", None
        if self.agent_cooldown.get_retry_after(guild_id) is not None:
            return "failed", "rate limited", None

        channel = self.client.get_channel(channel_id)
        if channel is None:
            channel = await self.client.fetch_channel(channel_id)
        # The row comes from n8n: never post into a guild other than the one it names.
        if getattr(getattr(channel, "guild", None), "id", None) != guild_id:
            return "failed", "channel not in guild", None

        reference = None
        if req.get("reply_to_message_id"):
            reference = nextcord.MessageReference(
                message_id=int(req["reply_to_message_id"]),
                channel_id=channel_id,
                guild_id=guild_id,
                fail_if_not_exists=False,
            )
        no_pings = nextcord.AllowedMentions.none()

        template = await self.catalog.resolve(str(req["template"]))
        if template is None:
            await channel.send(
                f"(mem nie wyszedł: nie znam szablonu „{str(req['template'])[:80]}”)",
                reference=reference, allowed_mentions=no_pings,
            )
            return "failed", "unknown template", None

        captions = req.get("captions") or []
        if not isinstance(captions, list):
            captions = [captions]
        texts = [str(c or "").strip()[:MAX_TEXT] for c in captions]
        if not any(texts):
            return "failed", "no captions", None

        data = await self.catalog.render(template, texts)
        sent = await channel.send(
            file=nextcord.File(io.BytesIO(data), filename="mem.jpg"),
            reference=reference,
            allowed_mentions=no_pings,
        )
        return "done", None, sent.id
