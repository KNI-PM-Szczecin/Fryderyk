"""
Captioned GIFs: a white caption bar above an animation (the classic "GIF with a
caption" look), so it works for ANY gif without hand-measured text boxes.

Sources are resolved by the caller (cogs/meme.py): a KLIPY search, an attachment
or an embed of a Discord message. This module only does:

    frames, durations = load_frames(media_bytes)        # GIF/WebP/PNG/JPEG via Pillow, MP4/WebM via PyAV
    data, ext = caption_media(frames, durations, text, max_bytes)

plus a tiny KLIPY client. KLIPY replaced Tenor after Google shut the Tenor API
down on 2026-06-30. The API key lives in the URL path, so never log request URLs.
"""
import asyncio
import io
import random
import time
from collections import deque

import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageSequence, UnidentifiedImageError

from utilities.meme import FONT_PATH, _wrap

MAX_SECONDS = 10.0       # longer clips are cut
MAX_SOURCE_FRAMES = 400  # hard stop while decoding
MIN_FRAME_MS = 60        # ~16 fps cap: denser frames are merged
MAX_DOWNLOAD = 25 * 1024 * 1024
WIDTHS = (480, 400, 320, 256)   # tried in order until the GIF fits the upload limit
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=20)


# --- decoding ---

def load_frames(data: bytes):
    """Returns (list of RGB frames, list of durations in ms)."""
    try:
        return _load_with_pillow(data)
    except UnidentifiedImageError:
        return _load_with_av(data)


def _flatten(img):
    """RGBA -> RGB on white (transparent GIF pixels would otherwise turn black)."""
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGB", img.size, "white")
        bg.paste(img, mask=img.getchannel("A"))
        return bg
    return img.convert("RGB")


def _load_with_pillow(data):
    im = Image.open(io.BytesIO(data))
    frames, durations, total = [], [], 0
    default = im.info.get("duration") or 100
    # Pillow >= 9 hands out fully composited frames, so GIF disposal is handled.
    for frame in ImageSequence.Iterator(im):
        d = int(frame.info.get("duration") or default)
        d = d if d >= 20 else 100   # 0/10 ms frames are a browser quirk, treat as 100 ms
        frames.append(_flatten(frame.copy()))
        durations.append(d)
        total += d
        if total / 1000 >= MAX_SECONDS or len(frames) >= MAX_SOURCE_FRAMES:
            break
    return _merge_dense(frames, durations)


def _load_with_av(data):
    import av  # only needed for video sources; keep the import lazy

    frames, times = [], []
    with av.open(io.BytesIO(data)) as container:
        stream = container.streams.video[0]
        rate = float(stream.average_rate or 15) or 15
        for frame in container.decode(stream):
            t = float(frame.time) if frame.time is not None else len(frames) / rate
            if t > MAX_SECONDS or len(frames) >= MAX_SOURCE_FRAMES:
                break
            frames.append(frame.to_image().convert("RGB"))
            times.append(t)
    if not frames:
        raise ValueError("no video frames")
    durations = [max(20, int((b - a) * 1000)) for a, b in zip(times, times[1:])]
    durations.append(int(1000 / rate))
    return _merge_dense(frames, durations)


def _merge_dense(frames, durations):
    """Drops frames shown for less than MIN_FRAME_MS, giving their time to the kept frame."""
    out_f, out_d = [], []
    for f, d in zip(frames, durations):
        if out_d and out_d[-1] < MIN_FRAME_MS:
            out_d[-1] += d
            continue
        out_f.append(f)
        out_d.append(d)
    return out_f, out_d


# --- captioning ---

