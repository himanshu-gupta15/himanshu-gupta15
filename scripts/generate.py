"""Render the neon terminal-style SVGs used by the profile README.

Pulls live data from the GitHub GraphQL API and writes:
  assets/hero.svg      window with dotted portrait + SYSTEM.INFO + streak row
  assets/stats.svg     GitHub stats, top languages, contribution grid
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
BG = "#05051a"
PANEL = "#0a0a2e"
CYAN = "#22d3ee"
PINK = "#f472b6"
VIOLET = "#a855f7"
MINT = "#4ade80"
TEXT = "#e2e8f0"
MUTED = "#7c83b0"

PROFILE = [
    ("Subject", "Himanshu Gupta"),
    ("Role", "AI Full Stack Developer Intern @ The AI Signal"),
    ("Origin", "Mau, Uttar Pradesh, India"),
    ("Education", "B.Tech CSE @ IIIT Sonepat"),
    ("Status", "Building multi-agent AI systems"),
    ("ToolChain", "VS Code · Git · Docker · Postman"),
    None,
    ("Core.Lang", "C++, TypeScript, JavaScript, Python, Java"),
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
            colors[name] = e["node"]["color"] or MUTED
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
      <feGaussianBlur stdDeviation="4" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <filter id="softglow" x="-50%%" y="-50%%" width="200%%" height="200%%">
      <feGaussianBlur stdDeviation="1.6" result="b"/>
      <feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
    </filter>
    <pattern id="grid" width="28" height="28" patternUnits="userSpaceOnUse">
      <path d="M28 0H0V28" fill="none" stroke="#1b1b4a" stroke-width=".6"/>
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
  <rect width="100%%" height="100%%" rx="16" fill="url(#grid)" opacity=".55"/>
%s
</svg>
""" % (w, h, w, h, e(FONT), FONT, style, defs(), BG, body)


def window(x, y, w, h, title_right=""):
    return """
  <rect x="%d" y="%d" width="%d" height="%d" rx="14" fill="%s" stroke="%s" stroke-width="2" filter="url(#glow)" opacity=".95"/>
  <rect x="%d" y="%d" width="%d" height="%d" rx="14" fill="%s" stroke="%s" stroke-opacity=".9" stroke-width="1.4"/>
  <circle cx="%d" cy="%d" r="6" fill="#ff5f57"/><circle cx="%d" cy="%d" r="6" fill="#febc2e"/><circle cx="%d" cy="%d" r="6" fill="#28c840"/>
  <line x1="%d" y1="%d" x2="%d" y2="%d" stroke="#23235a"/>
  <text x="%d" y="%d" text-anchor="end" font-size="12" fill="%s" font-weight="700">%s</text>""" % (
        x, y, w, h, PANEL, CYAN,
        x, y, w, h, PANEL, CYAN,
        x + 24, y + 22, x + 44, y + 22, x + 64, y + 22,
        x, y + 44, x + w, y + 44,
        x + w - 22, y + 26, TEXT, e(title_right))


def brackets(x, y, w, h, n=14, color=CYAN):
    p = "M{0} {1}v-{n}h{n} M{2} {1}v-{n}h-{n} M{0} {3}v{n}h{n} M{2} {3}v{n}h-{n}"
    d = p.format(x, y + n, x + w, y + h - n, n=n)
    return '<path d="%s" fill="none" stroke="%s" stroke-width="2"/>' % (d, color)


def lerp_color(a, b, t):
    a, b = [int(a[i:i + 2], 16) for i in (1, 3, 5)], [int(b[i:i + 2], 16) for i in (1, 3, 5)]
    return "#%02x%02x%02x" % tuple(round(x + (y - x) * t) for x, y in zip(a, b))


def portrait(x, y, w, h):
    """Dot-matrix rendering of the avatar: dot size follows brightness."""
    img = Image.open(PORTRAIT).convert("L")
    side = min(img.size)
    img = ImageOps.fit(img, (side, side), centering=(0.5, 0.0))
    img = ImageOps.autocontrast(img, cutoff=2)
    cols = 58
    step = w / cols
    rows = int(h / step)
    small = img.resize((cols, rows), Image.LANCZOS)
    dots = []
    for j in range(rows):
        t = j / max(rows - 1, 1)
        color = lerp_color(PINK, VIOLET, t * 1.6) if t < .6 else lerp_color(VIOLET, CYAN, (t - .6) / .4)
        for i in range(cols):
            v = small.getpixel((i, j)) / 255
            if v < .16:
                continue
            r = step * .5 * (v ** .8)
            cls = ' class="tw"' if (i * 7 + j * 13) % 23 == 0 else ""
            dots.append('<circle cx="%.1f" cy="%.1f" r="%.2f" fill="%s"%s/>' % (
                x + i * step + step / 2, y + j * step + step / 2, r, color, cls))
    return '<g filter="url(#softglow)">%s</g>' % "".join(dots)


