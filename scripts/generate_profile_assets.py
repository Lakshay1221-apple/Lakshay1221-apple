
    
  
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
        ((start + dt.timedelta(days=i)).isoformat(), max(0, int(rng.gauss(6, 6))))
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
    index = sum(1 for threshold in thresholds if value >= threshold) - 1
    if index < 0:
        return -1, 0.0
    if index >= len(thresholds) - 1:
        return index, 1.0
    low, high = thresholds[index], thresholds[index + 1]
    return index, max(0.0, min(1.0, (value - low) / (high - low)))


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
    age = max(0, dt.datetime.now(dt.timezone.utc).year - data["joined"])
    items = [
        (f"Joined {data['joined']}", age, f"{age} yr" + ("" if age == 1 else "s"), [0, 1, 2, 3, 5, 7, 10, 15]),
        ("Followers", data["followers"], f"{data['followers']} followers", [1, 5, 10, 25, 50, 100, 250, 500]),
        ("Contributions", data["contributions"], f"{data['contributions']} public / year", [10, 100, 300, 600, 1000, 2000, 4000, 8000]),
        ("Commit Contributions", data["commits"], f"{data['commits']} public commit contrib.", [10, 100, 300, 600, 1000, 2000, 4000, 8000]),
        ("Public Repos", data["public_repos"], f"{data['public_repos']} public repos", [1, 5, 10, 20, 35, 50, 75, 100]),
        ("Public Forks", data["public_forks"], f"{data['public_forks']} public forks", [1, 5, 10, 20, 35, 50, 75, 100]),
        ("Original Repos", data["public_original_repos"], f"{data['public_original_repos']} originals", [1, 5, 10, 20, 35, 50, 75, 100]),
        ("Public Stars", data["stars"], f"{data['stars']} public stars", [1, 5, 10, 30, 75, 150, 400, 1000]),
        ("Languages", data["languages"], f"{data['languages']} languages", [1, 2, 3, 5, 8, 12, 20, 30]),
    ]
    card_width, card_height, gap = 104, 150, 8
    width = len(items) * card_width + (len(items) - 1) * gap
    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{card_height}" viewBox="0 0 {width} {card_height}" role="img" '
        f'aria-label="Public GitHub trophies for {escape(USER)}"><title>Public GitHub trophies for {escape(USER)}</title>'
    ]
    for index, (title, value, label, thresholds) in enumerate(items):
        rank_index, progress = rank_of(value, thresholds)
        color = RANK_COLORS[rank_index] if rank_index >= 0 else UNRANKED
        rank = RANKS[rank_index] if rank_index >= 0 else "-"
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
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 500, 1000):
        if step >= raw:
            return step
    return int(math.ceil(raw))


def activity_svg(days: list[tuple[str, int]]) -> str:
    points = days[-31:]
    width, height = 780, 300
    left, right, top_margin, bottom = 60, 24, 60, 52
    plot_width, plot_height = width - left - right, height - top_margin - bottom
    peak = max([value for _, value in points] + [1])
    step = nice_step(peak / 5)
    top = step * math.ceil(peak / step)
    count = len(points)
    xs = [left + (plot_width * i / (count - 1) if count > 1 else plot_width / 2) for i in range(count)]
    ys = [top_margin + plot_height - (value / top) * plot_height for _, value in points]
    baseline = top_margin + plot_height

    output = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" '
        f'aria-label="{escape(USER)} public GitHub activity graph, last 31 days"><title>{escape(USER)} public GitHub Activity Graph</title>',
        '<defs><linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">'
        f'<stop offset="0" stop-color="{LINE}" stop-opacity=".40"/><stop offset="1" stop-color="{LINE}" stop-opacity="0"/>'
        '</linearGradient></defs>',
        f'<rect x=".5" y=".5" width="{width - 1}" height="{height - 1}" rx="10" fill="{BG}" stroke="{BORDER}"/>',
        f'<text x="{width / 2}" y="32" text-anchor="middle" font-family="{FONT}" font-size="16" font-weight="700" fill="{TITLE}">{escape(USER)} Public GitHub Activity Graph</text>',
    ]
    for value in range(0, top + 1, step):
        y = baseline - value / top * plot_height
        output.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width - right}" y2="{y:.1f}" stroke="{BORDER}" stroke-dasharray="3 4"/>')
        output.append(f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="{FONT}" font-size="10" fill="{MUTED}">{value}</text>')

    if points:
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in zip(xs, ys))
        area = f"M{xs[0]:.1f},{baseline} " + " ".join(f"L{x:.1f},{y:.1f}" for x, y in zip(xs, ys)) + f" L{xs[-1]:.1f},{baseline} Z"
        output.append(f'<path d="{area}" fill="url(#fill)"/>')
        output.append(f'<polyline points="{line}" fill="none" stroke="{LINE}" stroke-width="2" stroke-linejoin="round"/>')
        for (date, value), x, y in zip(points, xs, ys):
            output.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{LINE}"><title>{date}: {value} public contributions</title></circle>')
            output.append(f'<text x="{x:.1f}" y="{baseline + 18}" text-anchor="middle" font-family="{FONT}" font-size="10" fill="{MUTED}">{int(date[8:10])}</text>')
    else:
        output.append(f'<text x="{width / 2}" y="{baseline - 20}" text-anchor="middle" font-family="{FONT}" font-size="13" fill="{MUTED}">Run the profile-assets workflow to load public activity</text>')

    output.append(f'<text x="{left + plot_width / 2}" y="{height - 12}" text-anchor="middle" font-family="{FONT}" font-size="11" fill="{MUTED}">Days</text>')
    output.append(
        f'<text transform="rotate(-90)" x="{-(top_margin + plot_height / 2):.1f}" y="18" text-anchor="middle" font-family="{FONT}" font-size="11" fill="{MUTED}">Public contributions</text>'
    )
    output.append("</svg>")
    return "".join(output)


def write_atomically(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(content, encoding="utf-8")
    temporary.replace(path)


def main() -> None:
    validate_identity()
    data = mock() if MOCK else fetch()
    write_atomically(OUT / "trophies.svg", trophies_svg(data))
    write_atomically(OUT / "activity-graph.svg", activity_svg(data["days"]))
    print(f"Generated public-only profile assets in {OUT} for {USER}.")


if __name__ == "__main__":
    try:
        main()
    except (KeyError, TypeError, ValueError) as exc:
        # Keep logs concise; do not print API payloads or environment values.
        print(f"Profile asset generation failed: invalid or incomplete public API data ({type(exc).__name__}).", file=sys.stderr)
        raise SystemExit(1) from None

