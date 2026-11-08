"""
Image cards drawn with Pillow: quote cards ("@Fryderyk zacytuj to") and the
semester summary ("Wrapped") cards and the long ranking ("topka").

Text may contain Unicode emoji and Discord custom emoji (<:name:id>), which no
text font can draw, so text is split into runs and emoji are pasted as images
(Twemoji for Unicode, Discord's CDN for custom ones). Fetching is async and
happens BEFORE rendering: `await EmojiStore.prefetch(texts)`, then the sync
render_* functions (run them through asyncio.to_thread) read from the store.
"""
import io
import os
import re

import aiohttp
import emoji as emoji_lib
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

_FONTS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "fonts")
LATO = os.path.join(_FONTS, "Lato-Regular.ttf")
LATO_BOLD = os.path.join(_FONTS, "Lato-Bold.ttf")
LATO_BLACK = os.path.join(_FONTS, "Lato-Black.ttf")
LATO_ITALIC = os.path.join(_FONTS, "Lato-Italic.ttf")
ANTON = os.path.join(_FONTS, "Anton-Regular.ttf")

TWEMOJI = "https://cdn.jsdelivr.net/gh/jdecked/twemoji@16.0.1/assets/72x72/{}.png"
DISCORD_EMOJI = "https://cdn.discordapp.com/emojis/{}.png?size=96"
CUSTOM_RE = re.compile(r"<a?:(\w{1,32}):(\d{15,25})>")
HTTP_TIMEOUT = aiohttp.ClientTimeout(total=10)

BG = (24, 25, 28)
CARD = (35, 36, 41)
FG = (238, 238, 240)
MUTED = (150, 152, 160)


def _font(path, size):
    return ImageFont.truetype(path, size)


# --- emoji ---

def _twemoji_code(chars: str) -> str:
    # Twemoji file names drop U+FE0F unless the sequence is a ZWJ sequence.
    cps = [ord(c) for c in chars]
    if 0x200D not in cps:
        cps = [c for c in cps if c != 0xFE0F]
    return "-".join(f"{c:x}" for c in cps)


_NOTDEF = {}


def _missing(ch, path=LATO_BOLD):
    """True if the font would draw its .notdef box for ch (compared to a PUA char)."""
    f = _font(path, 24)
    ref = _NOTDEF.setdefault(path, bytes(f.getmask("\ue000")))
    return bytes(f.getmask(ch)) == ref


def sanitize(text: str) -> str:
    """Drops characters Lato can't render (fancy nick decorations etc.)."""
    return "".join(c for c in text if c.isspace() or ord(c) < 0x250 or not _missing(c))


def tokenize(text: str):
    """Splits text into [('text', str) | ('emoji', key)] runs."""
    runs = []
    pos = 0
    spans = [(m.start(), m.end(), "custom:" + m.group(2)) for m in CUSTOM_RE.finditer(text)]
    for e in emoji_lib.emoji_list(text):
        spans.append((e["match_start"], e["match_end"], "tw:" + _twemoji_code(e["emoji"])))
    spans.sort()
    for start, end, key in spans:
        if start < pos:
            continue
        if start > pos:
            runs.append(("text", sanitize(text[pos:start])))
        runs.append(("emoji", key))
        pos = end
    if pos < len(text):
        runs.append(("text", sanitize(text[pos:])))
    return runs


class EmojiStore:
    """Downloaded emoji images keyed like tokenize() keys; misses render as nothing."""

    def __init__(self):
        self.images = {}

    async def prefetch(self, texts):
        keys = {k for t in texts if t for kind, k in tokenize(t) if kind == "emoji"}
        keys -= set(self.images)
        if not keys:
            return
        async with aiohttp.ClientSession(timeout=HTTP_TIMEOUT) as session:
            for key in list(keys)[:60]:
                url = DISCORD_EMOJI.format(key[7:]) if key.startswith("custom:") else TWEMOJI.format(key[3:])
                try:
                    async with session.get(url) as resp:
                        if resp.status == 200:
                            self.images[key] = Image.open(io.BytesIO(await resp.read())).convert("RGBA")
                except Exception:
                    pass  # an emoji we can't fetch just disappears from the card

    def get(self, key):
        return self.images.get(key)


# --- rich text layout (text runs + inline emoji) ---