def ring(cx, cy, r, pct, label, sub=None, color="url(#neon)", width=7, size=15):
    c = 2 * math.pi * r
    out = ['<circle cx="%d" cy="%d" r="%d" fill="none" stroke="#23235a" stroke-width="%d"/>' % (cx, cy, r, width)]
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
    W, H = 1000, 670
    b = ['<text x="34" y="36" font-size="15" font-weight="800" fill="%s">%s <tspan fill="%s">/</tspan> README<tspan fill="%s">.md</tspan></text>'
         % (TEXT, USER, MUTED, CYAN)]
    b.append(window(24, 56, 952, 456, "himanshugpt0005@gmail.com"))

    # Visual map
    b.append('<text x="56" y="126" font-size="10" letter-spacing="2" fill="%s">VISUAL.MAP</text>' % MUTED)
    b.append('<rect x="52" y="136" width="352" height="356" rx="6" fill="#060622" stroke="#2a2a6a"/>')
    b.append(brackets(52, 136, 352, 356))
    b.append(portrait(62, 160, 332, 326))
    b.append('<rect class="scan" x="53" y="137" width="350" height="3" fill="%s" opacity=".35"/>' % CYAN)

    # System info
    x0, y = 432, 124
    b.append('<text x="%d" y="%d" font-size="15" font-weight="800" fill="%s" filter="url(#softglow)">SYSTEM.INFO</text>' % (x0, y, CYAN))
    y += 12
    b.append('<rect x="%d" y="%d" width="150" height="20" rx="4" fill="%s"/>' % (x0, y, VIOLET))
    b.append('<text x="%d" y="%d" font-size="12" font-weight="800" fill="#fff">himanshu@github</text>' % (x0 + 10, y + 14))
    y += 38
    delay = .3
    for row in PROFILE:
        if row is None:
            y += 6
            continue
        if isinstance(row, str):
            b.append('<text class="reveal" style="animation-delay:%.2fs" x="%d" y="%d" font-size="12.5" font-weight="700" fill="%s">%s</text>'
                     % (delay, x0, y, TEXT, e(row)))
        else:
            k, v = row
            key = (k + " ").ljust(16, ".")
            kc = MINT if k.startswith(("Core", "Grid")) else CYAN
            b.append('<text class="reveal" style="animation-delay:%.2fs" x="%d" y="%d" font-size="12.5">'
                     '<tspan fill="%s" font-weight="700">%s</tspan><tspan fill="#3b3f74">%s</tspan>'
                     '<tspan fill="%s"> %s</tspan></text>'
                     % (delay, x0, y, kc, e(k), e(key[len(k):]), TEXT, e(v)))
        y += 16.5
        delay += .08
    b.append('<text x="%d" y="%d" font-size="12.5" fill="%s">▸ <tspan fill="%s">./more_about_me.sh</tspan><tspan class="cursor" fill="%s"> █</tspan></text>'
             % (x0, y + 4, PINK, MUTED, CYAN))

    # Streak row
    top = 532
    b.append('<rect x="24" y="%d" width="952" height="118" rx="14" fill="%s" stroke="#23235a"/>' % (top, PANEL))
    for xx in (341, 659):
        b.append('<line x1="%d" y1="%d" x2="%d" y2="%d" stroke="%s" stroke-opacity=".5"/>' % (xx, top + 18, xx, top + 100, CYAN))
    b.append('<text x="182" y="%d" text-anchor="middle" font-size="34" font-weight="800" fill="%s" filter="url(#softglow)">%s</text>' % (top + 54, TEXT, "{:,}".format(total)))
    b.append('<text x="182" y="%d" text-anchor="middle" font-size="13" fill="%s">Total Contributions</text>' % (top + 78, CYAN))
    b.append('<text x="182" y="%d" text-anchor="middle" font-size="10" fill="%s">%s - Present</text>' % (top + 96, MUTED, e(first_day)))
    b.append(ring(500, top + 44, 28, min(current / max(longest, 1), 1), str(current), size=20))
    b.append('<text x="500" y="%d" text-anchor="middle" font-size="13" font-weight="700" fill="%s">Current Streak</text>' % (top + 96, PINK))
    b.append('<text x="500" y="%d" text-anchor="middle" font-size="10" fill="%s">%s</text>' % (top + 111, MUTED, e(cur_range)))
    b.append('<text x="818" y="%d" text-anchor="middle" font-size="34" font-weight="800" fill="%s" filter="url(#softglow)">%d</text>' % (top + 54, TEXT, longest))
    b.append('<text x="818" y="%d" text-anchor="middle" font-size="13" fill="%s">Longest Streak</text>' % (top + 78, VIOLET))
    b.append('<text x="818" y="%d" text-anchor="middle" font-size="10" fill="%s">days in a row</text>' % (top + 96, MUTED))

    style = """
    @keyframes scan { from { transform: translateY(0); } to { transform: translateY(352px); } }
    .scan { animation: scan 3.2s linear infinite; }
    @keyframes twinkle { 0%, 100% { opacity: 1; } 50% { opacity: .15; } }
    .tw { animation: twinkle 2.2s ease-in-out infinite; }
    """
    return svg(W, H, "\n  ".join(b), style)


