"""
Meme rendering: Imgflip template catalog + Pillow text overlay.

Deliberately independent of Discord so any caller (the /mem command today, an
LLM-driven "make me a meme" path later) can do:

    catalog = MemeCatalog()
    template = await catalog.resolve("drake")
    png = await catalog.render(template, ["pisać testy", "pushować na main"])

Imgflip's get_memes is public (no key) and lists the ~100 most popular
templates, but it does NOT say where each text box goes. Popular multi-panel
templates get hand-measured boxes in LAYOUTS; everything else falls back to the
classic top/bottom (or evenly stacked bands for 3+ boxes).
"""
import asyncio
import io
import os
import time
from collections import OrderedDict
from dataclasses import dataclass

import aiohttp
from PIL import Image, ImageDraw, ImageFont

GET_MEMES_URL = "https://api.imgflip.com/get_memes"
CATALOG_TTL_S = 12 * 3600
IMAGE_CACHE_SIZE = 40
MAX_SIDE = 1200          # templates bigger than this are downscaled before drawing
MAX_BOXES = 5            # Discord modals hold at most 5 text inputs
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=15)

FONT_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "assets", "fonts", "Anton-Regular.ttf",
)

# Box = (x0, y0, x1, y1) as fractions of the image, a style and a short hint
# shown as the modal field label.
#   style "outline": white text with a black stroke (readable on any photo)
#   style "dark":    black text, no stroke (for white panels/whiteboards/signs)
# valign: "top" | "middle" | "bottom" (where the text block sits inside the box)


@dataclass(frozen=True)
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    hint: str = ""
    style: str = "outline"
    valign: str = "middle"


TOP = Box(0.02, 0.02, 0.98, 0.26, "Góra", valign="top")
BOTTOM = Box(0.02, 0.74, 0.98, 0.98, "Dół", valign="bottom")

LAYOUTS = {
    # Drake Hotline Bling
    "181913649": [
        Box(0.52, 0.03, 0.98, 0.47, "Nie (góra)", "dark"),
        Box(0.52, 0.53, 0.98, 0.97, "Tak (dół)", "dark"),
    ],
    # Two Buttons
    "87743020": [
        Box(0.04, 0.06, 0.42, 0.24, "Lewy przycisk"),
        Box(0.44, 0.03, 0.88, 0.20, "Prawy przycisk"),
        Box(0.04, 0.80, 0.96, 0.97, "Spocony gość", valign="bottom"),
    ],
    # Distracted Boyfriend
    "112126428": [
        Box(0.08, 0.55, 0.46, 0.85, "Ta nowa (czerwona)"),
        Box(0.47, 0.30, 0.73, 0.58, "On"),
        Box(0.72, 0.45, 0.99, 0.75, "Jego dziewczyna"),
    ],
    # Gru's Plan
    "131940431": [
        Box(0.29, 0.06, 0.48, 0.47, "Plan, krok 1", "dark"),
        Box(0.78, 0.06, 0.97, 0.47, "Plan, krok 2", "dark"),
        Box(0.29, 0.55, 0.48, 0.96, "Plan, krok 3", "dark"),
        Box(0.78, 0.55, 0.97, 0.96, "Krok 3 jeszcze raz", "dark"),
    ],
    # Change My Mind
    "129242436": [
        Box(0.43, 0.60, 0.92, 0.82, "Tekst na tabliczce", "dark"),
        Box(0.02, 0.02, 0.98, 0.25, "Góra (opcjonalnie)", valign="top"),
    ],
    # UNO Draw 25 Cards
    "217743513": [
        Box(0.09, 0.22, 0.46, 0.48, "Zrób X albo...", "dark"),
        Box(0.52, 0.02, 0.98, 0.24, "Gość z kartami", valign="top"),
    ],
    # Woman Yelling At Cat
    "188390779": [
        Box(0.01, 0.01, 0.49, 0.21, "Krzycząca kobieta", "dark"),
        Box(0.51, 0.01, 0.99, 0.21, "Kot", "dark"),
    ],
    # Is This A Pigeon
    "100777631": [
        Box(0.55, 0.06, 0.97, 0.30, "Motyl"),
        Box(0.04, 0.22, 0.50, 0.42, "Gość"),
        Box(0.02, 0.80, 0.98, 0.98, "Is this a...?", valign="bottom"),
    ],
    # Epic Handshake
    "135256802": [
        Box(0.02, 0.50, 0.42, 0.82, "Lewa ręka"),
        Box(0.58, 0.50, 0.98, 0.82, "Prawa ręka"),
        Box(0.22, 0.03, 0.68, 0.25, "Wspólne (uścisk)"),
    ],
    # Left Exit 12 Off Ramp
    "124822590": [
        Box(0.24, 0.12, 0.49, 0.34, "Prosto"),
        Box(0.51, 0.12, 0.74, 0.34, "Zjazd w lewo"),
        Box(0.30, 0.72, 0.80, 0.94, "Samochód"),
    ],
    # Anakin Padme 4 Panel
    "322841258": [
        Box(0.02, 0.36, 0.49, 0.49, "Anakin", valign="bottom"),
        Box(0.51, 0.36, 0.98, 0.49, "Padme", valign="bottom"),
        Box(0.02, 0.86, 0.49, 0.99, "Anakin (cisza)", valign="bottom"),
    ],
    # Trade Offer
    "309868304": [
        Box(0.03, 0.22, 0.48, 0.42, "Ja dostaję"),
        Box(0.52, 0.22, 0.97, 0.42, "Ty dostajesz"),
        Box(0.04, 0.82, 0.96, 0.98, "Dół (opcjonalnie)", valign="bottom"),
    ],
    # Bike Fall
    "79132341": [
        Box(0.06, 0.04, 0.94, 0.15, "Panel 1"),
        Box(0.06, 0.39, 0.94, 0.50, "Panel 2"),
        Box(0.06, 0.68, 0.94, 0.79, "Panel 3"),
    ],
    # Sad Pablo Escobar
    "80707627": [
        Box(0.02, 0.33, 0.98, 0.49, "Panel 1", valign="bottom"),
        Box(0.02, 0.83, 0.49, 0.99, "Panel 2", valign="bottom"),
        Box(0.51, 0.83, 0.98, 0.99, "Panel 3", valign="bottom"),
    ],
    # Running Away Balloon
    "131087935": [
        Box(0.58, 0.08, 0.98, 0.36, "Balon (góra)"),
        Box(0.04, 0.32, 0.46, 0.48, "Ludzik (góra)"),
        Box(0.76, 0.58, 0.99, 0.80, "Balon (dół)"),
        Box(0.01, 0.66, 0.34, 0.86, "Różowy"),
        Box(0.36, 0.80, 0.76, 0.97, "Ludzik (dół)"),
    ],
    # Expanding Brain
    "93895088": [
        Box(0.03, 0.02, 0.47, 0.24, "Mózg 1", "dark"),
        Box(0.03, 0.27, 0.47, 0.49, "Mózg 2", "dark"),
        Box(0.03, 0.52, 0.47, 0.73, "Mózg 3", "dark"),
        Box(0.03, 0.76, 0.47, 0.98, "Mózg 4", "dark"),
    ],
}