def _words(runs):
    """Groups runs into words (lists of runs) split on whitespace."""
    words, cur = [], []
    for kind, val in runs:
        if kind == "emoji":
            cur.append((kind, val))
            continue
        parts = re.split(r"(\s+)", val)
        for p in parts:
            if not p:
                continue
            if p.isspace():
                if cur:
                    words.append(cur)
                    cur = []
                if "\n" in p:
                    words.append([("break", None)])
            else:
                cur.append(("text", p))
    if cur:
        words.append(cur)
    return words


def _word_width(word, font, em):
    return sum(font.getlength(v) if k == "text" else em for k, v in word)


def layout(text, font, max_w):
    """Greedy wrap. Returns list of lines, each a list of words."""
    em = font.size * 1.15
    space = font.getlength(" ")
    lines, cur, cur_w = [], [], 0.0
    for word in _words(tokenize(text)):
        if word[0][0] == "break":
            lines.append(cur)
            cur, cur_w = [], 0.0
            continue
        w = _word_width(word, font, em)
        add = w if not cur else w + space
        if cur and cur_w + add > max_w:
            lines.append(cur)
            cur, cur_w = [word], w
        else:
            cur.append(word)
            cur_w += add
    if cur:
        lines.append(cur)
    return lines


def _lines_fit(lines, font, max_w):
    em = font.size * 1.15
    space = font.getlength(" ")
    return all(
        sum(_word_width(w, font, em) for w in line) + space * max(0, len(line) - 1) <= max_w
        for line in lines
    )


def fit_text(text, path, max_w, max_h, start, minimum=18, line_gap=1.3):
    """Largest size (<= start) where the wrapped text fits. Returns (font, lines, line_h)."""
    for size in range(start, minimum - 1, -2):
        font = _font(path, size)
        lines = layout(text, font, max_w)
        line_h = int(size * line_gap)
        if line_h * len(lines) <= max_h and _lines_fit(lines, font, max_w):
            return font, lines, line_h
    font = _font(path, minimum)
    return font, layout(text, font, max_w), int(minimum * line_gap)


def draw_lines(img, lines, font, line_h, x, y, max_w, fill, emojis, align="left"):
    draw = ImageDraw.Draw(img)
    em = int(font.size * 1.15)
    space = font.getlength(" ")
    for line in lines:
        width = sum(_word_width(w, font, em) for w in line) + space * max(0, len(line) - 1)
        cx = x + (max_w - width) / 2 if align == "center" else x
        for i, word in enumerate(line):
            if i:
                cx += space
            for kind, val in word:
                if kind == "text":
                    draw.text((cx, y), val, font=font, fill=fill)
                    cx += font.getlength(val)
                else:
                    im = emojis.get(val) if emojis else None
                    if im is not None:
                        e = im.resize((em, em), Image.LANCZOS)
                        img.paste(e, (int(cx), int(y + (line_h - em) / 2 - font.size * 0.08)), e)
                    cx += em
        y += line_h
    return y


# --- helpers ---

def circle_avatar(data: bytes | None, size: int, fallback_letter="?"):
    if data:
        try:
            av = Image.open(io.BytesIO(data)).convert("RGBA")
            av = ImageOps.fit(av, (size, size), Image.LANCZOS)
        except Exception:
            av = None
    else:
        av = None
    if av is None:
        av = Image.new("RGBA", (size, size), (88, 101, 242, 255))
        d = ImageDraw.Draw(av)
        f = _font(LATO_BLACK, size // 2)
        d.text((size / 2, size / 2), fallback_letter[:1].upper(), font=f, fill="white", anchor="mm")
    mask = Image.new("L", (size * 4, size * 4), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size * 4, size * 4), fill=255)
    av.putalpha(mask.resize((size, size), Image.LANCZOS))
    return av


def accent_from(data: bytes | None, default=(88, 101, 242)):
    """A vivid-ish dominant colour of the avatar for the card accent."""
    if not data:
        return default
    try:
        im = Image.open(io.BytesIO(data)).convert("RGB").resize((32, 32))
        colors = sorted(im.getcolors(32 * 32), reverse=True)
        for _, (r, g, b) in colors:
            mx, mn = max(r, g, b), min(r, g, b)
            if mx > 90 and mx - mn > 50:   # skip greys / near-black
                return (r, g, b)
    except Exception:
        pass
    return default


