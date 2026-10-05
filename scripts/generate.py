"""Render the neon terminal-style SVGs used by the profile README.

Pulls live data from the GitHub GraphQL API and writes:
  assets/hero.svg      window with dotted portrait + SYSTEM.INFO + streak row
  assets/stats.svg     GitHub stats and top languages
  assets/projects.svg  ./projects.sh --all project cards

Token: $GITHUB_TOKEN (Actions) or `gh auth token` locally.
"""

import datetime as dt
import json
import math
import os
import subprocess
import urllib.request
from html import escape
from pathlib import Path

from PIL import Image, ImageOps

USER = "himanshu-gupta15"
ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
PORTRAIT = ASSETS / "avatar.jpg"

FONT = "'JetBrains Mono','Fira Code','SFMono-Regular',Menlo,Consolas,'Liberation Mono',monospace"
# Calm midnight palette: soft pastels on a slate-indigo base, easy on the eyes.
BG = "#0d1020"
PANEL = "url(#panel)"
CYAN = "#8ecdf0"
PINK = "#eba7c8"
VIOLET = "#a99cf0"
MINT = "#93d9b4"
TEXT = "#dfe3f5"
MUTED = "#8a90b8"
LINE = "#262b4d"
FAINT = "#565b8a"

PROFILE = [
    ("Subject", "Himanshu Gupta"),
    ("Role", "AI Full Stack Intern @ The AI Signal"),
    ("Origin", "Mau, Uttar Pradesh, India"),
    ("Education", "B.Tech CSE @ IIIT Sonepat"),
    ("Status", "Building multi-agent AI systems"),
    ("ToolChain", "VS Code · Git · Docker · Postman"),
    None,
    ("Core.Lang", "C++, TypeScript, JavaScript, Python"),
    ("Core.Frontend", "React, Next.js, Redux, Tailwind"),
    ("Core.Backend", "Node.js, Express, Kafka, Redis"),
    ("Core.Database", "PostgreSQL, MongoDB, MySQL, Firebase"),
    ("Core.AI", "LangGraph, LangChain, RAG, Qdrant"),
    ("Core.Infra", "AWS, Docker, GitHub Actions, Vercel"),
    "- Contact",
    ("Grid.Mail", "himanshugpt0005@gmail.com"),
    ("Grid.Portfolio", "portfoliohimanshugupta.netlify.app"),
    ("Grid.LinkedIn", "in/himanshu-gupta27"),
    ("Grid.LeetCode", "himanshu8083 · Knight 1900+"),
    ("Grid.CodeChef", "himanshugpt80 · 4★ 1800+"),
]

# (repo, display title, description lines, tags)
PROJECTS = [
    ("MultiMind", "MultiMind", ["Multi-agent AI platform: 5 microservices,",
                                "8+ LangGraph agents, Qdrant-backed RAG"],
     ["LangGraph", "React", "Docker"]),
    ("DrawixAi", "DravixAI", ["Voice agents grounded in a knowledge base,",
                              "local ONNX embeddings + Whisper ASR"],
     ["Next.js", "RAG", "Voice"]),
    ("JobPortal", "CareerLaunch", ["AI job portal: Kafka events, Redis cache",
                                   "(-40% latency), Gemini resume screening"],
     ["Next.js", "Kafka", "Gemini"]),
    ("Brainwave_weather_bot", "Brainwave", ["Weather-safety chat bot: a rule engine",
                                            "decides, the LLM only words the answer"],
     ["LangGraph.js", "Open-Meteo"]),
    ("Alogrise", "ALGORISE", ["Competitive programming arena with live",
                              "leaderboards and XP gamification"],
     ["MERN", "Redux", "Redis"]),
    ("College-Finder", "CollegeFinder", ["College discovery and comparison",
                                         "platform for Indian higher education"],
     ["Next.js", "React 19", "Tailwind"]),
]


# ---------------------------------------------------------------- data

def token():
    t = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if t:
        return t
    return subprocess.check_output(["gh", "auth", "token"], text=True).strip()