@dataclass(frozen=True)
class Template:
    id: str
    name: str
    url: str
    box_count: int

    @property
    def boxes(self):
        return layout_for(self.id, self.box_count)


def layout_for(template_id: str, box_count: int):
    """Hand-measured boxes if we have them, otherwise a generic layout."""
    if template_id in LAYOUTS:
        return LAYOUTS[template_id][:MAX_BOXES]
    n = max(1, min(box_count or 2, MAX_BOXES))
    if n == 1:
        return [TOP]
    if n == 2:
        return [TOP, BOTTOM]
    # 3+ boxes on an unknown template: stack evenly spaced horizontal bands.
    band = 1.0 / n
    return [
        Box(0.02, i * band + 0.01, 0.98, (i + 1) * band - 0.01, f"Pole {i + 1}")
        for i in range(n)
    ]


# --- rendering (pure, synchronous: call through asyncio.to_thread) ---

def _wrap(draw, text, font, max_width, stroke):
    """Greedy word wrap. Returns lines, or None if a single word is too wide."""
    lines, current = [], ""
    for word in text.split():
        candidate = f"{current} {word}".strip()
        if draw.textlength(candidate, font=font) + 2 * stroke <= max_width:
            current = candidate
            continue
        if not current:
            return None
        lines.append(current)
        current = word
        if draw.textlength(current, font=font) + 2 * stroke > max_width:
            return None
    if current:
        lines.append(current)
    return lines


