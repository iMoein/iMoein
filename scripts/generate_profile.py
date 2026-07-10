#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import urllib.parse
from collections import Counter
from html import escape

import requests


ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "profile.json"
ASCII_PATH = ROOT / "assets" / "photo-ascii.txt"
SVG_PATH = ROOT / "assets" / "terminal.svg"

BG = "#0d1117"
FG = "#d1d7e0"
MUTED = "#7d8590"
DIM = "#4f5968"
ORANGE = "#ff9950"
BLUE = "#a5d6ff"
GREEN = "#56d364"
RED = "#ff7b72"
WHITE = "#f0f6fc"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as f:
        cfg = json.load(f)
    if os.getenv("GH_USERNAME"):
        cfg["github_username"] = os.getenv("GH_USERNAME")
    return cfg


def age_parts(birth_iso: str) -> tuple[int, int, int]:
    birth = dt.datetime.fromisoformat(birth_iso)
    now = dt.datetime.now()
    years = now.year - birth.year
    if (now.month, now.day, now.time()) < (birth.month, birth.day, birth.time()):
        years -= 1

    cursor = birth.replace(year=birth.year + years)
    months = 0
    while True:
        next_month = cursor.month + 1
        next_year = cursor.year
        if next_month == 13:
            next_month = 1
            next_year += 1

        try:
            nxt = cursor.replace(year=next_year, month=next_month)
        except ValueError:
            nxt = cursor.replace(year=next_year, month=next_month, day=28)

        if nxt <= now:
            months += 1
            cursor = nxt
        else:
            break

    days = (now.date() - cursor.date()).days
    return years, months, days


def api_get(url: str, token: str | None) -> dict | list | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-terminal-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, headers=headers, timeout=20)
        if r.status_code >= 400:
            return None
        return r.json()
    except requests.RequestException:
        return None


def github_graphql(query: str, variables: dict, token: str | None) -> dict | None:
    if not token:
        return None
    headers = {
        "Authorization": f"Bearer {token}",
        "User-Agent": "github-profile-terminal-readme",
    }
    try:
        r = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json={"query": query, "variables": variables},
            timeout=20,
        )
        if r.status_code >= 400:
            return None
        payload = r.json()
        return payload.get("data")
    except requests.RequestException:
        return None


def fetch_github_stats(username: str, token: str | None) -> dict:
    encoded = urllib.parse.quote(username)
    user = api_get(f"https://api.github.com/users/{encoded}", token) or {}

    repos = []
    page = 1
    while page <= 10:
        url = (
            f"https://api.github.com/users/{encoded}/repos"
            f"?per_page=100&page={page}&sort=updated&type=owner"
        )
        data = api_get(url, token)
        if not isinstance(data, list) or not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1

    owned_non_forks = [r for r in repos if not r.get("fork")]
    stars = sum(int(r.get("stargazers_count", 0)) for r in repos)
    forks = sum(int(r.get("forks_count", 0)) for r in repos)
    lang_counter = Counter(r.get("language") for r in owned_non_forks if r.get("language"))
    top_langs = [lang for lang, _ in lang_counter.most_common(5)]

    now = dt.datetime.now(dt.UTC)
    year_ago = now - dt.timedelta(days=365)
    gql = github_graphql(
        """
        query($login: String!, $from: DateTime!, $to: DateTime!) {
          user(login: $login) {
            contributionsCollection(from: $from, to: $to) {
              totalCommitContributions
              totalIssueContributions
              totalPullRequestContributions
              totalPullRequestReviewContributions
              totalRepositoryContributions
              contributionCalendar {
                totalContributions
              }
            }
          }
        }
        """,
        {
            "login": username,
            "from": year_ago.isoformat(timespec="seconds").replace("+00:00", "Z"),
            "to": now.isoformat(timespec="seconds").replace("+00:00", "Z"),
        },
        token,
    )

    c = (((gql or {}).get("user") or {}).get("contributionsCollection") or {})
    total_contributions = (c.get("contributionCalendar") or {}).get("totalContributions")

    return {
        "repos": user.get("public_repos") or len(repos) or "—",
        "stars": stars if repos else "—",
        "followers": user.get("followers", "—"),
        "following": user.get("following", "—"),
        "forks": forks if repos else "—",
        "top_langs": top_langs or ["—"],
        "commits_1y": c.get("totalCommitContributions", "—"),
        "contribs_1y": total_contributions if total_contributions is not None else "—",
        "prs_1y": c.get("totalPullRequestContributions", "—"),
        "issues_1y": c.get("totalIssueContributions", "—"),
    }


