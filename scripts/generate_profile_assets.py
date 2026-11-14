#!/usr/bin/env python3
"""Builds assets/trophies.svg and assets/activity-graph.svg from GitHub's GraphQL API.

Why this exists: the public trophy / activity-graph hosts are often down or
rate-limited, which shows up as broken images in a README. These two files are
generated inside your own repo by a GitHub Action, so they always load.

Env vars:
  GH_USER   GitHub username (default: Lakshay1221-apple)
  GH_TOKEN  token for the API (the Action passes secrets.GITHUB_TOKEN)
  OUT_DIR   output folder (default: assets)
  MOCK=1    use fake data (for local layout testing only)
"""
import datetime as dt
import json
import math
import os
import random
import urllib.request
from html import escape

USER = os.environ.get("GH_USER", "Lakshay1221-apple")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT = os.environ.get("OUT_DIR", "assets")

FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
BG, BORDER, TITLE, MUTED = "#1a1b27", "#2f3549", "#70a5fd", "#a9b1d6"
LINE = "#4d6bff"

RANKS = ["C", "B", "A", "AA", "AAA", "S", "SS", "SSS"]
RANK_COLORS = ["#8a94a6", "#6ea8ff", "#3ddc97", "#2ec4b6", "#ffd166", "#ffb347", "#ff9f43", "#ff6b6b"]
UNRANKED = "#4a5068"