def _caption_bar(text, width):
    """White bar with centred black text, wrapped and shrunk to at most 4 lines."""
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    pad = max(6, width // 24)
    inner = width - 2 * pad
    for size in range(max(14, width // 9), 11, -2):
        font = ImageFont.truetype(FONT_PATH, size)
        lines = _wrap(draw, text, font, inner, 0)
        if lines and len(lines) <= 4:
            break
    else:
        lines = lines or [text]
    line_h = int(size * 1.2)
    bar = Image.new("RGB", (width, line_h * len(lines) + 2 * pad), "white")
    d = ImageDraw.Draw(bar)
    y = pad
    for line in lines:
        x = (width - d.textlength(line, font=font)) / 2
        d.text((x, y), line, font=font, fill="black")
        y += line_h
    return bar


def _compose(frames, text, width):
    w0, h0 = frames[0].size
    height = max(1, round(h0 * width / w0))
    bar = _caption_bar(text, width)
    out = []
    for f in frames:
        canvas = Image.new("RGB", (width, bar.height + height), "white")
        canvas.paste(bar, (0, 0))
        canvas.paste(f.resize((width, height), Image.BILINEAR), (0, bar.height))
        out.append(canvas)
    return out


def caption_media(frames, durations, text, max_bytes):
    """
    Returns (bytes, extension). One frame -> JPEG; animation -> looping GIF that
    fits max_bytes, shrinking width and then frame rate until it does.
    """
    text = " ".join((text or "").split())
    if len(frames) == 1:
        img = _compose(frames, text, min(800, max(320, frames[0].width)))[0]
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue(), "jpg"

    src_w = frames[0].width
    # Tiny sources (KLIPY often serves 220 px) are upscaled so the caption stays readable.
    widths = [w for w in WIDTHS if w <= max(src_w, 320)] or [WIDTHS[-1]]
    stride = 1
    for attempt in range(8):
        width = widths[min(attempt, len(widths) - 1)]
        if attempt >= len(widths):
            stride *= 2   # out of widths: halve the frame rate instead
        fs = frames[::stride]
        ds = [sum(durations[i:i + stride]) for i in range(0, len(durations), stride)]
        # FASTOCTREE without dithering: ~20x faster than Pillow's default
        # median-cut on GIF save, visually the same for memes, smaller files.
        composed = [
            f.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE)
            for f in _compose(fs, text, width)
        ]
        buf = io.BytesIO()
        composed[0].save(
            buf, format="GIF", save_all=True, append_images=composed[1:],
            duration=ds, loop=0, disposal=1, optimize=False,
        )
        if buf.tell() <= max_bytes:
            return buf.getvalue(), "gif"
    raise ValueError("gif too large even after shrinking")


# --- downloading ---

async def download(url: str) -> bytes:
    async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
        async with session.get(url) as resp:
            if resp.status >= 400:
                raise RuntimeError(f"download failed: HTTP {resp.status}")
            if (resp.content_length or 0) > MAX_DOWNLOAD:
                raise RuntimeError("file too large")
            # content.read(n) returns whatever has arrived so far, not n bytes:
            # stream until EOF and enforce the cap ourselves.
            buf = bytearray()
            async for chunk in resp.content.iter_chunked(64 * 1024):
                buf += chunk
                if len(buf) > MAX_DOWNLOAD:
                    raise RuntimeError("file too large")
            return bytes(buf)


# --- KLIPY ---

class KlipyClient:
    """
    Minimal KLIPY GIF search. Test keys allow 100 calls/hour, so the client keeps
    its own sliding-window cap below that. Errors never include the request URL
    (it contains the key).
    """

    SEARCH = "https://api.klipy.com/api/v1/{key}/gifs/search"

    def __init__(self, key: str, hourly_cap: int = 60):
        self.key = (key or "").strip()
        self.hourly_cap = hourly_cap
        self._calls = deque()

    @property
    def enabled(self):
        return bool(self.key)

    def _take_slot(self):
        now = time.time()
        while self._calls and now - self._calls[0] > 3600:
            self._calls.popleft()
        if len(self._calls) >= self.hourly_cap:
            raise RuntimeError("KLIPY hourly limit reached")
        self._calls.append(now)

    async def search(self, query: str, customer_id: str, per_page: int = 8):
        if not self.enabled:
            raise RuntimeError("KLIPY key not configured")
        self._take_slot()
        params = {"q": query[:100], "per_page": str(per_page), "customer_id": customer_id}
        try:
            async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
                async with session.get(self.SEARCH.format(key=self.key), params=params) as resp:
                    status = resp.status
                    body = await resp.json(content_type=None) if status < 400 else None
        except asyncio.TimeoutError:
            raise RuntimeError("KLIPY timeout") from None
        except aiohttp.ClientError as e:
            raise RuntimeError(f"KLIPY connection error ({type(e).__name__})") from None
        if status >= 400 or not body or not body.get("result"):
            raise RuntimeError(f"KLIPY HTTP {status}")
        items = (body.get("data") or {}).get("data") or []
        # Ads are off for our key, but never caption anything that isn't a plain gif.
        return [it for it in items if it.get("type") == "gif"]

    @staticmethod
    def pick_url(items, max_bytes=8 * 1024 * 1024):
        """Random pick among the top results (variety), best size variant under max_bytes."""
        pool = items[:5]
        random.shuffle(pool)
        for it in pool:
            files = it.get("file") or {}
            for size in ("hd", "md", "sm"):
                gif = (files.get(size) or {}).get("gif") or {}
                if gif.get("url") and (gif.get("size") or 0) <= max_bytes:
                    return gif["url"]
        return None