def _to_png(img):
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="PNG", optimize=True)
    return buf.getvalue()


# --- quote card ---

def render_quote(text, author, avatar_bytes, footer, emojis=None):
    """
    Dark card: big accent quote mark, the message, author with round avatar and
    a footer (date · #channel). Height adapts to the text. Returns PNG bytes.
    """
    W, PAD = 1200, 72
    accent = accent_from(avatar_bytes)
    inner = W - 2 * PAD
    font, lines, line_h = fit_text(text, LATO_BOLD, inner, 520, start=58, minimum=26)
    text_h = line_h * len(lines)
    H = PAD + 70 + text_h + 60 + 96 + PAD

    img = Image.new("RGB", (W, H), BG)
    # soft accent glow in the corner
    glow = Image.new("RGB", (W, H), BG)
    ImageDraw.Draw(glow).ellipse((-300, -300, 500, 400), fill=accent)
    img = Image.blend(img, glow.filter(ImageFilter.GaussianBlur(160)), 0.35)
    d = ImageDraw.Draw(img)

    # Decorative mark sits in the 70 px band above the text: align by its real
    # bounding box, not the font baseline (quote glyphs float high or low).
    qf = _font(LATO_BLACK, 160)
    bx0, by0, _, _ = qf.getbbox("”")
    d.text((PAD - bx0, PAD - 24 - by0), "”", font=qf, fill=accent)
    y = draw_lines(img, lines, font, line_h, PAD, PAD + 70, inner, FG, emojis)

    y += 60
    av = circle_avatar(avatar_bytes, 96, author)
    img.paste(av, (PAD, y), av)
    d = ImageDraw.Draw(img)
    d.text((PAD + 120, y + 14), sanitize(author), font=_font(LATO_BLACK, 36), fill=FG)
    d.text((PAD + 120, y + 58), footer, font=_font(LATO, 26), fill=MUTED)
    d.rectangle((0, H - 8, W, H), fill=accent)
    return _to_png(img)


# --- shared bits for the semester summary ---

MONTHS = ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca",
          "sierpnia", "września", "października", "listopada", "grudnia"]
URL_RE = re.compile(r"https?://\S+")
IMG_EXT = (".png", ".jpg", ".jpeg", ".gif", ".webp")


def pl_date(d):
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def clean_text(text, limit=320):
    """Message text for a card: attachment/links become short markers, length capped."""
    def repl(m):
        url = m.group(0).split("?")[0].lower()
        if "cdn.discordapp.com/attachments" in url or url.endswith(IMG_EXT):
            return "📎"
        return "🔗"
    text = URL_RE.sub(repl, text or "").strip()
    text = re.sub(r"(\*\*|__|~~|`{1,3}|\|\|)", "", text)        # markdown markers
    text = re.sub(r"(?m)^\s*(#{1,3}|>)\s+", "", text)          # headings / quotes
    text = re.sub(r"[ \t]+", " ", text)
    return text if len(text) <= limit else text[: limit - 1].rstrip() + "…"


def fmt_int(n):
    return f"{int(n):,}".replace(",", " ")


def fmt_hours(h):
    return f"{h:.1f}".replace(".", ",") + " h" if h < 100 else f"{round(h)} h"


def _bg(W, H, accent):
    img = Image.new("RGB", (W, H), BG)
    glow = Image.new("RGB", (W, H), BG)
    ImageDraw.Draw(glow).ellipse((W - 520, -360, W + 360, 420), fill=accent)
    return Image.blend(img, glow.filter(ImageFilter.GaussianBlur(190)), 0.38)


def _readable(accent):
    """Lift dark accents so marks/labels stay visible on the dark surface."""
    r, g, b = accent
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if lum >= 110:
        return accent
    k = 110 / max(lum, 1)
    return tuple(min(255, int(c * k + 40)) for c in accent)