# --------------------------------------------------------------------------- data
def gql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        data=json.dumps({"query": query, "variables": variables}).encode(),
        headers={
            "Authorization": f"bearer {TOKEN}",
            "Content-Type": "application/json",
            "User-Agent": "profile-assets-script",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.load(resp)
    if payload.get("errors"):
        raise SystemExit(f"GitHub API error: {payload['errors']}")
    return payload["data"]


def fetch():
    now = dt.datetime.now(dt.timezone.utc)
    head = gql("query($l:String!){user(login:$l){createdAt}}", {"l": USER})["user"]
    created = dt.datetime.fromisoformat(head["createdAt"].replace("Z", "+00:00"))

    # commits per calendar year (the API allows at most one year per range)
    year_fields = []
    for y in range(created.year, now.year + 1):
        end = now.strftime("%Y-%m-%dT%H:%M:%SZ") if y == now.year else f"{y}-12-31T23:59:59Z"
        year_fields.append(
            f'y{y}: contributionsCollection(from: "{y}-01-01T00:00:00Z", to: "{end}") '
            f"{{ totalCommitContributions }}"
        )
    query = """
    query($l: String!) { user(login: $l) {
        followers { totalCount }
        pullRequests { totalCount }
        issues { totalCount }
        repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC) { totalCount }
        contributionsCollection {
            contributionCalendar {
                totalContributions
                weeks { contributionDays { date contributionCount } }
            }
        }
        %s
    } }""" % "\n".join(year_fields)
    u = gql(query, {"l": USER})["user"]

    commits = sum(v["totalCommitContributions"] for k, v in u.items() if k[0] == "y" and k[1:].isdigit())

    stars, cursor = 0, None
    while True:
        repos = gql(
            """query($l:String!,$after:String){user(login:$l){
                 repositories(ownerAffiliations: OWNER, isFork: false, privacy: PUBLIC, first: 100, after: $after){
                   nodes{stargazerCount} pageInfo{hasNextPage endCursor}}}}""",
            {"l": USER, "after": cursor},
        )["user"]["repositories"]
        stars += sum(n["stargazerCount"] for n in repos["nodes"])
        if not repos["pageInfo"]["hasNextPage"]:
            break
        cursor = repos["pageInfo"]["endCursor"]

    today = now.strftime("%Y-%m-%d")
    days = [
        (d["date"], d["contributionCount"])
        for w in u["contributionsCollection"]["contributionCalendar"]["weeks"]
        for d in w["contributionDays"]
        if d["date"] <= today
    ]
    return {
        "joined": created.year,
        "followers": u["followers"]["totalCount"],
        "prs": u["pullRequests"]["totalCount"],
        "issues": u["issues"]["totalCount"],
        "repos": u["repositories"]["totalCount"],
        "stars": stars,
        "commits": commits,
        "contributions": u["contributionsCollection"]["contributionCalendar"]["totalContributions"],
        "days": days,
    }


def mock():
    rnd = random.Random(7)
    start = dt.date.today() - dt.timedelta(days=40)
    days = [((start + dt.timedelta(days=i)).isoformat(), max(0, int(rnd.gauss(6, 6)))) for i in range(41)]
    return {"joined": 2025, "followers": 12, "prs": 10, "issues": 0, "repos": 43,
            "stars": 95, "commits": 777, "contributions": 900, "days": days}


# --------------------------------------------------------------------------- trophies
def rank_of(value, thresholds):
    idx = sum(1 for t in thresholds if value >= t) - 1
    if idx < 0:
        return -1, 0.0
    if idx >= len(thresholds) - 1:
        return idx, 1.0
    lo, hi = thresholds[idx], thresholds[idx + 1]
    return idx, max(0.0, min(1.0, (value - lo) / (hi - lo)))


def cup(color):
    return (
        f'<path d="M-14 0 H14 V12 C14 24 8 30 0 30 C-8 30 -14 24 -14 12 Z" fill="{color}"/>'
        f'<path d="M-14 4 H-20 C-23 4 -22 15 -13 17" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
        f'<path d="M14 4 H20 C23 4 22 15 13 17" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
        f'<rect x="-3" y="30" width="6" height="8" fill="{color}"/>'
        f'<rect x="-10" y="38" width="20" height="5" rx="2" fill="{color}"/>'
        '<path d="M-9 4 V12 C-9 17 -7 20 -5 22" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="2" stroke-linecap="round"/>'
    )


def trophies_svg(d):
    age = dt.datetime.now(dt.timezone.utc).year - d["joined"]
    items = [
        (f"Joined{d['joined']}", age, f"{age} yr" + ("" if age == 1 else "s"), [0, 1, 2, 3, 5, 7, 10, 15]),
        ("Followers", d["followers"], f"{d['followers']} followers", [1, 5, 10, 25, 50, 100, 250, 500]),
        ("Contributions", d["contributions"], f"{d['contributions']} this year", [10, 100, 300, 600, 1000, 2000, 4000, 8000]),
        ("Commits", d["commits"], f"{d['commits']} commits", [10, 100, 300, 600, 1000, 2000, 4000, 8000]),
        ("Public Repositories", d["repos"], f"{d['repos']} public repos", [1, 5, 10, 20, 35, 50, 75, 100]),
        ("Stars", d["stars"], f"{d['stars']} stars", [1, 5, 10, 30, 75, 150, 400, 1000]),
        ("Issues", d["issues"], f"{d['issues']} issues", [1, 5, 10, 25, 50, 100, 250, 500]),
        ("PullRequest", d["prs"], f"{d['prs']} PRs", [1, 5, 10, 25, 50, 100, 250, 500]),
    ]
    cw, ch, gap = 104, 150, 8
    width = len(items) * cw + (len(items) - 1) * gap
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{ch}" viewBox="0 0 {width} {ch}" role="img" '
        f'aria-label="GitHub trophies for {escape(USER)}"><title>GitHub trophies for {escape(USER)}</title>'
    ]
    for i, (title, value, label, th) in enumerate(items):
        idx, pct = rank_of(value, th)
        color = RANK_COLORS[idx] if idx >= 0 else UNRANKED
        rank = RANKS[idx] if idx >= 0 else "-"
        x = i * (cw + gap)
        out.append(
            f'<g transform="translate({x} 0)">'
            f'<rect x=".5" y=".5" width="{cw - 1}" height="{ch - 1}" rx="8" fill="{BG}" stroke="{BORDER}"/>'
            f'<text x="{cw / 2}" y="22" text-anchor="middle" font-family="{FONT}" font-size="12" font-weight="700" fill="{TITLE}">{escape(title)}</text>'
            f'<g transform="translate({cw / 2} 34)">{cup(color)}</g>'
            f'<text x="{cw / 2}" y="106" text-anchor="middle" font-family="{FONT}" font-size="16" font-weight="700" fill="{color}">{rank}</text>'
            f'<text x="{cw / 2}" y="124" text-anchor="middle" font-family="{FONT}" font-size="10" fill="{MUTED}">{escape(label)}</text>'
            f'<rect x="12" y="134" width="80" height="4" rx="2" fill="{BORDER}"/>'
            f'<rect x="12" y="134" width="{80 * pct:.1f}" height="4" rx="2" fill="{color}"/>'
            "</g>"
        )
    out.append("</svg>")
    return "".join(out)


