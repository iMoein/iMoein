#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import time
import urllib.parse
from collections import Counter
from html import escape

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "profile.json"
ASCII_PATH = ROOT / "assets" / "photo-ascii.txt"
SVG_PATH = ROOT / "assets" / "terminal.svg"
README_PATH = ROOT / "README.md"

BG = "#0b1220"
PANEL = "#0d1117"
BORDER = "#1f2937"
FG = "#d1d5db"
WHITE = "#f9fafb"
MUTED = "#9ca3af"
DIM = "#4b5563"
ORANGE = "#fb923c"
BLUE = "#bfdbfe"
GREEN = "#86efac"
RED = "#fca5a5"


def load_config() -> dict:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
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
        nm = cursor.month + 1
        ny = cursor.year
        if nm == 13:
            nm = 1
            ny += 1
        try:
            nxt = cursor.replace(year=ny, month=nm)
        except ValueError:
            nxt = cursor.replace(year=ny, month=nm, day=28)
        if nxt <= now:
            months += 1
            cursor = nxt
        else:
            break
    days = (now.date() - cursor.date()).days
    return years, months, days


def api_get(url: str, token: str | None, allow_202: bool = False):
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-terminal-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, headers=headers, timeout=30)
        if allow_202 and r.status_code == 202:
            return {"_status": 202}
        return None if r.status_code >= 400 else r.json()
    except requests.RequestException:
        return None


def github_graphql(query: str, variables: dict, token: str | None):
    if not token:
        return None
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "github-profile-terminal-readme"}
    try:
        r = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json={"query": query, "variables": variables},
            timeout=30,
        )
        return None if r.status_code >= 400 else r.json().get("data")
    except requests.RequestException:
        return None


def fetch_code_frequency(owner: str, repo_name: str, token: str | None) -> tuple[int, int, int]:
    url = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(repo_name)}/stats/code_frequency"
    data = None
    for _ in range(3):
        resp = api_get(url, token, allow_202=True)
        if isinstance(resp, dict) and resp.get("_status") == 202:
            time.sleep(1.2)
            continue
        data = resp
        break
    if not isinstance(data, list):
        return 0, 0, 0
    added = 0
    deleted = 0
    for row in data:
        if isinstance(row, list) and len(row) >= 3:
            added += int(row[1] or 0)
            deleted += abs(int(row[2] or 0))
    current = max(0, added - deleted)
    return current, added, deleted


def fetch_telemetry(username: str, token: str | None) -> dict:
    encoded = urllib.parse.quote(username)
    repos = []
    page = 1
    while page <= 10:
        data = api_get(
            f"https://api.github.com/users/{encoded}/repos?per_page=100&page={page}&sort=updated&type=owner",
            token,
        )
        if not isinstance(data, list) or not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1

    owned_non_forks = [r for r in repos if not r.get("fork")]
    lang_counter = Counter(r.get("language") for r in owned_non_forks if r.get("language"))
    top_langs = [lang for lang, _ in lang_counter.most_common(5)] or ["-"]

    lines_total = 0
    lines_added = 0
    lines_deleted = 0
    for repo in owned_non_forks:
        owner = (repo.get("owner") or {}).get("login") or username
        name = repo.get("name")
        if not name:
            continue
        current, added, deleted = fetch_code_frequency(owner, name, token)
        lines_total += current
        lines_added += added
        lines_deleted += deleted

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
              contributionCalendar { totalContributions }
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
    cal = (c.get("contributionCalendar") or {})

    return {
        "lines_total": lines_total,
        "lines_added": lines_added,
        "lines_deleted": lines_deleted,
        "contribs_1y": cal.get("totalContributions", 0),
        "commits_1y": c.get("totalCommitContributions", 0),
        "prs_1y": c.get("totalPullRequestContributions", 0),
        "issues_1y": c.get("totalIssueContributions", 0),
        "top_langs": top_langs,
    }


def fmt(n: int) -> str:
    return f"{int(n):,}"


def text(x: int, y: int, value: str, color: str = FG, size: float = 14, weight: str = "400") -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" xml:space="preserve">{escape(value)}</text>'


def title(x: int, y: int, value: str) -> str:
    return text(x, y, f"- {value} " + "-" * max(8, 62 - len(value)), WHITE, 14, "700")