def _tile(img, box, label, value, sub, emojis, value_font=ANTON, value_size=64):
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=22, fill=CARD)
    pad = 28
    inner = x1 - x0 - 2 * pad
    d.text((x0 + pad, y0 + 24), label.upper(), font=_font(LATO_BOLD, 22), fill=MUTED)
    # value: one line, shrink to fit; it owns the band between label and sub line
    vf, vlines, vh = fit_text(value, value_font, inner, int(value_size * 1.25), start=value_size, minimum=26, line_gap=1.15)
    band_top, band_bottom = y0 + 60, y1 - 56
    if vlines:
        # centre the glyphs' real box in the band (Anton is much taller than Lato)
        bb = vf.getbbox("Ag0#")
        gy = band_top + (band_bottom - band_top - (bb[3] - bb[1])) / 2 - bb[1]
        draw_lines(img, vlines[:1], vf, bb[3] - bb[1], x0 + pad, gy, inner, FG, emojis)
    if sub:
        sf, slines, sh = fit_text(sub, LATO, inner, 34, start=26, minimum=18, line_gap=1.2)
        draw_lines(img, slines[:1], sf, sh, x0 + pad, y1 - 46, inner, MUTED, emojis)


def _hour_chart(img, box, hours, accent):
    """24 thin bars (one series, one hue), 2 px gaps, rounded tops on the
    baseline, recessive axis, only the peak hour labelled."""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=22, fill=CARD)
    pad = 28
    d.text((x0 + pad, y0 + 24), "KIEDY PISZESZ", font=_font(LATO_BOLD, 22), fill=MUTED)
    top, base = y0 + 110, y1 - 56
    left, right = x0 + pad, x1 - pad
    peak = max(hours) if any(hours) else 0
    slot = (right - left) / 24
    bw = max(4, slot - 4)
    color = _readable(accent)
    d.line((left, base, right, base), fill=(70, 72, 80), width=2)
    for h, n in enumerate(hours):
        bx = left + h * slot + (slot - bw) / 2
        if n and peak:
            bh = max(4, (base - top) * n / peak)
            d.rounded_rectangle((bx, base - bh, bx + bw, base), radius=4, fill=color)
            d.rectangle((bx, base - min(bh, 4), bx + bw, base), fill=color)  # flat on the baseline
        if h % 6 == 0:
            d.text((bx + bw / 2, base + 12), f"{h}:00", font=_font(LATO, 20), fill=MUTED, anchor="mt")
    if peak:
        ph = hours.index(peak)
        bx = left + ph * slot + slot / 2
        bh = (base - top) * 1.0
        d.text((bx, base - bh - 10), f"{ph}:00", font=_font(LATO_BOLD, 22), fill=FG, anchor="mb")


MONTH_CHART_H = 290
MONTHS_SHORT = ["sty", "lut", "mar", "kwi", "maj", "cze", "lip", "sie", "wrz", "paź", "lis", "gru"]


def _month_chart(img, box, title, months, accent):
    """Messages per month over the whole history: one series, one hue, thin
    bars on a shared baseline, years marked under the axis, peak labelled."""
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=22, fill=CARD)
    pad = 28
    d.text((x0 + pad, y0 + 24), title.upper(), font=_font(LATO_BOLD, 22), fill=MUTED)
    top, base = y0 + 100, y1 - 56
    left, right = x0 + pad, x1 - pad
    values = [n for _, n in months]
    peak = max(values) if any(values) else 0
    slot = (right - left) / max(1, len(months))
    bw = max(3, min(28, slot - 2))
    color = _readable(accent)
    d.line((left, base, right, base), fill=(70, 72, 80), width=2)
    small = _font(LATO, 20)
    last_label_end = -1
    for i, (m, n) in enumerate(months):
        bx = left + i * slot + (slot - bw) / 2
        if n and peak:
            bh = max(4, (base - top) * n / peak)
            d.rounded_rectangle((bx, base - bh, bx + bw, base), radius=min(4, bw / 2), fill=color)
            d.rectangle((bx, base - min(bh, 4), bx + bw, base), fill=color)
        if i == 0 or m.month == 1:
            label = f"{MONTHS_SHORT[m.month - 1]} {m.year}" if i == 0 else str(m.year)
            lx = max(left, bx)
            if lx > last_label_end + 12:
                d.text((lx, base + 12), label, font=small, fill=MUTED)
                last_label_end = lx + small.getlength(label)
    if peak:
        i = values.index(peak)
        m = months[i][0]
        cx = left + i * slot + slot / 2
        label = f"{MONTHS_SHORT[m.month - 1]} {m.year} · {fmt_int(peak)}"
        f = _font(LATO_BOLD, 22)
        w = f.getlength(label)
        lx = min(max(cx - w / 2, left), right - w)
        d.text((lx, top - 12), label, font=f, fill=FG, anchor="lb")