# --------------------------------------------------------------------------- activity graph
def nice_step(raw):
    for s in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000):
        if s >= raw:
            return s
    return int(math.ceil(raw))


def activity_svg(days):
    pts = days[-31:]
    W, H = 780, 300
    L, R, T, B = 60, 24, 60, 52
    pw, ph = W - L - R, H - T - B
    peak = max([v for _, v in pts] + [1])
    step = nice_step(peak / 5)
    top = step * math.ceil(peak / step)
    n = len(pts)
    xs = [L + (pw * i / (n - 1) if n > 1 else pw / 2) for i in range(n)]
    ys = [T + ph - (v / top) * ph for _, v in pts]
    base = T + ph

    o = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="{escape(USER)} GitHub activity graph, last 31 days"><title>{escape(USER)}\'s GitHub Activity Graph</title>',
        '<defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{LINE}" stop-opacity=".40"/><stop offset="1" stop-color="{LINE}" stop-opacity="0"/>'
        "</linearGradient></defs>",
        f'<rect x=".5" y=".5" width="{W - 1}" height="{H - 1}" rx="10" fill="{BG}" stroke="{BORDER}"/>',
        f'<text x="{W / 2}" y="32" text-anchor="middle" font-family="{FONT}" font-size="16" font-weight="700" fill="{TITLE}">'
        f"{escape(USER)}'s GitHub Activity Graph</text>",
    ]
    for val in range(0, top + 1, step):
        y = base - val / top * ph
        o.append(f'<line x1="{L}" y1="{y:.1f}" x2="{W - R}" y2="{y:.1f}" stroke="{BORDER}" stroke-dasharray="3 4"/>')
        o.append(f'<text x="{L - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="{FONT}" font-size="10" fill="{MUTED}">{val}</text>')

    line = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
    area = f"M{xs[0]:.1f},{base} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in zip(xs, ys)) + f" L{xs[-1]:.1f},{base} Z"
    o.append(f'<path d="{area}" fill="url(#fill)"/>')
    o.append(f'<polyline points="{line}" fill="none" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>')
    for (date, v), x, y in zip(pts, xs, ys):
        o.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{LINE}"><title>{date}: {v} contributions</title></circle>')
        o.append(f'<text x="{x:.1f}" y="{base + 18}" text-anchor="middle" font-family="{FONT}" font-size="10" fill="{MUTED}">{int(date[8:10])}</text>')

    o.append(f'<text x="{L + pw / 2}" y="{H - 12}" text-anchor="middle" font-family="{FONT}" font-size="11" fill="{MUTED}">Days</text>')
    o.append(
        f'<text transform="rotate(-90)" x="{-(T + ph / 2):.1f}" y="18" text-anchor="middle" font-family="{FONT}" '
        f'font-size="11" fill="{MUTED}">Contributions</text>'
    )
    o.append("</svg>")
    return "".join(o)


# --------------------------------------------------------------------------- main
def main():
    data = mock() if os.environ.get("MOCK") == "1" else fetch()
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "trophies.svg"), "w", encoding="utf-8") as f:
        f.write(trophies_svg(data))
    with open(os.path.join(OUT, "activity-graph.svg"), "w", encoding="utf-8") as f:
        f.write(activity_svg(data["days"]))
    print(f"wrote {OUT}/trophies.svg and {OUT}/activity-graph.svg for {USER}")


if __name__ == "__main__":
    main()