def text_line(x: int, y: int, text: str, color: str = FG, size: float = 14, weight: str = "400") -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
        f'font-weight="{weight}" xml:space="preserve">{escape(text)}</text>'
    )


def info_line(x: int, y: int, label: str, value: str, width: int = 65) -> str:
    label_txt = f"{label}:"
    dots_count = max(3, width - len(label_txt) - len(value))
    dots = " " + "." * dots_count + " "
    return (
        f'<text x="{x}" y="{y}" font-size="14" xml:space="preserve">'
        f'<tspan fill="{ORANGE}" font-weight="700">{escape(label_txt)}</tspan>'
        f'<tspan fill="{DIM}">{escape(dots)}</tspan>'
        f'<tspan fill="{BLUE}" font-weight="700">{escape(value)}</tspan>'
        f'</text>'
    )


def section_title(x: int, y: int, title: str) -> str:
    left = "─ " + title + " "
    right_len = max(10, 68 - len(left))
    return text_line(x, y, left + ("─" * right_len), WHITE, 14, "700")


def truncate(value: str, max_len: int = 58) -> str:
    return value if len(value) <= max_len else value[: max_len - 3] + "..."


def generate_svg() -> str:
    cfg = load_config()
    username = cfg["github_username"]
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    stats = fetch_github_stats(username, token)

    years, months, days = age_parts(cfg["birth_datetime"])
    birth = dt.datetime.fromisoformat(cfg["birth_datetime"])
    ascii_lines = ASCII_PATH.read_text(encoding="utf-8").splitlines()

    width, height = 1120, 620
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" rx="14" fill="{BG}"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace;dominant-baseline:hanging}</style>',
    ]

    # Left: true keyboard-character ASCII portrait. No embedded raster image.
    x_ascii, y_ascii = 18, 22
    font_size, line_h = 7.65, 10.75
    for i, line in enumerate(ascii_lines[:52]):
        # Subtle terminal-like tonal change while keeping every pixel as characters.
        color = "#f0f6fc" if i < 20 else "#d1d7e0" if i < 35 else "#8b949e"
        lines.append(text_line(x_ascii, int(y_ascii + i * line_h), line, color, font_size))

    x, y = 440, 28
    lines.append(section_title(x, y, f"{username}@github"))
    y += 38

    born_value = birth.strftime("%d %b %Y, %H:%M")
    info = [
        ("Name", cfg["name"]),
        ("OS", ", ".join(cfg["os"])),
        ("Born", born_value),
        ("Life", f"{years} years, {months} months, {days} days"),
        ("Role", cfg["role"]),
        ("IDE", cfg["ide"]),
        ("Languages.Program", ", ".join(cfg["programming_languages"])),
        ("Languages.Tools", ", ".join(cfg["tools"])),
        ("Focus", ", ".join(cfg["focus"])),
    ]

    for label, value in info:
        lines.append(info_line(x, y, label, truncate(value)))
        y += 28

    y += 12
    lines.append(section_title(x, y, "Contact"))
    y += 36
    lines.append(info_line(x, y, "LinkedIn", "linkedin.com/in/moeinghezelbash"))
    y += 46

    lines.append(section_title(x, y, "GitHub Stats"))
    y += 36

    gh_lines = [
        ("Repos", f'{stats["repos"]} | Stars: {stats["stars"]} | Forks: {stats["forks"]}'),
        ("Followers", f'{stats["followers"]} | Following: {stats["following"]}'),
        ("Contribs.1y", f'{stats["contribs_1y"]} | Commits.1y: {stats["commits_1y"]}'),
        ("PRs/Issues.1y", f'{stats["prs_1y"]} PRs | {stats["issues_1y"]} Issues'),
        ("Top.Langs", ", ".join(stats["top_langs"])),
    ]

    for label, value in gh_lines:
        lines.append(info_line(x, y, label, truncate(str(value))))
        y += 28

    updated = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(text_line(x, height - 34, f"Last updated: {updated}", MUTED, 12))
    lines.append("</svg>")
    return "\n".join(lines)


if __name__ == "__main__":
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(generate_svg(), encoding="utf-8")
    print(f"Generated {SVG_PATH.relative_to(ROOT)}")