def _best_message(img, box, title, text, footer, emojis, accent):
    x0, y0, x1, y1 = box
    d = ImageDraw.Draw(img)
    d.rounded_rectangle(box, radius=22, fill=CARD)
    d.rectangle((x0, y0 + 22, x0 + 6, y1 - 22), fill=_readable(accent))
    pad = 34
    inner = x1 - x0 - 2 * pad
    d.text((x0 + pad, y0 + 24), title.upper(), font=_font(LATO_BOLD, 22), fill=MUTED)
    font, lines, lh = fit_text(text, LATO_ITALIC, inner, y1 - y0 - 130, start=34, minimum=20)
    draw_lines(img, lines, font, lh, x0 + pad, y0 + 66, inner, FG, emojis)
    d.text((x0 + pad, y1 - 48), footer, font=_font(LATO, 22), fill=MUTED)


def _header(img, W, PAD, accent, semester, right_text=None, title="WRAPPED"):
    d = ImageDraw.Draw(img)
    d.text((PAD, PAD - 6), title, font=_font(ANTON, 44), fill=_readable(accent))
    d.text((PAD, PAD + 52), semester, font=_font(LATO_BOLD, 26), fill=MUTED)
    if right_text:
        d.text((W - PAD, PAD + 4), right_text, font=_font(LATO, 24), fill=MUTED, anchor="ra")


def _voice_note(s):
    """Voice logging started 2026-05-29; say so when the window reaches further back."""
    v = s.get("voice_since")
    return f" · od {v.day}.{v.month:02d}.{v.year}" if v else ""


# --- personal card ---