def _fit(draw, text, box_w, box_h, outline, max_size):
    """Largest font size whose wrapped text fits the box. Returns (font, lines, stroke, line_h)."""
    hi = max(12, min(int(box_h * 0.9), max_size))
    for size in range(hi, 9, -2):
        font = ImageFont.truetype(FONT_PATH, size)
        stroke = max(1, size // 14) if outline else 0
        lines = _wrap(draw, text, font, box_w, stroke)
        if lines is None:
            continue
        line_h = int(size * 1.15)
        if line_h * len(lines) + 2 * stroke <= box_h:
            return font, lines, stroke, line_h
    # Text is absurdly long for the box: smallest size, let it overflow downward.
    font = ImageFont.truetype(FONT_PATH, 10)
    return font, _wrap(draw, text, font, box_w, 1) or [text], 1, 12


def render_meme(image_bytes: bytes, texts, boxes) -> bytes:
    """Draws texts into boxes on the image and returns JPEG bytes."""
    img = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    w, h = img.size
    draw = ImageDraw.Draw(img)
    # A one-word caption would otherwise fill the whole box; classic meme text
    # tops out around a tenth of the image.
    max_size = max(16, int(min(w, h) * 0.13))

    for text, box in zip(texts, boxes):
        text = " ".join((text or "").split()).upper()
        if not text:
            continue
        outline = box.style != "dark"
        bx0, by0 = int(box.x0 * w), int(box.y0 * h)
        bw, bh = int((box.x1 - box.x0) * w), int((box.y1 - box.y0) * h)
        font, lines, stroke, line_h = _fit(draw, text, bw, bh, outline, max_size)

        block_h = line_h * len(lines)
        if box.valign == "top":
            y = by0
        elif box.valign == "bottom":
            y = by0 + bh - block_h
        else:
            y = by0 + (bh - block_h) // 2

        for line in lines:
            line_w = draw.textlength(line, font=font)
            x = bx0 + (bw - line_w) / 2
            draw.text(
                (x, y), line, font=font,
                fill="white" if outline else "black",
                stroke_width=stroke, stroke_fill="black",
            )
            y += line_h

    out = io.BytesIO()
    img.save(out, format="JPEG", quality=90)
    return out.getvalue()


# --- catalog ---

def _norm(text: str) -> str:
    return "".join(ch for ch in text.lower() if ch.isalnum())


class MemeCatalog:
    """
    Caches the Imgflip template list (refreshed every CATALOG_TTL_S) and the
    downloaded template images (small LRU). One instance per process is enough:
    the data is global, not per guild.
    """

    def __init__(self):
        self._templates = []
        self._by_id = {}
        self._loaded_at = 0.0
        self._lock = asyncio.Lock()
        self._images = OrderedDict()

    async def templates(self):
        if self._templates and time.time() - self._loaded_at < CATALOG_TTL_S:
            return self._templates
        async with self._lock:
            if self._templates and time.time() - self._loaded_at < CATALOG_TTL_S:
                return self._templates
            try:
                async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
                    async with session.get(GET_MEMES_URL) as resp:
                        data = await resp.json(content_type=None)
                if not data.get("success"):
                    raise RuntimeError(data.get("error_message") or "Imgflip error")
                templates = [
                    Template(str(m["id"]), m["name"], m["url"], int(m.get("box_count") or 2))
                    for m in data["data"]["memes"]
                ]
            except Exception as e:
                # Keep serving a stale list rather than failing outright.
                if self._templates:
                    print(f"[meme] catalog refresh failed, using stale list: {e}")
                    self._loaded_at = time.time() - CATALOG_TTL_S + 600
                    return self._templates
                raise
            self._templates = templates
            self._by_id = {t.id: t for t in templates}
            self._loaded_at = time.time()
            return self._templates

    def cached_templates(self):
        """Whatever is already loaded, without touching the network."""
        return self._templates

    def search(self, query: str, limit: int = 25):
        """Name substring match over the loaded list, popularity order preserved."""
        templates = self._templates
        q = (query or "").strip().lower()
        if not q:
            return templates[:limit]
        starts = [t for t in templates if t.name.lower().startswith(q)]
        contains = [t for t in templates if q in t.name.lower() and t not in starts]
        return (starts + contains)[:limit]

    async def resolve(self, value: str):
        """Template by id (what autocomplete sends) or by name (what a human/LLM types)."""
        await self.templates()
        value = (value or "").strip()
        if not value:
            return None
        if value in self._by_id:
            return self._by_id[value]
        # Exact name first (an LLM usually names the template verbatim), then
        # prefix/substring, then the same ignoring punctuation ("Grus Plan").
        exact = [t for t in self._templates if t.name.lower() == value.lower()]
        if exact:
            return exact[0]
        matches = self.search(value, limit=1)
        if matches:
            return matches[0]
        key = _norm(value)
        loose = [t for t in self._templates if key and key in _norm(t.name)]
        return loose[0] if loose else None

    async def image(self, template: Template) -> bytes:
        if template.id in self._images:
            self._images.move_to_end(template.id)
            return self._images[template.id]
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            async with session.get(template.url) as resp:
                resp.raise_for_status()
                data = await resp.read()
        self._images[template.id] = data
        while len(self._images) > IMAGE_CACHE_SIZE:
            self._images.popitem(last=False)
        return data

    async def render(self, template: Template, texts) -> bytes:
        """Downloads (or reuses) the template image and renders off the event loop."""
        image_bytes = await self.image(template)
        return await asyncio.to_thread(render_meme, image_bytes, list(texts), template.boxes)
