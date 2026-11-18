
#!/usr/bin/env python3
"""Generate public-only GitHub profile trophies and activity SVGs.

Only public profile data is requested. Private repository metadata and private
contributions are excluded at query time, not filtered after retrieval.

Environment:
  GH_USER   GitHub username (defaults to the profile repository owner)
  GH_TOKEN  GitHub Actions token (GITHUB_TOKEN); no PAT is required
  OUT_DIR   Output directory (defaults to assets)
  MOCK=1    Generate deterministic fake data for local SVG layout testing
"""

from __future__ import annotations

import datetime as dt
import json
import math
import os
import random
import re
import sys
import urllib.error
import urllib.request
from html import escape
from pathlib import Path

USER = os.environ.get("GH_USER", "Lakshay1221-apple")
TOKEN = os.environ.get("GH_TOKEN", "")
OUT = Path(os.environ.get("OUT_DIR", "assets"))
MOCK = os.environ.get("MOCK") == "1"

FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
BG, BORDER, TITLE, MUTED = "#1a1b27", "#2f3549", "#70a5fd", "#a9b1d6"
LINE = "#4d6bff"

RANKS = ["C", "B", "A", "AA", "AAA", "S", "SS", "SSS"]

RANK_COLORS = [
    "#8a94a6",
    "#6ea8ff",
    "#3ddc97",
    "#2ec4b6",
    "#ffd166",
    "#ffb347",
    "#ff9f43",
    "#ff6b6b",
]

UNRANKED = "#4a5068"


def validate_identity() -> None:
    if not re.fullmatch(r"[A-Za-z0-9-]{1,39}", USER):
        raise SystemExit("GH_USER is not a valid GitHub username.")

    if MOCK and os.environ.get("GITHUB_ACTIONS", "").lower() == "true":
        raise SystemExit(
            "MOCK=1 is forbidden in GitHub Actions; refusing to publish test data."
        )

    if not MOCK and not TOKEN:
        raise SystemExit(
            "GH_TOKEN is required. In Actions, pass the built-in GITHUB_TOKEN."
        )


