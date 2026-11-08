"""
Semester / all-time summary ("KNI Wrapped") statistics, computed from what the bot already
logs: messages, voice sessions and reaction events.

Pure data layer - no Discord, no drawing. Every function takes `q(sql, params)`
returning a list of dicts (Database.fetch_all_dict in the bot), so it can be
exercised against the real database with plain psycopg2.

Counting rules:
- messages: originals only (`NOT is_edited` - edits are logged as new rows),
  humans only (`NOT is_bot`), one guild, [start, end) in Europe/Warsaw.
  Exception: a personal card asked for a bot (Fryderyk's own, %(me)s) also
  counts that one bot, so it gets ranked among the humans;
- reactions: events 'reaction' / 'reaction (backfilled)', about = "added <emoji>
  to message id <discord_id>", joined to the message to know its author;
  self-reactions don't count;
- voice: sessions whose join time falls in the window (voice logging started
  2026-05-29, so older semesters have no voice data).
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

TZ = ZoneInfo("Europe/Warsaw")


@dataclass(frozen=True)
class Semester:
    name: str
    start: datetime
    end: datetime   # exclusive
    noun: str = "semestru"   # genitive for labels: "Gaduła semestru", "Kanał wszech czasów"
    all_time: bool = False


def semester_for(day: date) -> Semester:
    """Winter = 1 Oct .. end of Feb, summer = 1 Mar .. end of Sep (Polish academic year)."""
    y = day.year
    if day.month >= 10:
        s, e, name = date(y, 10, 1), date(y + 1, 3, 1), f"Semestr zimowy {y}/{str(y + 1)[2:]}"
    elif day.month <= 2:
        s, e, name = date(y - 1, 10, 1), date(y, 3, 1), f"Semestr zimowy {y - 1}/{str(y)[2:]}"
    else:
        s, e, name = date(y, 3, 1), date(y, 10, 1), f"Semestr letni {y - 1}/{str(y)[2:]}"
    as_dt = lambda d: datetime(d.year, d.month, d.day, tzinfo=TZ)
    return Semester(name, as_dt(s), as_dt(e))


def previous_semester(sem: Semester) -> Semester:
    return semester_for((sem.start - timedelta(days=1)).date())


def all_time(since: datetime, now: datetime) -> Semester:
    """The whole history of a server: from its creation until now."""
    since, now = since.astimezone(TZ), now.astimezone(TZ)
    years = str(since.year) if since.year == now.year else f"{since.year}–{now.year}"
    return Semester(f"Od początku serwera · {years}", since, now + timedelta(days=1), "wszech czasów", True)


def _months(q, sql, p, sem: Semester):
    """[(first day of month, n)] for every month of the window, gaps filled with 0."""
    got = {r["m"]: int(r["n"]) for r in q(sql, p)}
    first = sem.start.date().replace(day=1)
    last = (min(sem.end, datetime.now(TZ)) - timedelta(seconds=1)).date().replace(day=1)
    out, m = [], first
    while m <= last:
        out.append((m, got.get(m, 0)))
        m = (m + timedelta(days=32)).replace(day=1)
    return out


def _voice_since(q, p):
    """When voice logging actually starts inside the window (it began 2026-05-29)."""
    r = _one(q("""SELECT min(date_join) AS d FROM voice
        WHERE guild_id = %(g)s AND date_join >= %(s)s AND date_join < %(e)s""", p))
    return r["d"].astimezone(TZ).date() if r and r.get("d") else None


# Shared CTEs. %(g)s guild, %(s)s/%(e)s window.
_MSGS = """
msgs AS (
    SELECT user_id, channel_id, channel_name, date, discord_id, reply_to_id, message
    FROM messages
    WHERE guild_id = %(g)s AND date >= %(s)s AND date < %(e)s
      AND (NOT is_bot OR user_id = %(me)s) AND NOT is_edited
)"""
_REACTS = """
reacts AS (
    SELECT ev.user_id AS reactor,
           substring(ev.about from '^added (.+) to message id \\d+$') AS emoji,
           m.user_id AS author, m.discord_id, m.message, m.channel_id, m.channel_name, m.date AS msg_date
    FROM events ev
    JOIN messages m
      ON m.discord_id = substring(ev.about from 'message id (\\d+)$')::bigint
     AND NOT m.is_edited
    WHERE ev.guild_id = %(g)s AND ev.what IN ('reaction', 'reaction (backfilled)')
      AND ev.date >= %(s)s AND ev.date < %(e)s
      AND NOT ev.is_bot AND (NOT m.is_bot OR m.user_id = %(me)s)
      AND ev.user_id <> m.user_id
)"""


def _one(rows):
    return rows[0] if rows else None


def user_stats(q, guild_id, user_id, sem: Semester, public_channels=()):
    """public_channels: ids readable by @everyone - only these may show up as
    channel names or quoted text (cards are posted publicly). Counts use all."""
    p = {"g": guild_id, "u": user_id, "me": user_id, "s": sem.start, "e": sem.end, "pub": list(public_channels) or [0]}
    out = {"user_id": user_id, "semester": sem.name}

    counts = _one(q(f"""WITH {_MSGS},
        c AS (SELECT user_id, count(*) AS n FROM msgs GROUP BY user_id)
        SELECT n, rnk, total_users, total_msgs FROM (
            SELECT user_id, n, rank() OVER (ORDER BY n DESC) AS rnk,
                   count(*) OVER () AS total_users, sum(n) OVER () AS total_msgs
            FROM c) x
        WHERE user_id = %(u)s""", p)) or {}
    out["messages"] = int(counts.get("n") or 0)
    out["rank"] = counts.get("rnk")
    out["total_users"] = counts.get("total_users")
    out["share"] = (out["messages"] / float(counts["total_msgs"])) if counts.get("total_msgs") else 0.0

    days = q(f"""WITH {_MSGS}
        SELECT DISTINCT (date AT TIME ZONE 'Europe/Warsaw')::date AS d
        FROM msgs WHERE user_id = %(u)s ORDER BY d""", p)
    ds = [r["d"] for r in days]
    out["active_days"] = len(ds)
    best = run = 0
    for i, d in enumerate(ds):
        run = run + 1 if i and (d - ds[i - 1]).days == 1 else 1
        best = max(best, run)
    out["streak"] = best

    ch = _one(q(f"""WITH {_MSGS}
        SELECT channel_name, count(*) AS n FROM msgs WHERE user_id = %(u)s AND channel_id = ANY(%(pub)s)
        GROUP BY channel_name ORDER BY n DESC LIMIT 1""", p))
    out["top_channel"] = (ch["channel_name"], int(ch["n"])) if ch else None

    hours = q(f"""WITH {_MSGS}
        SELECT extract(hour FROM date AT TIME ZONE 'Europe/Warsaw')::int AS h, count(*) AS n
        FROM msgs WHERE user_id = %(u)s GROUP BY h""", p)
    hist = {int(r["h"]): int(r["n"]) for r in hours}
    out["hours"] = [hist.get(h, 0) for h in range(24)]
    out["peak_hour"] = max(hist, key=hist.get) if hist else None
    out["night_share"] = (sum(hist.get(h, 0) for h in range(0, 5)) / out["messages"]) if out["messages"] else 0.0

    voice = _one(q("""WITH v AS (
            SELECT user_id, sum(time_on) AS secs FROM voice
            WHERE guild_id = %(g)s AND date_join >= %(s)s AND date_join < %(e)s AND NOT is_bot
            GROUP BY user_id)
        SELECT secs, rnk FROM (SELECT user_id, secs, rank() OVER (ORDER BY secs DESC) AS rnk FROM v) x
        WHERE user_id = %(u)s""", p)) or {}
    out["voice_hours"] = round(float(voice.get("secs") or 0) / 3600, 1)
    out["voice_rank"] = voice.get("rnk")

    rec = _one(q(f"""WITH {_REACTS}
        SELECT count(*) AS n FROM reacts WHERE author = %(u)s""", p)) or {}
    out["reactions_received"] = int(rec.get("n") or 0)
    top_rec = q(f"""WITH {_REACTS}
        SELECT emoji, count(*) AS n FROM reacts WHERE author = %(u)s
        GROUP BY emoji ORDER BY n DESC LIMIT 3""", p)
    out["top_emoji_received"] = [(r["emoji"], int(r["n"])) for r in top_rec]
    given = _one(q(f"""WITH {_REACTS}
        SELECT count(*) AS n FROM reacts WHERE reactor = %(u)s""", p)) or {}
    out["reactions_given"] = int(given.get("n") or 0)

    best_msg = _one(q(f"""WITH {_REACTS}
        SELECT discord_id, message, channel_name, msg_date, count(DISTINCT reactor) AS n
        FROM reacts WHERE author = %(u)s AND coalesce(message, '') <> '' AND channel_id = ANY(%(pub)s)
        GROUP BY discord_id, message, channel_name, msg_date
        ORDER BY n DESC, msg_date DESC LIMIT 1""", p))
    out["best_message"] = dict(best_msg) if best_msg else None

    duo = _one(q(f"""WITH {_MSGS},
        pairs AS (
            SELECT CASE WHEN a.user_id = %(u)s THEN b.user_id ELSE a.user_id END AS other
            FROM msgs a JOIN messages b ON b.discord_id = a.reply_to_id
            WHERE (a.user_id = %(u)s OR b.user_id = %(u)s) AND a.user_id <> b.user_id AND (NOT b.is_bot OR b.user_id = %(u)s)
        )
        SELECT other, count(*) AS n FROM pairs GROUP BY other ORDER BY n DESC LIMIT 1""", p))
    out["duo"] = (duo["other"], int(duo["n"])) if duo else None

    if sem.all_time:
        out["months"] = _months(q, f"""WITH {_MSGS}
            SELECT date_trunc('month', date AT TIME ZONE 'Europe/Warsaw')::date AS m, count(*) AS n
            FROM msgs WHERE user_id = %(u)s GROUP BY m""", p, sem)
        out["voice_since"] = _voice_since(q, p)
    out["noun"] = sem.noun
    out["titles"] = titles(out)
    return out


def server_stats(q, guild_id, sem: Semester, public_channels=()):
    p = {"g": guild_id, "me": 0, "s": sem.start, "e": sem.end, "pub": list(public_channels) or [0]}
    out = {"semester": sem.name, "noun": sem.noun}
    tot = _one(q(f"""WITH {_MSGS}
        SELECT count(*) AS n, count(DISTINCT user_id) AS users,
               count(DISTINCT (date AT TIME ZONE 'Europe/Warsaw')::date) AS days FROM msgs""", p)) or {}
    out["messages"] = int(tot.get("n") or 0)
    out["active_users"] = int(tot.get("users") or 0)
    out["active_days"] = int(tot.get("days") or 0)

    out["top_talkers"] = [(r["user_id"], int(r["n"])) for r in q(f"""WITH {_MSGS}
        SELECT user_id, count(*) AS n FROM msgs GROUP BY user_id ORDER BY n DESC LIMIT 5""", p)]
    out["top_channels"] = [(r["channel_name"], int(r["n"])) for r in q(f"""WITH {_MSGS}
        SELECT channel_name, count(*) AS n FROM msgs WHERE channel_id = ANY(%(pub)s)
        GROUP BY channel_name ORDER BY n DESC LIMIT 3""", p)]
    day = _one(q(f"""WITH {_MSGS}
        SELECT (date AT TIME ZONE 'Europe/Warsaw')::date AS d, count(*) AS n FROM msgs
        GROUP BY d ORDER BY n DESC LIMIT 1""", p))
    out["busiest_day"] = (day["d"], int(day["n"])) if day else None

    v = _one(q("""SELECT sum(time_on) AS secs FROM voice
        WHERE guild_id = %(g)s AND date_join >= %(s)s AND date_join < %(e)s AND NOT is_bot""", p)) or {}
    out["voice_hours"] = round(float(v.get("secs") or 0) / 3600)
    out["top_voice"] = [(r["user_id"], round(float(r["secs"]) / 3600, 1)) for r in q("""
        SELECT user_id, sum(time_on) AS secs FROM voice
        WHERE guild_id = %(g)s AND date_join >= %(s)s AND date_join < %(e)s AND NOT is_bot
        GROUP BY user_id ORDER BY secs DESC LIMIT 3""", p)]

    out["top_emoji"] = [(r["emoji"], int(r["n"])) for r in q(f"""WITH {_REACTS}
        SELECT emoji, count(*) AS n FROM reacts GROUP BY emoji ORDER BY n DESC LIMIT 5""", p)]
    best = _one(q(f"""WITH {_REACTS}
        SELECT author, discord_id, message, channel_name, msg_date, count(DISTINCT reactor) AS n
        FROM reacts WHERE coalesce(message, '') <> '' AND channel_id = ANY(%(pub)s)
        GROUP BY author, discord_id, message, channel_name, msg_date
        ORDER BY n DESC, msg_date DESC LIMIT 1""", p))
    out["best_message"] = dict(best) if best else None

    owl = _one(q(f"""WITH {_MSGS}
        SELECT user_id, avg((extract(hour FROM date AT TIME ZONE 'Europe/Warsaw') < 5)::int) AS night, count(*) AS n
        FROM msgs GROUP BY user_id HAVING count(*) >= 50 ORDER BY night DESC LIMIT 1""", p))
    out["night_owl"] = (owl["user_id"], float(owl["night"])) if owl and float(owl["night"]) >= 0.15 else None

    if sem.all_time:
        out["months"] = _months(q, f"""WITH {_MSGS}
            SELECT date_trunc('month', date AT TIME ZONE 'Europe/Warsaw')::date AS m, count(*) AS n
            FROM msgs GROUP BY m""", p, sem)
        out["voice_since"] = _voice_since(q, p)
        first = _one(q(f"""WITH {_MSGS}
            SELECT user_id, message, channel_name, date FROM msgs
            WHERE channel_id = ANY(%(pub)s) AND coalesce(message, '') <> ''
            ORDER BY date LIMIT 1""", p))
        out["first_message"] = dict(first) if first else None
    return out


def titles(s):
    """1-3 fun labels derived from the numbers, most specific first."""
    t = []
    if s.get("rank") == 1:
        t.append(f"Gaduła {s.get('noun', 'semestru')}")
    elif s.get("rank") and s["rank"] <= 3:
        t.append(f"Podium gadania (#{s['rank']})")
    if s.get("night_share", 0) >= 0.25 and s.get("messages", 0) >= 30:
        t.append("Nocny Marek")
    if s.get("voice_rank") == 1:
        t.append("Król voice'a")
    if s.get("streak", 0) >= 14:
        t.append(f"Seria {s['streak']} dni z rzędu")
    if s.get("reactions_received", 0) >= 50:
        t.append("Magnes na reakcje")
    if not t and s.get("messages", 0):
        t.append("Cichy obserwator" if s["messages"] < 30 else "Stały bywalec")
    return t[:3]


METRICS = {
    "wiadomosci": "wiadomości",
    "voice": "godziny na voice",
    "reakcje": "otrzymane reakcje",
}


def leaderboard(q, guild_id, sem: Semester, metric="wiadomosci", limit=15, me=None):
    """
    Long ranking ("topka") for one metric: humans only. Returns
    {"rows": [(rank, user_id, value)], "total": participants, "mine": (rank, user_id, value) | None,
     "sum": value summed over everyone}. `mine` is set only when `me` is ranked but outside the top `limit`.
    Voice values are hours (voice logging started 2026-05-29).
    """
    p = {"g": guild_id, "me": 0, "s": sem.start, "e": sem.end}
    if metric == "voice":
        base = """v AS (SELECT user_id, sum(time_on) / 3600.0 AS val FROM voice
                   WHERE guild_id = %(g)s AND date_join >= %(s)s AND date_join < %(e)s AND NOT is_bot
                   GROUP BY user_id HAVING sum(time_on) > 0)"""
    elif metric == "reakcje":
        base = f"""{_REACTS}, v AS (SELECT author AS user_id, count(*)::numeric AS val FROM reacts GROUP BY author)"""
    else:
        base = f"""{_MSGS}, v AS (SELECT user_id, count(*)::numeric AS val FROM msgs GROUP BY user_id)"""
    rows = q(f"""WITH {base},
        r AS (SELECT user_id, val, rank() OVER (ORDER BY val DESC) AS rnk,
                     row_number() OVER (ORDER BY val DESC, user_id) AS rn,
                     count(*) OVER () AS total, sum(val) OVER () AS everyone FROM v)
        SELECT user_id, val, rnk, rn, total, everyone FROM r
        WHERE rn <= %(lim)s OR user_id = %(who)s ORDER BY rn""", {**p, "lim": int(limit), "who": int(me or 0)})
    fmt = (lambda v: round(float(v), 1)) if metric == "voice" else (lambda v: int(v))
    top = [(int(r["rnk"]), int(r["user_id"]), fmt(r["val"])) for r in rows if int(r["rn"]) <= limit]
    mine = next(((int(r["rnk"]), int(r["user_id"]), fmt(r["val"])) for r in rows
                 if int(r["rn"]) > limit), None)
    since = _voice_since(q, p) if metric == "voice" else None
    if since and (since - sem.start.date()).days < 7:
        since = None   # logging covers the whole window, nothing to explain
    return {
        "period": sem.name, "metric": metric, "rows": top, "mine": mine, "voice_since": since,
        "total": int(rows[0]["total"]) if rows else 0,
        "sum": fmt(rows[0]["everyone"]) if rows else 0,
    }