def row(x: int, y: int, label: str, value: str, width: int = 60, value_color: str = BLUE) -> str:
    label_text = f"{label}:"
    dots = " " + "." * max(3, width - len(label_text) - len(value)) + " "
    return (
        f'<text x="{x}" y="{y}" font-size="14" xml:space="preserve">'
        f'<tspan fill="{ORANGE}" font-weight="700">{escape(label_text)}</tspan>'
        f'<tspan fill="{DIM}">{escape(dots)}</tspan>'
        f'<tspan fill="{value_color}" font-weight="700">{escape(value)}</tspan>'
        f'</text>'
    )


def trunc(value: str, max_len: int = 50) -> str:
    return value if len(value) <= max_len else value[:max_len - 3] + "..."


def write_readme(cache_bust: str) -> None:
    repo = os.getenv("GITHUB_REPOSITORY", "iMoein/iMoein")
    owner, name = repo.split("/", 1)
    image_url = f"https://raw.githubusercontent.com/{owner}/{name}/main/assets/terminal.svg?v={cache_bust}"
    README_PATH.write_text(
        f'<p align="center">\n  <img src="{image_url}" alt="Moein Ghezelbash GitHub profile terminal" width="1120" />\n</p>\n',
        encoding="utf-8",
    )


def generate_svg() -> str:
    cfg = load_config()
    username = cfg["github_username"]
    token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    telemetry = fetch_telemetry(username, token)

    years, months, days = age_parts(cfg["birth_datetime"])
    uptime = f"{years} years, {months} months, {days} days"
    unix_time = str(int(dt.datetime.now(dt.UTC).timestamp()))
    ascii_lines = ASCII_PATH.read_text(encoding="utf-8").splitlines()

    width, height = 1180, 720
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" rx="14" fill="{BG}"/>',
        f'<rect x="12" y="12" width="1156" height="696" rx="12" fill="{PANEL}" stroke="{BORDER}" stroke-width="1"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace;dominant-baseline:hanging}</style>',
    ]

    ax, ay = 24, 28
    font_size, line_h = 10.0, 12.4
    for i, line in enumerate(ascii_lines[:42]):
        c = WHITE if i < 16 else FG if i < 29 else MUTED
        out.append(text(ax, int(ay + i * line_h), line, c, font_size))

    x, y = 585, 30
    out.append(title(x, y, f"{username.lower()}@github")); y += 42
    out.append(text(x, y, "$ systemctl status profile.service", GREEN, 13, "700")); y += 30

    system_rows = [
        ("Name", cfg["name"], BLUE),
        ("OS", ", ".join(cfg["os"]), BLUE),
        ("Kernel", cfg.get("kernel", "Darwin/XNU, NT, Linux"), BLUE),
        ("Uptime", uptime, GREEN),
        ("UnixTime", unix_time, GREEN),
        ("Role", cfg["role"], BLUE),
        ("Editor", cfg["editor"], BLUE),
        ("Langs", ", ".join(cfg["programming_languages"]), BLUE),
        ("Toolchain", ", ".join(cfg["toolchain"]), BLUE),
        ("Services", ", ".join(cfg["services"]), BLUE),
    ]
    for label, value, color in system_rows:
        out.append(row(x, y, label, trunc(value), value_color=color)); y += 27

    y += 16
    out.append(title(x, y, "network")); y += 36
    out.append(row(x, y, "LinkedIn", "linkedin.com/in/moeinghezelbash", value_color=BLUE)); y += 48

    out.append(title(x, y, "telemetry")); y += 36
    telemetry_rows = [
        ("Lines.Code", fmt(telemetry["lines_total"]), GREEN),
        ("Lines.Added", "+" + fmt(telemetry["lines_added"]), GREEN),
        ("Lines.Deleted", "-" + fmt(telemetry["lines_deleted"]), RED),
        ("Commits.1y", fmt(telemetry["commits_1y"]), BLUE),
        ("Top.Langs", ", ".join(telemetry["top_langs"]), BLUE),
    ]
    for label, value, color in telemetry_rows:
        out.append(row(x, y, label, trunc(value), value_color=color)); y += 27

    updated = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    out.append(text(x, height - 34, f"Last updated: {updated}", MUTED, 12))
    out.append("</svg>")

    write_readme(str(int(dt.datetime.now(dt.UTC).timestamp())))
    return "\n".join(out)


if __name__ == "__main__":
    SVG_PATH.write_text(generate_svg(), encoding="utf-8")
    print(f"Generated {SVG_PATH.relative_to(ROOT)} and README.md")