def gql(query: str, variables: dict) -> dict:
    """Call GitHub GraphQL without exposing credentials or API response data."""

    body = json.dumps({
        "query": query,
        "variables": variables,
    }).encode("utf-8")

    request = urllib.request.Request(
        "https://api.github.com/graphql",
        data=body,
        headers={
            "Authorization": f"Bearer {TOKEN}",
            "Content-Type": "application/json",
            "Accept": "application/vnd.github+json",
            "User-Agent": "public-profile-assets-generator",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            payload = json.load(response)

    except urllib.error.HTTPError as exc:
        raise SystemExit(
            f"GitHub GraphQL request failed with HTTP {exc.code}."
        ) from None

    except (
        urllib.error.URLError,
        TimeoutError,
        json.JSONDecodeError,
    ):
        raise SystemExit(
            "GitHub GraphQL request failed (network, timeout, or invalid JSON)."
        ) from None

    # IMPROVED ERROR HANDLING:
    # Show the actual GraphQL error instead of hiding it.
    if payload.get("errors"):
        for error in payload["errors"]:
            message = error.get("message", "Unknown GraphQL error")
            path = error.get("path", [])

            print(
                f"GraphQL Error: {message}",
                file=sys.stderr,
            )

            if path:
                print(
                    f"Error path: {path}",
                    file=sys.stderr,
                )

        raise SystemExit(1)

    data = payload.get("data")

    if not isinstance(data, dict):
        raise SystemExit(
            "GitHub GraphQL returned no usable data."
        )

    return data


def fetch() -> dict:
    now = dt.datetime.now(dt.timezone.utc).replace(microsecond=0)

    head_data = gql(
        "query($login:String!){ user(login:$login){ createdAt } }",
        {"login": USER},
    )

    user_head = head_data.get("user")

    if not user_head:
        raise SystemExit(
            "The requested public GitHub user could not be found."
        )

    created = dt.datetime.fromisoformat(
        user_head["createdAt"].replace("Z", "+00:00")
    )

    # Exclude private contributions from yearly commit statistics.
    rolling_from = now - dt.timedelta(days=365)

    aliases = []

    for year in range(created.year, now.year + 1):

        half_year_ranges = [
            (
                dt.datetime(year, 1, 1, tzinfo=dt.timezone.utc),
                dt.datetime(year, 7, 1, tzinfo=dt.timezone.utc)
                - dt.timedelta(seconds=1),
                "h1",
            ),
            (
                dt.datetime(year, 7, 1, tzinfo=dt.timezone.utc),
                dt.datetime(year + 1, 1, 1, tzinfo=dt.timezone.utc)
                - dt.timedelta(seconds=1),
                "h2",
            ),
        ]

        for start, end, half in half_year_ranges:
            if start > now:
                continue

            end = min(end, now)

            aliases.append(
                f'y{year}{half}: contributionsCollection('
                f'from: "{start.isoformat().replace("+00:00", "Z")}", '
                f'to: "{end.isoformat().replace("+00:00", "Z")}", '
                'includePrivateContributions: false) { totalCommitContributions }'
            )

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        createdAt

        followers {
          totalCount
        }

        publicRepositories: repositories(
          ownerAffiliations: OWNER,
          privacy: PUBLIC
        ) {
          totalCount
        }

        publicForkRepositories: repositories(
          ownerAffiliations: OWNER,
          privacy: PUBLIC,
          isFork: true
        ) {
          totalCount
        }

        publicOriginalRepositories: repositories(
          ownerAffiliations: OWNER,
          privacy: PUBLIC,
          isFork: false
        ) {
          totalCount
        }

        contributionsCollection(
          from: $from,
          to: $to,
          includePrivateContributions: false
        ) {
          contributionCalendar {
            totalContributions

            weeks {
              contributionDays {
                date
                contributionCount
              }
            }
          }
        }

        %s
      }
    }
    """ % "\n".join(aliases)

    result = gql(
        query,
        {
            "login": USER,
            "from": rolling_from.isoformat().replace("+00:00", "Z"),
            "to": now.isoformat().replace("+00:00", "Z"),
        },
    )

    user = result.get("user")

    if not user:
        raise SystemExit(
            "The requested public GitHub user could not be found."
        )

    public_commits = sum(
        value["totalCommitContributions"]
        for key, value in user.items()
        if key.startswith("y")
    )

    # Paginate only repositories explicitly filtered to PUBLIC.
    public_stars = 0
    public_languages = set()
    cursor = None

    while True:
        page = gql(
            """query($login:String!, $after:String) {
              user(login:$login) {
                repositories(
                  ownerAffiliations: OWNER,
                  privacy: PUBLIC,
                  first: 100,
                  after: $after
                ) {
                  nodes {
                    stargazerCount
                    primaryLanguage {
                      name
                    }
                  }

                  pageInfo {
                    hasNextPage
                    endCursor
                  }
                }
              }
            }""",
            {
                "login": USER,
                "after": cursor,
            },
        )["user"]["repositories"]

        public_stars += sum(
            node["stargazerCount"]
            for node in page["nodes"]
        )

        public_languages.update(
            node["primaryLanguage"]["name"]
            for node in page["nodes"]
            if node.get("primaryLanguage")
        )

        if not page["pageInfo"]["hasNextPage"]:
            break

        cursor = page["pageInfo"]["endCursor"]

    calendar = user["contributionsCollection"]["contributionCalendar"]

    today = now.date().isoformat()

    days = [
        (day["date"], day["contributionCount"])
        for week in calendar["weeks"]
        for day in week["contributionDays"]
        if day["date"] <= today
    ]

    return {
        "joined": created.year,
        "followers": user["followers"]["totalCount"],
        "public_repos": user["publicRepositories"]["totalCount"],
        "public_forks": user["publicForkRepositories"]["totalCount"],
        "public_original_repos": user["publicOriginalRepositories"]["totalCount"],
        "stars": public_stars,
        "languages": len(public_languages),
        "commits": public_commits,
        "contributions": calendar["totalContributions"],
        "days": days,
    }


def mock() -> dict:
    """Deterministic fake data for local SVG layout checks only."""

    rng = random.Random(7)

    today = dt.date.today()
    start = today - dt.timedelta(days=30)

    days = [
        (
            (start + dt.timedelta(days=i)).isoformat(),
            max(0, int(rng.gauss(6, 6))),
        )
        for i in range(31)
    ]

    return {
        "joined": 2025,
        "followers": 12,
        "public_repos": 50,
        "public_forks": 7,
        "public_original_repos": 43,
        "stars": 95,
        "languages": 14,
        "commits": 777,
        "contributions": sum(value for _, value in days),
        "days": days,
    }


def rank_of(value: int, thresholds: list[int]) -> tuple[int, float]:

    index = sum(
        1 for threshold in thresholds
        if value >= threshold
    ) - 1

    if index < 0:
        return -1, 0.0

    if index >= len(thresholds) - 1:
        return index, 1.0

    low, high = thresholds[index], thresholds[index + 1]

    return index, max(
        0.0,
        min(1.0, (value - low) / (high - low)),
    )


def cup(color: str) -> str:

    return (
        f'<path d="M-14 0 H14 V12 C14 24 8 30 0 30 C-8 30 -14 24 -14 12 Z" fill="{color}"/>'
        f'<path d="M-14 4 H-20 C-23 4 -22 15 -13 17" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
        f'<path d="M14 4 H20 C23 4 22 15 13 17" fill="none" stroke="{color}" stroke-width="3" stroke-linecap="round"/>'
        f'<rect x="-3" y="30" width="6" height="8" fill="{color}"/>'
        f'<rect x="-10" y="38" width="20" height="5" rx="2" fill="{color}"/>'
        '<path d="M-9 4 V12 C-9 17 -7 20 -5 22" fill="none" stroke="#fff" stroke-opacity=".35" stroke-width="2" stroke-linecap="round"/>'
    )


def trophies_svg(data: dict) -> str:

    age = max(
        0,
        dt.datetime.now(dt.timezone.utc).year - data["joined"],
    )

    items = [
        (
            f"Joined {data['joined']}",
            age,
            f"{age} yr" + ("" if age == 1 else "s"),
            [0, 1, 2, 3, 5, 7, 10, 15],
        ),
        (
            "Followers",
            data["followers"],
            f"{data['followers']} followers",
            [1, 5, 10, 25, 50, 100, 250, 500],
        ),
        (
            "Contributions",
            data["contributions"],
            f"{data['contributions']} public / year",
            [10, 100, 300, 600, 1000, 2000, 4000, 8000],
        ),
        (
            "Commit Contributions",
            data["commits"],
            f"{data['commits']} public commit contrib.",
            [10, 100, 300, 600, 1000, 2000, 4000, 8000],
        ),
        (
            "Public Repos",
            data["public_repos"],
            f"{data['public_repos']} public repos",
            [1, 5, 10, 20, 35, 50, 75, 100],
        ),
        (
            "Public Forks",
            data["public_forks"],
            f"{data['public_forks']} public forks",
            [1, 5, 10, 20, 35, 50, 75, 100],
        ),
        (
            "Original Repos",
            data["public_original_repos"],
            f"{data['public_original_repos']} originals",
            [1, 5, 10, 20, 35, 50, 75, 100],
        ),
        (
            "Public Stars",
            data["stars"],
            f"{data['stars']} public stars",
            [1, 5, 10, 30, 75, 150, 400, 1000],
        ),
        (
            "Languages",
            data["languages"],
            f"{data['languages']} languages",
            [1, 2, 3, 5, 8, 12, 20, 30],
        ),
    ]

    card_width, card_height, gap = 104, 150, 8

    width = (
        len(items) * card_width
        + (len(items) - 1) * gap
    )

    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{card_height}" viewBox="0 0 {width} {card_height}" role="img" '
        f'aria-label="Public GitHub trophies for {escape(USER)}"><title>Public GitHub trophies for {escape(USER)}</title>'
    ]

    for index, (title, value, label, thresholds) in enumerate(items):

        rank_index, progress = rank_of(value, thresholds)

        color = (
            RANK_COLORS[rank_index]
            if rank_index >= 0
            else UNRANKED
        )

        rank = (
            RANKS[rank_index]
            if rank_index >= 0
            else "-"
        )

        x = index * (card_width + gap)

        output.append(
            f'<g transform="translate({x} 0)">'
            f'<rect x=".5" y=".5" width="{card_width - 1}" height="{card_height - 1}" rx="8" fill="{BG}" stroke="{BORDER}"/>'
            f'<text x="{card_width / 2}" y="22" text-anchor="middle" font-family="{FONT}" font-size="11" font-weight="700" fill="{TITLE}">{escape(title)}</text>'
            f'<g transform="translate({card_width / 2} 34)">{cup(color)}</g>'
            f'<text x="{card_width / 2}" y="106" text-anchor="middle" font-family="{FONT}" font-size="16" font-weight="700" fill="{color}">{rank}</text>'
            f'<text x="{card_width / 2}" y="124" text-anchor="middle" font-family="{FONT}" font-size="9" fill="{MUTED}">{escape(label)}</text>'
            f'<rect x="12" y="134" width="80" height="4" rx="2" fill="{BORDER}"/>'
            f'<rect x="12" y="134" width="{80 * progress:.1f}" height="4" rx="2" fill="{color}"/>'
            '</g>'
        )

    output.append("</svg>")

    return "".join(output)


def nice_step(raw: float) -> int:

    for step in (
        1, 2, 5, 10, 20, 25, 50,
        100, 200, 500, 1000,
    ):
        if step >= raw:
            return step

    return int(math.ceil(raw))


def activity_svg(days: list[tuple[str, int]]) -> str:

    points = days[-31:]

    width, height = 780, 300

    left, right, top_margin, bottom = 60, 24, 60, 52

    plot_width = width - left - right
    plot_height = height - top_margin - bottom

    peak = max(
        [value for _, value in points] + [1]
    )

    step = nice_step(peak / 5)
    top = step * math.ceil(peak / step)

    count = len(points)

    xs = [
        left + (
            plot_width * i / (count - 1)
            if count > 1
            else plot_width / 2
        )
        for i in range(count)
    ]

    ys = [
        top_margin + plot_height - (value / top) * plot_height
        for _, value in points
    ]

    baseline = top_margin + plot_height

    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(USER)} public GitHub activity graph, last 31 days"><title>{escape(USER)} public GitHub Activity Graph</title>',

        '<defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{LINE}" stop-opacity=".40"/>'
        f'<stop offset="1" stop-color="{LINE}" stop-opacity="0"/>'
        '</linearGradient></defs>',

        f'<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="10" fill="{BG}" stroke="{BORDER}"/>',

        f'<text x="{width / 2}" y="32" text-anchor="middle" font-family="{FONT}" font-size="16" font-weight="700" fill="{TITLE}">{escape(USER)} Public GitHub Activity Graph</text>',
    ]

    for value in range(0, top + 1, step):

        y = baseline - value / top * plot_height

        output.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="{BORDER}" stroke-dasharray="3 4"/>'
        )

        output.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="{FONT}" font-size="10" fill="{MUTED}">{value}</text>'
        )

    if points:

        line = " ".join(
            f"{x:.1f},{y:.1f}"
            for x, y in zip(xs, ys)
        )

        area = (
            f"M{xs[0]:.1f},{baseline} "
            + " ".join(
                f"L{x:.1f},{y:.1f}"
                for x, y in zip(xs, ys)
            )
            + f" L{xs[-1]:.1f},{baseline} Z"
        )

        output.append(
            f'<path d="{area}" fill="url(#fill)"/>'
        )

        output.append(
            f'<polyline points="{line}" fill="none" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>'
        )

        for (date, value), x, y in zip(points, xs, ys):

            output.append(
                f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{LINE}"><title>{date}: {value} public contributions</title></circle>'
            )

            output.append(
                f'<text x="{x:.1f}" y="{baseline + 18}" text-anchor="middle" font-family="{FONT}" font-size="10" fill="{MUTED}">{int(date[8:10])}</text>'
            )

    else:

        output.append(
            f'<text x="{width / 2}" y="{baseline - 20}" text-anchor="middle" font-family="{FONT}" font-size="13" fill="{MUTED}">Run the profile-assets workflow to load public activity</text>'
        )

    output.append(
        f'<text x="{left + plot_width / 2}" y="{height - 12}" text-anchor="middle" font-family="{FONT}" font-size="11" fill="{MUTED}">Days</text>'
    )

    output.append(
        f'<text transform="rotate(-90)" x="{-(top_margin + plot_height / 2):.1f}" y="18" text-anchor="middle" font-family="{FONT}" font-size="11" fill="{MUTED}">Public contributions</text>'
    )

    output.append("</svg>")

    return "".join(output)


def write_atomically(path: Path, content: str) -> None:

    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(path.suffix + ".tmp")

    temporary.write_text(
        content,
        encoding="utf-8",
    )

    temporary.replace(path)


def main() -> None:

    validate_identity()

    data = mock() if MOCK else fetch()

    write_atomically(
        OUT / "trophies.svg",
        trophies_svg(data),
    )

    write_atomically(
        OUT / "activity-graph.svg",
        activity_svg(data["days"]),
    )

    print(
        f"Generated public-only profile assets in {OUT} for {USER}."
    )


if __name__ == "__main__":

    try:
        main()

    except (KeyError, TypeError, ValueError) as exc:

        print(
            f"Profile asset generation failed: invalid or incomplete public API data ({type(exc).__name__}).",
            file=sys.stderr,
        )

        raise SystemExit(1) from None