def gql(query, **variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={"Authorization": "bearer " + token(), "User-Agent": USER},
    )
    with urllib.request.urlopen(req) as r:
        body = json.load(r)
    if body.get("errors"):
        raise RuntimeError(body["errors"])
    return body["data"]


def fetch():
    base = gql("""
    query($login: String!) {
      user(login: $login) {
        createdAt
        followers { totalCount }
        repositories(ownerAffiliations: OWNER, isFork: false, first: 100) {
          totalCount
          nodes {
            name stargazerCount pushedAt
            languages(first: 10, orderBy: {field: SIZE, direction: DESC}) {
              edges { size node { name color } }
            }
          }
        }
        repositoriesContributedTo(first: 1, contributionTypes: [COMMIT, PULL_REQUEST, ISSUE, REPOSITORY]) { totalCount }
        contributionsCollection {
          totalCommitContributions totalPullRequestContributions
          totalIssueContributions restrictedContributionsCount
        }
      }
    }""", login=USER)["user"]

    # Contribution calendar for every year since the account was created.
    days = {}
    start = dt.datetime.fromisoformat(base["createdAt"].replace("Z", "+00:00")).year
    now = dt.datetime.now(dt.timezone.utc)
    for year in range(start, now.year + 1):
        frm = dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc)
        to = min(dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=dt.timezone.utc), now)
        cal = gql("""
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              contributionCalendar { weeks { contributionDays { date contributionCount } } }
            }
          }
        }""", login=USER, **{"from": frm.isoformat(), "to": to.isoformat()})
        for w in cal["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]
    return base, days


def streaks(days):
    ordered = sorted(days.items())
    longest = run = 0
    for _, n in ordered:
        run = run + 1 if n > 0 else 0
        longest = max(longest, run)
    # Current streak: today may still be empty without breaking the streak.
    current = 0
    for i, (_, n) in enumerate(reversed(ordered)):
        if n > 0:
            current += 1
        elif i > 0:
            break
    return current, longest


IGNORED_LANGS = {"Jupyter Notebook", "Cython", "Fortran", "C", "PowerShell", "Batchfile", "Shell", "Dockerfile", "Procfile", "Makefile"}


def lang_totals(repos):
    """Share of each language, with every repo weighted equally."""
    totals, colors = {}, {}
    for r in repos:
        edges = [e for e in r["languages"]["edges"] if e["node"]["name"] not in IGNORED_LANGS]
        size = float(sum(e["size"] for e in edges))
        for e in edges:
            name = e["node"]["name"]
            totals[name] = totals.get(name, 0) + e["size"] / size
            colors[name] = soften(e["node"]["color"] or MUTED)
    return totals, colors


def ago(iso):
    then = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    s = (dt.datetime.now(dt.timezone.utc) - then).total_seconds()
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if s >= size:
            return "%d%s ago" % (s // size, unit)
    return "just now"


# ---------------------------------------------------------------- svg helpers

def e(s):
    return escape(str(s), quote=True)


def defs():
    return """
  <defs>
    <linearGradient id="neon" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="%s"/><stop offset=".5" stop-color="%s"/><stop offset="1" stop-color="%s"/>
    </linearGradient>
    <filter id="glow" x="-20%%" y="-20%%" width="140%%" height="140%%">
      <feGaussianBlur stdDeviation="3" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="softglow" x="-50%%" y="-50%%" width="200%%" height="200%%">
      <feGaussianBlur stdDeviation="1.1" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <linearGradient id="panel" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#181d3b"/><stop offset="1" stop-color="#10132a"/>
    </linearGradient>
    <linearGradient id="sheen" gradientUnits="userSpaceOnUse" x1="-360" y1="0" x2="0" y2="0">
      <stop offset="0" stop-color="#ffffff" stop-opacity="0"/>
      <stop offset=".5" stop-color="#e8f4ff" stop-opacity="1"/>
      <stop offset="1" stop-color="#ffffff" stop-opacity="0"/>
      <animateTransform attributeName="gradientTransform" type="translate" values="0 0;1300 0;1300 0" keyTimes="0;.6;1" dur="8s" repeatCount="indefinite"/>
    </linearGradient>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M28 0H0V28" fill="none" stroke="#171b36" stroke-width=".6"/>
    </pattern>
  </defs>""" % (CYAN, VIOLET, PINK)


def svg(w, h, body, style=""):
    return """<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" viewBox="0 0 %d %d" font-family="%s">
  <style>
    text { font-family: %s; }
    @keyframes fadeUp { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
    @keyframes blink { 50%% { opacity: 0; } }
    @keyframes pulse { 0%%, 100%% { opacity: .55; } 50%% { opacity: 1; } }
    .reveal { animation: fadeUp .5s ease-out both; }
    .cursor { animation: blink 1s steps(1) infinite; }
    .pulse { animation: pulse 2.4s ease-in-out infinite; }
    %s
  </style>%s
  <rect width="100%%" height="100%%" rx="16" fill="%s"/>
  <rect width="100%%" height="100%%" rx="16" fill="url(#grid)" opacity=".4"/>
%s
</svg>
""" % (w, h, w, h, e(FONT), FONT, style, defs(), BG, body)


def window(x, y, w, h, title_right=""):
    return """
  <rect x="%d" y="%d" width="%d" height="%d" rx="14" fill="%s" stroke="%s" stroke-width="2" filter="url(#glow)" opacity=".3"/>
  <rect x="%d" y="%d" width="%d" height="%d" rx="14" fill="%s" stroke="%s" stroke-opacity=".5" stroke-width="1.2"/>
  <rect x="%d" y="%d" width="%d" height="%d" rx="14" fill="none" stroke="url(#sheen)" stroke-width="2.2" filter="url(#softglow)"/>
  <circle cx="%d" cy="%d" r="6" fill="#ff5f57"/><circle cx="%d" cy="%d" r="6" fill="#febc2e"/><circle cx="%d" cy="%d" r="6" fill="#28c840"/>
  <line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s"/>
  <text x="%d" y="%d" text-anchor="end" font-size="12" fill="%s" font-weight="700">%s</text>""" % (
        x, y, w, h, PANEL, CYAN,
        x, y, w, h, PANEL, CYAN,
        x, y, w, h,
        x + 24, y + 22, x + 44, y + 22, x + 64, y + 22,
        x, y + 44, x + w, y + 44, LINE,
        x + w - 22, y + 26, TEXT, e(title_right))


def brackets(x, y, w, h, n=14, color=CYAN):
    p = "M{0} {1}v-{n}h{n} M{2} {1}v-{n}h-{n} M{0} {3}v{n}h{n} M{2} {3}v{n}h-{n}"
    d = p.format(x, y + n, x + w, y + h - n, n=n)
    return '<path d="%s" fill="none" stroke="%s" stroke-width="2"/>' % (d, color)


def soften(c):
    return lerp_color(c, "#9aa0c8", .35)


def lerp_color(a, b, t):
    a, b = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def _stroke(rng, n, pts, thick):
    """n points scattered along a polyline with some thickness (unit coords)."""
    segs = list(zip(pts, pts[1:]))
    lens = [math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in segs]
    out = []
    for _ in range(n):
        k = rng.choices(range(len(segs)), weights=lens)[0]
        (ax, ay), (bx, by) = segs[k]
        t = rng.random()
        nx, ny = -(by - ay) / lens[k], (bx - ax) / lens[k]
        o = rng.uniform(-thick, thick)
        out.append((ax + (bx - ax) * t + nx * o, ay + (by - ay) * t + ny * o))
    return out


def shape_code(rng, n):
    # </>
    parts = [([(.30, .26), (.10, .50), (.30, .74)], .30),
             ([(.70, .26), (.90, .50), (.70, .74)], .30),
             ([(.58, .18), (.42, .82)], .40)]
    out = []
    for pts, share in parts:
        out += _stroke(rng, int(n * share), pts, .035)
    return (out + _stroke(rng, n - len(out), parts[2][0], .035))[:n]


def shape_atom(rng, n):
    out = []
    for i in range(n):
        if i < n * .1:
            a, r = rng.uniform(0, 2 * math.pi), .07 * math.sqrt(rng.random())
            out.append((.5 + r * math.cos(a), .5 + r * math.sin(a)))
            continue
        rot = math.radians(60 * (i % 3))
        t = rng.uniform(0, 2 * math.pi)
        ex, ey = .42 * math.cos(t), .16 * math.sin(t) + rng.uniform(-.012, .012)
        out.append((.5 + ex * math.cos(rot) - ey * math.sin(rot), .5 + ex * math.sin(rot) + ey * math.cos(rot)))
    return out


def shape_triangle(rng, n):
    a, b, c = (.5, .17), (.13, .80), (.87, .80)
    out = []
    for _ in range(n):
        u, v = rng.random(), rng.random()
        if u + v > 1:
            u, v = 1 - u, 1 - v
        out.append((a[0] + u * (b[0] - a[0]) + v * (c[0] - a[0]), a[1] + u * (b[1] - a[1]) + v * (c[1] - a[1])))
    return out


def portrait_image():
    img = Image.open(PORTRAIT).convert("L")
    side = min(img.size)
    return ImageOps.autocontrast(ImageOps.fit(img, (side, side), centering=(0.5, 0.0)), cutoff=2)


def shape_portrait(rng, n):
    img = portrait_image().resize((120, 120), Image.LANCZOS)
    px = [(i, j, img.getpixel((i, j)) / 255) for j in range(120) for i in range(120)]
    px = [p for p in px if p[2] > .2]
    picks = rng.choices(px, weights=[p[2] ** 2 for p in px], k=n)
    return [((i + rng.random()) / 120, (j + rng.random()) / 120) for i, j, _ in picks]


def duotone_uri(size):
    import base64
    import io
    img = ImageOps.colorize(portrait_image().resize((size, size), Image.LANCZOS),
                            black="#0b0d1f", mid="#7867c9", white="#e8e1fb", midpoint=110)
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=78)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def morph(x, y, w, h, n=700, cycle=16):
    """Particles flying between shapes: </>, React atom, triangle, portrait."""
    import random
    rng = random.Random(7)  # deterministic, so the SVG only changes when data does
    shapes = [shape_code(rng, n), shape_atom(rng, n), shape_triangle(rng, n), shape_portrait(rng, n)]
    for sh in shapes:
        rng.shuffle(sh)
    hold, move = .1875, .0625  # per shape: 3s hold, 1s flight (16s cycle)
    times, ease = ["0"], []
    for i in range(len(shapes)):
        times += ["%.4g" % ((i * (hold + move)) + hold), "%.4g" % ((i + 1) * (hold + move))]
        ease += ["0 0 1 1", ".7 0 .2 1"]
    kt, ks = ";".join(times), ";".join(ease)
    palette = ["#e9c3f2", "#cfc6f8", "#bfd4f5", "#efc0d8", "#d6cbf6"]
    out = ['<image href="%s" x="%d" y="%d" width="%d" height="%d" opacity="0">'
           '<animate attributeName="opacity" dur="%ds" repeatCount="indefinite" keyTimes="0;.80;.85;.92;.95;1" values="0;0;.95;.95;0;0"/></image>'
           % (duotone_uri(320), x, y, w, h, cycle)]
    out.append('<g filter="url(#softglow)"><animate attributeName="opacity" dur="%ds" repeatCount="indefinite" '
               'keyTimes="0;.80;.85;.92;.95;1" values="1;1;.18;.18;1;1"/>' % cycle)
    anim = '<animate attributeName="%s" dur="%ds" repeatCount="indefinite" calcMode="spline" keyTimes="%s" keySplines="%s" values="%s"/>'
    for k in range(n):
        xs = ["%d" % (x + sh[k][0] * w) for sh in shapes]
        ys = ["%d" % (y + sh[k][1] * h) for sh in shapes]
        # Each shape holds, then flies to the next: s0 s0 s1 s1 s2 s2 s3 s3 s0
        vx = [xs[0], xs[0], xs[1], xs[1], xs[2], xs[2], xs[3], xs[3], xs[0]]
        vy = [ys[0], ys[0], ys[1], ys[1], ys[2], ys[2], ys[3], ys[3], ys[0]]
        out.append('<circle cx="%s" cy="%s" r="%.1f" fill="%s">%s%s</circle>' % (
            xs[0], ys[0], 1.2 + (k % 3) * .35, palette[k % len(palette)],
            anim % ("cx", cycle, kt, ks, ";".join(vx)), anim % ("cy", cycle, kt, ks, ";".join(vy))))
    out.append("</g>")
    return "".join(out)


def ring(cx, cy, r, pct, label, sub=None, color="url(#neon)", width=7, size=15):
    c = 2 * math.pi * r
    out = ['<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="%d"/>' % (cx, cy, r, LINE, width)]
    out.append(
        '<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="%d" stroke-linecap="round" '
        'stroke-dasharray="%.1f %.1f" transform="rotate(-90 %d %d)" filter="url(#softglow)">'
        '<animate attributeName="stroke-dasharray" from="0 %.1f" to="%.1f %.1f" dur="1.6s" fill="freeze"/></circle>'
        % (cx, cy, r, color, width, c * pct, c, cx, cy, c, c * pct, c))
    out.append('<text x="%d" y="%d" text-anchor="middle" font-size="%d" font-weight="800" fill="%s">%s</text>'
               % (cx, cy + size * .35, size, TEXT, e(label)))
    if sub:
        out.append('<text x="%d" y="%d" text-anchor="middle" font-size="10" fill="%s">%s</text>'
                   % (cx, cy + size * .35 + 14, MUTED, e(sub)))
    return "".join(out)


# ---------------------------------------------------------------- hero

def hero(total, current, longest, first_day, cur_range):
    W = 860
    b = ['<text x="24" y="36" font-size="17" font-weight="800" fill="%s">%s <tspan fill="%s">/</tspan> README<tspan fill="%s">.md</tspan></text>'
         % (TEXT, USER, MUTED, CYAN)]

    # System info (laid out first: its length sets the window height)
    x0, y = 368, 124
    info = ['<text x="%d" y="%d" font-size="17" font-weight="800" fill="%s" filter="url(#softglow)">SYSTEM.INFO</text>' % (x0, y, CYAN)]
    y += 12
    info.append('<rect x="%d" y="%d" width="160" height="23" rx="4" fill="%s"/>' % (x0, y, VIOLET))
    info.append('<text x="%d" y="%d" font-size="13.5" font-weight="800" fill="#fff">himanshu@github</text>' % (x0 + 10, y + 16))
    y += 46
    delay = .3
    for row in PROFILE:
        if row is None:
            y += 7
            continue
        if isinstance(row, str):
            info.append('<text class="reveal" style="animation-delay:%.2fs" x="%d" y="%d" font-size="14" font-weight="700" fill="%s">%s</text>'
                        % (delay, x0, y, TEXT, e(row)))
        else:
            k, v = row
            key = (k + " ").ljust(15, ".")
            kc = MINT if k.startswith(("Core", "Grid")) else CYAN
            info.append('<text class="reveal" style="animation-delay:%.2fs" x="%d" y="%d" font-size="14">'
                        '<tspan fill="%s" font-weight="700">%s</tspan><tspan fill="#3a3f66">%s</tspan>'
                        '<tspan fill="%s"> %s</tspan></text>'
                        % (delay, x0, y, kc, e(k), e(key[len(k):]), TEXT, e(v)))
        y += 19.5
        delay += .08
    info.append('<text x="%d" y="%d" font-size="14" fill="%s">▸ <tspan fill="%s">./more_about_me.sh</tspan><tspan class="cursor" fill="%s"> █</tspan></text>'
                % (x0, y + 6, PINK, MUTED, CYAN))
    bottom = int(y + 30)

    b.append(window(16, 56, W - 32, bottom - 56, "himanshugpt0005@gmail.com"))

    # Visual map: particle morph, centred in a tall framed box
    bx, by, bw = 36, 128, 312
    bh = bottom - 22 - by
    side = bw - 16
    my = by + (bh - side) // 2
    b.append('<text x="%d" y="%d" font-size="11" letter-spacing="2" fill="%s">VISUAL.MAP</text>' % (bx + 2, by - 10, MUTED))
    b.append('<rect x="%d" y="%d" width="%d" height="%d" rx="6" fill="#0b0e1f" stroke="#2b305a"/>' % (bx, by, bw, bh))
    b.append(brackets(bx, by, bw, bh))
    b.append('<text x="%d" y="%d" font-size="11" fill="%s">[ x:0.42  y:0.17 ]</text>' % (bx + 14, by + 26, FAINT))
    b.append('<text x="%d" y="%d" font-size="11" fill="%s"><tspan class="pulse" fill="%s">●</tspan> rendering himanshu.exe</text>'
             % (bx + 14, by + bh - 14, FAINT, PINK))
    b.append(morph(bx + 8, my, side, side))
    b.append('<rect class="scan" x="%d" y="%d" width="%d" height="3" fill="%s" opacity=".16"/>' % (bx + 1, by + 1, bw - 2, CYAN))
    b += info

    # Streak row
    top = bottom + 18
    c1, c2, c3 = W // 6, W // 2, W * 5 // 6
    b.append('<rect x="16" y="%d" width="%d" height="136" rx="14" fill="%s" stroke="%s"/>' % (top, W - 32, PANEL, LINE))
    for xx in (W // 3, W * 2 // 3):
        b.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-opacity=".5"/>' % (xx, top + 20, xx, top + 116, CYAN))
    b.append('<text x="%d" y="%d" text-anchor="middle" font-size="40" font-weight="800" fill="%s" filter="url(#softglow)">%s</text>' % (c1, top + 60, TEXT, "{:,}".format(total)))
    b.append('<text x="%d" y="%d" text-anchor="middle" font-size="15" fill="%s">Total Contributions</text>' % (c1, top + 88, CYAN))
    b.append('<text x="%d" y="%d" text-anchor="middle" font-size="12" fill="%s">%s - Present</text>' % (c1, top + 108, MUTED, e(first_day)))
    b.append(ring(c2, top + 48, 31, min(current / max(longest, 1), 1), str(current), size=22))
    b.append('<text x="%d" y="%d" text-anchor="middle" font-size="15" font-weight="700" fill="%s">Current Streak</text>' % (c2, top + 106, PINK))
    b.append('<text x="%d" y="%d" text-anchor="middle" font-size="12" fill="%s">%s</text>' % (c2, top + 124, MUTED, e(cur_range)))
    b.append('<text x="%d" y="%d" text-anchor="middle" font-size="40" font-weight="800" fill="%s" filter="url(#softglow)">%d</text>' % (c3, top + 60, TEXT, longest))
    b.append('<text x="%d" y="%d" text-anchor="middle" font-size="15" fill="%s">Longest Streak</text>' % (c3, top + 88, VIOLET))
    b.append('<text x="%d" y="%d" text-anchor="middle" font-size="12" fill="%s">days in a row</text>' % (c3, top + 108, MUTED))

    style = """
    @keyframes scan { from { transform: translateY(0); } to { transform: translateY(%dpx); } }
    .scan { animation: scan 3.2s linear infinite; }
    """ % (bh - 4)
    return svg(W, top + 152, "\n  ".join(b), style)


# ---------------------------------------------------------------- stats

def stats(base, days, totals, colors):
    W, H = 860, 320
    cc = base["contributionsCollection"]
    repos = base["repositories"]["nodes"]
    rows = [
        ("★", "Total Stars Earned", sum(r["stargazerCount"] for r in repos)),
        ("◆", "Total Commits (last year)", cc["totalCommitContributions"] + cc["restrictedContributionsCount"]),
        ("⇄", "Total PRs", cc["totalPullRequestContributions"]),
        ("!", "Total Issues", cc["totalIssueContributions"]),
        ("⌘", "Public Repos", base["repositories"]["totalCount"]),
        ("◎", "Contributed to (last year)", base["repositoriesContributedTo"]["totalCount"]),
    ]
    b = [window(16, 16, W - 32, H - 32, "~/stats --live")]
    b.append('<text x="40" y="98" font-size="17" font-weight="800" fill="%s" filter="url(#softglow)">Himanshu\'s GitHub Stats</text>' % PINK)
    for i, (icon, label, val) in enumerate(rows):
        y = 132 + i * 28
        b.append('<text class="reveal" style="animation-delay:%.2fs" x="40" y="%d" font-size="14.5"><tspan fill="%s">%s</tspan>'
                 '<tspan fill="%s" dx="8">%s:</tspan></text>' % (.2 + i * .1, y, CYAN, icon, TEXT, e(label)))
        b.append('<text class="reveal" style="animation-delay:%.2fs" x="404" y="%d" text-anchor="end" font-size="15" font-weight="800" fill="%s">%s</text>'
                 % (.2 + i * .1, y, MINT, "{:,}".format(val)))

    # Languages
    lx, bw = 452, 372
    b.append('<line x1="428" y1="76" x2="428" y2="286" stroke="%s"/>' % LINE)
    b.append('<text x="%d" y="98" font-size="17" font-weight="800" fill="%s" filter="url(#softglow)">Most Used Languages</text>' % (lx, CYAN))
    whole = float(sum(totals.values())) or 1
    top = [kv for kv in sorted(totals.items(), key=lambda kv: -kv[1]) if kv[1] / whole >= .005][:8]
    whole = float(sum(v for _, v in top)) or 1
    x = lx
    b.append('<clipPath id="bar"><rect x="%d" y="118" width="%d" height="12" rx="6"/></clipPath><g clip-path="url(#bar)">' % (lx, bw))
    for name, v in top:
        w = bw * v / whole
        b.append('<rect x="%.1f" y="118" width="%.1f" height="12" fill="%s"/>' % (x, w + .5, colors[name]))
        x += w
    b.append("</g>")
    for i, (name, v) in enumerate(top):
        cx, cy = lx + (i % 2) * 190, 162 + (i // 2) * 28
        b.append('<circle cx="%d" cy="%d" r="6" fill="%s"/><text x="%d" y="%d" font-size="14" fill="%s">%s <tspan fill="%s">%.1f%%</tspan></text>'
                 % (cx + 6, cy - 5, colors[name], cx + 20, cy, TEXT, e(name), MUTED, 100 * v / whole))

    return svg(W, H, "\n  ".join(b))


# ---------------------------------------------------------------- projects

def projects(repo_map):
    W, cw, ch, gap = 860, 404, 206, 20
    rows = math.ceil(len(PROJECTS) / 2)
    H = 68 + rows * (ch + gap) + 4
    b = ['<text x="22" y="42" font-size="17" font-weight="700"><tspan fill="%s">himanshu@github</tspan><tspan fill="%s">:~$ </tspan>'
         '<tspan fill="%s">./projects.sh --all</tspan><tspan class="cursor" fill="%s"> █</tspan></text>' % (MINT, MUTED, TEXT, CYAN)]
    for idx, (repo, title, desc, tags) in enumerate(PROJECTS):
        r = repo_map.get(repo, {})
        x = 16 + (idx % 2) * (cw + gap)
        y = 68 + (idx // 2) * (ch + gap)
        g = ['<g class="reveal" style="animation-delay:%.2fs">' % (.15 * idx)]
        g.append('<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="%s" stroke="%s" stroke-opacity=".4"/>' % (x, y, cw, ch, PANEL, VIOLET))
        g.append('<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="none" stroke="url(#sheen)" stroke-opacity=".8"/>' % (x, y, cw, ch))
        g.append('<text x="%d" y="%d" font-size="12" fill="%s">%s/%s</text>' % (x + 18, y + 26, MUTED, USER, e(repo.lower())))
        g.append('<circle cx="%d" cy="%d" r="4.5" fill="%s" opacity=".85"/>' % (x + cw - 20, y + 22, MINT))
        g.append('<text x="%d" y="%d" font-size="22" font-weight="800" fill="%s">%s<tspan fill="%s">_</tspan></text>' % (x + 18, y + 58, TEXT, e(title), CYAN))
        for i, line in enumerate(desc):
            g.append('<text x="%d" y="%d" font-size="13" fill="%s">%s</text>' % (x + 18, y + 84 + i * 18, "#b3b8d9", e(line)))
        tx = x + 18
        for t in tags:
            tw = 7.6 * len(t) + 20
            g.append('<rect x="%d" y="%d" width="%.0f" height="24" rx="12" fill="#1f2147" stroke="%s" stroke-opacity=".6"/>' % (tx, y + 122, tw, VIOLET))
            g.append('<text x="%.0f" y="%d" text-anchor="middle" font-size="12" fill="#d9d3fb">%s</text>' % (tx + tw / 2, y + 138, e(t)))
            tx += tw + 8
        meta = "★ %d · updated %s" % (r.get("stargazerCount", 0), ago(r["pushedAt"]) if r.get("pushedAt") else "-")
        g.append('<text x="%d" y="%d" font-size="12" fill="%s">%s</text>' % (x + 18, y + 186, MUTED, e(meta)))

        langs = [(ed["node"]["name"], ed["size"], soften(ed["node"]["color"] or MUTED)) for ed in r.get("languages", {}).get("edges", [])]
        whole = float(sum(s for _, s, _ in langs)) or 1
        cx, cy, rad = x + cw - 48, y + 166, 24
        if langs:
            circ, off = 2 * math.pi * rad, 0
            g.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="7"/>' % (cx, cy, rad, LINE))
            for name, s, col in langs[:4]:
                seg = circ * s / whole
                g.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="7" stroke-dasharray="%.1f %.1f" '
                         'stroke-dashoffset="%.1f" transform="rotate(-90 %d %d)"/>' % (cx, cy, rad, col, seg, circ, -off, cx, cy))
                off += seg
            g.append('<text x="%d" y="%d" text-anchor="middle" font-size="12" font-weight="800" fill="%s">%d%%</text>'
                     % (cx, cy + 4, TEXT, round(100 * langs[0][1] / whole)))
            shown = [l for l in langs if round(100 * l[1] / whole) >= 1][:3]
            for i, (name, s, col) in enumerate(shown):
                ly = y + 160 + i * 16
                g.append('<circle cx="%d" cy="%d" r="4" fill="%s"/><text x="%d" y="%d" font-size="11.5" fill="%s">%s %d%%</text>'
                         % (x + cw - 196, ly, col, x + cw - 187, ly + 4, "#c4c9e8", e(name), round(100 * s / whole)))
        g.append("</g>")
        b.append("".join(g))
    return svg(W, H, "\n  ".join(b))


# ---------------------------------------------------------------- main

def main():
    ASSETS.mkdir(exist_ok=True)
    base, days = fetch()
    repos = base["repositories"]["nodes"]
    totals, colors = lang_totals(repos)
    current, longest = streaks(days)

    active = sorted(k for k, v in days.items() if v > 0)
    first = dt.date.fromisoformat(active[0]) if active else dt.date.today()
    if current:
        end = dt.date.fromisoformat(active[-1])
        cur_range = "%s - %s" % ((end - dt.timedelta(current - 1)).strftime("%b %-d"), end.strftime("%b %-d"))
    else:
        cur_range = "start one today"

    (ASSETS / "hero.svg").write_text(hero(sum(days.values()), current, longest, first.strftime("%b %-d, %Y"), cur_range))
    (ASSETS / "stats.svg").write_text(stats(base, days, totals, colors))

    repo_map = {r["name"]: r for r in repos}
    (ASSETS / "projects.svg").write_text(projects(repo_map))
    print("total=%d current=%d longest=%d" % (sum(days.values()), current, longest))


if __name__ == "__main__":
    main()