def render_wrapped_user(s, name, avatar_bytes, names, emojis=None, guild_name=""):
    """
    s: utilities.wrapped.user_stats() dict; names: user_id -> display name
    (for the duo). Returns PNG bytes, 1080 wide.
    """
    W, PAD, GAP = 1080, 60, 22
    accent = accent_from(avatar_bytes)
    best = s.get("best_message")
    months = s.get("months")
    th = 196
    # header+who 292, hero 210, tiles 3 rows, hour chart 230 (+ month chart 230 for all-time); best-message box 280
    base = PAD + 120 + 172 + 210 + 3 * (th + GAP) + 230 + GAP + ((MONTH_CHART_H + GAP) if months else 0)
    H = base + (280 + PAD if best else PAD - GAP)
    img = _bg(W, H, accent)
    _header(img, W, PAD, accent, s["semester"] + (f" · {sanitize(guild_name)}" if guild_name else ""))
    d = ImageDraw.Draw(img)

    # who
    y = PAD + 120
    av = circle_avatar(avatar_bytes, 132, name)
    img.paste(av, (PAD, y), av)
    nf, nl, nh = fit_text(name, LATO_BLACK, W - 2 * PAD - 160, 70, start=56, minimum=30)
    draw_lines(img, nl[:1], nf, nh, PAD + 160, y + 6, W - 2 * PAD - 160, FG, emojis)
    px = PAD + 160
    for t in s.get("titles", []):
        f = _font(LATO_BOLD, 22)
        w = f.getlength(t) + 32
        if px + w > W - PAD:
            break
        d.rounded_rectangle((px, y + 84, px + w, y + 124), radius=20, outline=_readable(accent), width=2)
        d.text((px + 16, y + 104), t, font=f, fill=FG, anchor="lm")
        px += w + 10

    # hero number
    y += 172
    d.text((PAD, y), fmt_int(s["messages"]), font=_font(ANTON, 150), fill=FG)
    hero_w = _font(ANTON, 150).getlength(fmt_int(s["messages"]))
    d.text((PAD + hero_w + 24, y + 42), "wiadomości", font=_font(LATO_BLACK, 40), fill=FG)
    rank = f"#{s['rank']} z {s['total_users']} osób · {round(s['share'] * 100)}% serwera" if s.get("rank") else "w tym okresie"
    d.text((PAD + hero_w + 24, y + 98), rank, font=_font(LATO, 26), fill=MUTED)

    # tiles 2 x 3
    y += 210
    cw = (W - 2 * PAD - GAP) / 2
    duo = s.get("duo")
    top_e = s.get("top_emoji_received") or []
    tiles = [
        ("Dni aktywności", str(s["active_days"]), f"najdłuższa seria: {s['streak']} dni"),
        ("Voice", fmt_hours(s["voice_hours"]) if s["voice_hours"] else "—",
         (f"#{s['voice_rank']} na serwerze" if s.get("voice_rank") else "brak sesji") + _voice_note(s)),
        ("Reakcje", fmt_int(s["reactions_received"]), f"otrzymane · {fmt_int(s['reactions_given'])} rozdanych"),
        ("Ulubiony kanał", "#" + s["top_channel"][0].split("┃")[-1] if s.get("top_channel") else "—",
         f"{fmt_int(s['top_channel'][1])} wiadomości" if s.get("top_channel") else ""),
        ("Duet", names.get(duo[0], "ktoś") if duo else "—", f"{fmt_int(duo[1])} odpowiedzi między wami" if duo else ""),
        ("Najczęstsze reakcje", "  ".join(e for e, _ in top_e) if top_e else "—",
         " · ".join(fmt_int(n) for _, n in top_e) if top_e else ""),
    ]
    for i, (label, value, sub) in enumerate(tiles):
        cx = PAD + (i % 2) * (cw + GAP)
        cy = y + (i // 2) * (th + GAP)
        text_value = label in ("Ulubiony kanał", "Duet")
        size = 40 if label == "Najczęstsze reakcje" else (46 if text_value else 58)
        _tile(img, (cx, cy, cx + cw, cy + th), label, value, sub, emojis,
              value_font=LATO_BLACK if text_value else ANTON, value_size=size)
    y += 3 * (th + GAP)

    if months:
        _month_chart(img, (PAD, y, W - PAD, y + MONTH_CHART_H), "Twoja aktywność w czasie", months, accent)
        y += MONTH_CHART_H + GAP
    _hour_chart(img, (PAD, y, W - PAD, y + 230), s["hours"], accent)
    y += 230 + GAP

    if best:
        n = best["n"]
        _best_message(img, (PAD, y, W - PAD, H - PAD), f"Najgłośniejsza wiadomość · {n} os. zareagowało",
                      clean_text(best["message"]), f"{pl_date(best['msg_date'])} · #{best['channel_name'].split('┃')[-1]}",
                      emojis, accent)
    return _to_png(img)


# --- server card ---

def render_wrapped_server(s, guild_name, icon_bytes, names, emojis=None):
    W, PAD, GAP = 1080, 60, 22
    accent = accent_from(icon_bytes)
    best = s.get("best_message")
    first = s.get("first_message")
    months = s.get("months")
    noun = s.get("noun", "semestru")
    th = 196
    box_h = 70 + 58 * max(1, len(s["top_talkers"])) + 20
    base = PAD + 120 + 172 + 210 + box_h + GAP + 3 * (th + GAP)
    base += (MONTH_CHART_H + GAP) if months else 0
    base += (210 + GAP) if first else 0
    H = base + (280 + PAD if best else PAD - GAP)
    img = _bg(W, H, accent)
    _header(img, W, PAD, accent, s["semester"])
    d = ImageDraw.Draw(img)

    y = PAD + 120
    icon = circle_avatar(icon_bytes, 132, guild_name)
    img.paste(icon, (PAD, y), icon)
    gf, gl, gh = fit_text(guild_name, LATO_BLACK, W - 2 * PAD - 160, 110, start=50, minimum=28, line_gap=1.15)
    draw_lines(img, gl[:2], gf, gh, PAD + 160, y + 10, W - 2 * PAD - 160, FG, emojis)

    y += 172
    d.text((PAD, y), fmt_int(s["messages"]), font=_font(ANTON, 150), fill=FG)
    hero_w = _font(ANTON, 150).getlength(fmt_int(s["messages"]))
    d.text((PAD + hero_w + 24, y + 42), "wiadomości", font=_font(LATO_BLACK, 40), fill=FG)
    d.text((PAD + hero_w + 24, y + 98), f"od {s['active_users']} osób w {s['active_days']} dni",
           font=_font(LATO, 26), fill=MUTED)

    # top talkers: one series of magnitudes -> thin horizontal bars, one hue, values as direct labels
    y += 210
    d.rounded_rectangle((PAD, y, W - PAD, y + box_h), radius=22, fill=CARD)
    d.text((PAD + 28, y + 24), "NAJWIĘCEJ PISALI", font=_font(LATO_BOLD, 22), fill=MUTED)
    top = s["top_talkers"][0][1] if s["top_talkers"] else 1
    name_w, bar_l, bar_r = 300, PAD + 28 + 300 + 16, W - PAD - 130
    color = _readable(accent)
    for i, (uid, n) in enumerate(s["top_talkers"]):
        ry = y + 74 + i * 58
        nm = sanitize(names.get(uid, str(uid)))
        nf = _font(LATO_BOLD, 28)
        while nf.getlength(nm) > name_w and len(nm) > 3:
            nm = nm[:-2] + "…" if not nm.endswith("…") else nm[:-2] + "…"
        d.text((PAD + 28, ry + 18), f"{i + 1}. {nm}", font=nf, fill=FG, anchor="lm")
        bw = max(6, (bar_r - bar_l) * n / top)
        d.rounded_rectangle((bar_l, ry + 6, bar_l + bw, ry + 30), radius=4, fill=color)
        d.text((bar_l + bw + 12, ry + 18), fmt_int(n), font=_font(LATO, 24), fill=MUTED, anchor="lm")
    y += box_h + GAP

    if months:
        _month_chart(img, (PAD, y, W - PAD, y + MONTH_CHART_H), "Aktywność miesiąc po miesiącu", months, accent)
        y += MONTH_CHART_H + GAP

    cw = (W - 2 * PAD - GAP) / 2
    bd = s.get("busiest_day")
    tv = s.get("top_voice") or []
    owl = s.get("night_owl")
    chans = s.get("top_channels") or []
    tiles = [
        ("Voice razem", fmt_hours(s["voice_hours"]) if s["voice_hours"] else "—",
         (f"{names.get(tv[0][0], '?')}: {fmt_hours(tv[0][1])}" if tv else "") + _voice_note(s)),
        ("Najgłośniejszy dzień", (pl_date(bd[0]) if months else pl_date(bd[0]).rsplit(" ", 1)[0]) if bd else "—", f"{fmt_int(bd[1])} wiadomości" if bd else ""),
        (f"Kanał {noun}", "#" + chans[0][0].split("┃")[-1] if chans else "—", f"{fmt_int(chans[0][1])} wiadomości" if chans else ""),
        ("Nocny Marek", names.get(owl[0], "?") if owl else "—", f"{round(owl[1] * 100)}% wiadomości między 0 a 5" if owl else "nikt nie pisze w nocy"),
        ("Ulubione reakcje", "  ".join(e for e, _ in (s.get("top_emoji") or [])[:4]) or "—",
         " · ".join(fmt_int(n) for _, n in (s.get("top_emoji") or [])[:4])),
        ("Aktywnych dni", str(s["active_days"]), "z przynajmniej jedną wiadomością"),
    ]
    for i, (label, value, sub) in enumerate(tiles):
        cx = PAD + (i % 2) * (cw + GAP)
        cy = y + (i // 2) * (th + GAP)
        text_value = label in (f"Kanał {noun}", "Nocny Marek", "Najgłośniejszy dzień")
        size = 40 if label == "Ulubione reakcje" else (44 if text_value else 58)
        _tile(img, (cx, cy, cx + cw, cy + th), label, value, sub, emojis,
              value_font=LATO_BLACK if text_value else ANTON, value_size=size)
    y += 3 * (th + GAP)

    if first:
        _best_message(img, (PAD, y, W - PAD, y + 210), "Pierwsza wiadomość",
                      clean_text(first["message"], limit=160),
                      f"{names.get(first['user_id'], '?')} · {pl_date(first['date'])} · #{first['channel_name'].split('┃')[-1]}",
                      emojis, accent)
        y += 210 + GAP

    if best:
        _best_message(img, (PAD, y, W - PAD, H - PAD),
                      f"Wiadomość {noun} · {best['n']} os. zareagowało",
                      clean_text(best["message"]),
                      f"{names.get(best['author'], '?')} · {pl_date(best['msg_date'])} · #{best['channel_name'].split('┃')[-1]}",
                      emojis, accent)
    return _to_png(img)


# --- long ranking ("topka") ---

RANK_TITLES = {
    "wiadomosci": "Najwięcej wiadomości",
    "voice": "Najwięcej godzin na voice",
    "reakcje": "Najwięcej otrzymanych reakcji",
}


def _fmt_metric(metric, v):
    return fmt_hours(v) if metric == "voice" else fmt_int(v)


def render_leaderboard(lb, guild_name, icon_bytes, names, avatars, me_id=None, emojis=None):
    """
    lb: utilities.wrapped.leaderboard() dict; names/avatars: user_id -> display
    name / avatar bytes. One row per person: rank, avatar, name, a thin bar
    (one series, one hue, scaled to #1) and the value as a direct label. The
    requester's row is highlighted; if they are outside the top, their row is
    appended after a gap. Returns PNG bytes, 1080 wide.
    """
    W, PAD, GAP = 1080, 60, 22
    ROW = 62
    accent = accent_from(icon_bytes)
    color = _readable(accent)
    rows, mine, metric = lb["rows"], lb.get("mine"), lb["metric"]
    n_rows = len(rows) + (1 if mine else 0)
    list_h = 84 + ROW * n_rows + (30 if mine else 0) + 8
    H = PAD + 120 + 120 + list_h + 50 + PAD
    img = _bg(W, H, accent)
    _header(img, W, PAD, accent, lb["period"], title="RANKING")
    d = ImageDraw.Draw(img)

    y = PAD + 120
    icon = circle_avatar(icon_bytes, 88, guild_name)
    img.paste(icon, (PAD, y), icon)
    tf, tl, th = fit_text(RANK_TITLES.get(metric, ""), LATO_BLACK, W - 2 * PAD - 116, 60, start=46, minimum=28)
    draw_lines(img, tl[:1], tf, th, PAD + 116, y + 2, W - 2 * PAD - 116, FG, emojis)
    d.text((PAD + 116, y + 62), sanitize(guild_name), font=_font(LATO, 26), fill=MUTED)

    y += 120
    box = (PAD, y, W - PAD, y + list_h)
    d.rounded_rectangle(box, radius=22, fill=CARD)
    d.text((PAD + 28, y + 24), f"TOP {len(rows)} Z {lb['total']} OSÓB", font=_font(LATO_BOLD, 22), fill=MUTED)
    top = rows[0][2] if rows and rows[0][2] else 1
    rank_w, av_s, name_w = 64, 40, 290
    name_x = PAD + 28 + rank_w + av_s + 16
    bar_l, bar_r = name_x + name_w + 16, W - PAD - 150
    rf, nf, vf = _font(ANTON, 30), _font(LATO_BOLD, 27), _font(LATO, 24)

    def row(ry, rank, uid, val):
        if uid == me_id:
            d.rounded_rectangle((PAD + 12, ry - 6, W - PAD - 12, ry + ROW - 12), radius=14, fill=(48, 50, 57))
        cy = ry + (ROW - 12) / 2 - 3
        d.text((PAD + 28 + rank_w - 14, cy), str(rank), font=rf, fill=FG if rank <= 3 else MUTED, anchor="rm")
        av = circle_avatar(avatars.get(uid), av_s, names.get(uid, "?"))
        img.paste(av, (int(PAD + 28 + rank_w), int(cy - av_s / 2)), av)
        nm = sanitize(names.get(uid, str(uid)))
        while nf.getlength(nm) > name_w and len(nm) > 3:
            nm = nm[:-2] + "…"
        d.text((name_x, cy), nm, font=nf, fill=FG, anchor="lm")
        bw = max(6, (bar_r - bar_l) * float(val) / float(top))
        d.rounded_rectangle((bar_l, cy - 11, bar_l + bw, cy + 11), radius=4, fill=color)
        d.text((bar_l + bw + 12, cy), _fmt_metric(metric, val), font=vf, fill=MUTED, anchor="lm")

    ry = y + 76
    for rank, uid, val in rows:
        row(ry, rank, uid, val)
        ry += ROW
    if mine:
        d.text((PAD + 28 + rank_w - 14, ry + 2), "· · ·", font=_font(LATO_BOLD, 24), fill=MUTED, anchor="rm")
        ry += 30
        row(ry, *mine)

    y += list_h + 24
    total = f"razem {_fmt_metric(metric, lb['sum'])}"
    v = lb.get("voice_since")
    if v:
        total += f" · voice liczony od {v.day}.{v.month:02d}.{v.year}"
    d.text((PAD, y + 8), total, font=_font(LATO, 26), fill=MUTED)
    return _to_png(img)