# ---------------------------------------------------------------- stats

def stats(base, days, totals, colors):
    W, H = 1000, 470
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
    b = [window(24, 20, 952, 430, "~/stats --live")]
    b.append('<text x="56" y="96" font-size="15" font-weight="800" fill="%s" filter="url(#softglow)">Himanshu\'s GitHub Stats</text>' % PINK)
    for i, (icon, label, val) in enumerate(rows):
        y = 126 + i * 23
        b.append('<text class="reveal" style="animation-delay:%.2fs" x="56" y="%d" font-size="13"><tspan fill="%s">%s</tspan>'
                 '<tspan fill="%s" dx="8">%s:</tspan></text>' % (.2 + i * .1, y, CYAN, icon, TEXT, e(label)))
        b.append('<text class="reveal" style="animation-delay:%.2fs" x="400" y="%d" text-anchor="end" font-size="13" font-weight="800" fill="%s">%s</text>'
                 % (.2 + i * .1, y, MINT, "{:,}".format(val)))

    # Languages
    b.append('<line x1="440" y1="76" x2="440" y2="250" stroke="#23235a"/>')
    b.append('<text x="476" y="96" font-size="15" font-weight="800" fill="%s" filter="url(#softglow)">Most Used Languages</text>' % CYAN)
    whole = float(sum(totals.values())) or 1
    top = [kv for kv in sorted(totals.items(), key=lambda kv: -kv[1]) if kv[1] / whole >= .005][:8]
    whole = float(sum(v for _, v in top)) or 1
    x, bw = 476, 468
    b.append('<clipPath id="bar"><rect x="476" y="114" width="%d" height="10" rx="5"/></clipPath><g clip-path="url(#bar)">' % bw)
    for name, v in top:
        w = bw * v / whole
        b.append('<rect x="%.1f" y="114" width="%.1f" height="10" fill="%s"/>' % (x, w + .5, colors[name]))
        x += w
    b.append("</g>")
    for i, (name, v) in enumerate(top):
        cx, cy = 476 + (i % 2) * 240, 150 + (i // 2) * 24
        b.append('<circle cx="%d" cy="%d" r="5" fill="%s"/><text x="%d" y="%d" font-size="12.5" fill="%s">%s <tspan fill="%s">%.1f%%</tspan></text>'
                 % (cx + 5, cy - 4, colors[name], cx + 18, cy, TEXT, e(name), MUTED, 100 * v / whole))

    # Contribution grid, last 53 weeks
    today = dt.date.today()
    start = today - dt.timedelta(days=today.weekday() + 1 + 52 * 7)  # a Sunday
    peak = max([days.get((start + dt.timedelta(d)).isoformat(), 0) for d in range((today - start).days + 1)] + [1])
    palette = ["#16163d", "#3b1d6e", "#6d28d9", "#a855f7", "#f0abfc"]
    cell, gap, gx, gy = 13, 3.4, 56, 292
    b.append('<text x="56" y="%d" font-size="11" letter-spacing="2" fill="%s">CONTRIBUTION.GRID // last 12 months</text>' % (gy - 10, MUTED))
    d, n = start, 0
    while d <= today:
        week, dow = (d - start).days // 7, (d.weekday() + 1) % 7
        c = days.get(d.isoformat(), 0)
        lvl = 0 if c == 0 else min(4, 1 + int(3 * c / peak))
        cls = ' class="pulse" style="animation-delay:%.1fs"' % ((week * 7 + dow) % 17 * .15) if lvl >= 3 else ""
        b.append('<rect x="%.1f" y="%.1f" width="%d" height="%d" rx="3" fill="%s"%s/>'
                 % (gx + week * (cell + gap), gy + dow * (cell + gap), cell, cell, palette[lvl], cls))
        d += dt.timedelta(1)
        n += 1
    lx = gx + 53 * (cell + gap) - 5 * (cell + gap) - 70
    b.append('<text x="%d" y="%d" font-size="10" fill="%s">less</text>' % (lx, gy + 7 * (cell + gap) + 14, MUTED))
    for i, col in enumerate(palette):
        b.append('<rect x="%d" y="%d" width="11" height="11" rx="2" fill="%s"/>' % (lx + 32 + i * 15, gy + 7 * (cell + gap) + 4, col))
    b.append('<text x="%d" y="%d" font-size="10" fill="%s">more</text>' % (lx + 32 + 5 * 15 + 4, gy + 7 * (cell + gap) + 14, MUTED))
    return svg(W, H, "\n  ".join(b))


# ---------------------------------------------------------------- projects

def projects(repo_map):
    W, cw, ch, gap = 1000, 466, 168, 20
    rows = math.ceil(len(PROJECTS) / 2)
    H = 70 + rows * (ch + gap) + 10
    b = ['<text x="30" y="42" font-size="15" font-weight="700"><tspan fill="%s">himanshu@github</tspan><tspan fill="%s">:~$ </tspan>'
         '<tspan fill="%s">./projects.sh --all</tspan><tspan class="cursor" fill="%s"> █</tspan></text>' % (MINT, MUTED, TEXT, CYAN)]
    for idx, (repo, title, desc, tags) in enumerate(PROJECTS):
        r = repo_map.get(repo, {})
        x = 24 + (idx % 2) * (cw + gap)
        y = 66 + (idx // 2) * (ch + gap)
        delay = .15 * idx
        g = ['<g class="reveal" style="animation-delay:%.2fs">' % delay]
        g.append('<rect x="%d" y="%d" width="%d" height="%d" rx="12" fill="%s" stroke="%s" stroke-opacity=".55"/>' % (x, y, cw, ch, PANEL, VIOLET))
        g.append('<text x="%d" y="%d" font-size="10.5" fill="%s">%s/%s</text>' % (x + 18, y + 24, MUTED, USER, e(repo.lower())))
        g.append('<circle class="pulse" cx="%d" cy="%d" r="4.5" fill="%s" filter="url(#softglow)"/>' % (x + cw - 20, y + 20, MINT))
        g.append('<text x="%d" y="%d" font-size="19" font-weight="800" fill="%s">%s<tspan fill="%s" class="cursor">_</tspan></text>' % (x + 18, y + 52, TEXT, e(title), CYAN))
        for i, line in enumerate(desc):
            g.append('<text x="%d" y="%d" font-size="11" fill="%s">%s</text>' % (x + 18, y + 74 + i * 15, "#a5abd6", e(line)))
        tx = x + 18
        for t in tags:
            tw = 7.2 * len(t) + 18
            g.append('<rect x="%d" y="%d" width="%.0f" height="20" rx="10" fill="#2a1250" stroke="%s"/>' % (tx, y + 110, tw, VIOLET))
            g.append('<text x="%.0f" y="%d" text-anchor="middle" font-size="10.5" fill="#e9d5ff">%s</text>' % (tx + tw / 2, y + 124, e(t)))
            tx += tw + 7
        meta = "★ %d · updated %s" % (r.get("stargazerCount", 0), ago(r["pushedAt"]) if r.get("pushedAt") else "-")
        g.append('<text x="%d" y="%d" font-size="10.5" fill="%s">%s</text>' % (x + 18, y + 152, MUTED, e(meta)))

        langs = [(ed["node"]["name"], ed["size"], ed["node"]["color"] or MUTED) for ed in r.get("languages", {}).get("edges", [])]
        whole = float(sum(s for _, s, _ in langs)) or 1
        cx, cy, rad = x + cw - 64, y + 66, 28
        if langs:
            circ, off = 2 * math.pi * rad, 0
            g.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="#23235a" stroke-width="7"/>' % (cx, cy, rad))
            for name, s, col in langs[:4]:
                seg = circ * s / whole
                g.append('<circle cx="%d" cy="%d" r="%d" fill="none" stroke="%s" stroke-width="7" stroke-dasharray="%.1f %.1f" '
                         'stroke-dashoffset="%.1f" transform="rotate(-90 %d %d)"/>' % (cx, cy, rad, col, seg, circ, -off, cx, cy))
                off += seg
            g.append('<text x="%d" y="%d" text-anchor="middle" font-size="12" font-weight="800" fill="%s">%d%%</text>'
                     % (cx, cy + 4, TEXT, round(100 * langs[0][1] / whole)))
            shown = [l for l in langs if round(100 * l[1] / whole) >= 1][:3]
            for i, (name, s, col) in enumerate(shown):
                ly = y + 112 + i * 14
                g.append('<circle cx="%d" cy="%d" r="3.5" fill="%s"/><text x="%d" y="%d" font-size="10" fill="%s">%s %d%%</text>'
                         % (x + cw - 118, ly, col, x + cw - 110, ly + 4, "#c4c9ee", e(name), round(100 * s / whole)))
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
