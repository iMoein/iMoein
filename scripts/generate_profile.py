#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import urllib.parse
from collections import Counter
from html import escape
from typing import Any

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "profile.json"
SVG_PATH = ROOT / "assets" / "terminal.svg"
README_PATH = ROOT / "README.md"

BG = "#08111f"
PANEL = "#0f172a"
PANEL_2 = "#111c2f"
BORDER = "#233044"
FG = "#d8dee9"
WHITE = "#f8fafc"
MUTED = "#94a3b8"
DIM = "#475569"
ORANGE = "#fb923c"
BLUE = "#bfdbfe"
GREEN = "#86efac"
RED = "#fca5a5"
CYAN = "#67e8f9"
YELLOW = "#fde68a"

CODE_EXTENSIONS = {
    ".py", ".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs",
    ".go", ".rs", ".java", ".kt", ".kts", ".swift",
    ".c", ".h", ".cpp", ".hpp", ".cs", ".php",
    ".rb", ".pl", ".sh", ".bash", ".zsh", ".fish", ".ps1",
    ".sql", ".html", ".css", ".scss", ".sass", ".less",
    ".vue", ".svelte", ".astro",
    ".json", ".yaml", ".yml", ".toml", ".xml",
    ".prisma", ".graphql", ".gql", ".dockerfile",
}
CODE_FILENAMES = {
    "Dockerfile", "Makefile", "Rakefile", "Gemfile", "Procfile",
    ".env.example", "docker-compose.yml", "docker-compose.yaml",
}
SKIP_PARTS = {
    ".git", "node_modules", "vendor", "dist", "build", ".next", ".nuxt",
    "coverage", ".cache", ".turbo", "target", "bin", "obj", "__pycache__",
    ".venv", "venv", "env", "Pods", "DerivedData",
}


def load_config() -> dict[str, Any]:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if os.getenv("GH_USERNAME"):
        cfg["github_username"] = os.getenv("GH_USERNAME")
    return cfg


def token() -> str | None:
    return os.getenv("PROFILE_STATS_TOKEN") or os.getenv("GH_TOKEN") or os.getenv("GITHUB_TOKEN")


def api_get(url: str, auth_token: str | None) -> Any | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-terminal-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    try:
        response = requests.get(url, headers=headers, timeout=30)
        if response.status_code >= 400:
            return None
        return response.json()
    except requests.RequestException:
        return None


def github_graphql(query: str, variables: dict[str, Any], auth_token: str | None) -> dict[str, Any] | None:
    if not auth_token:
        return None
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "User-Agent": "github-profile-terminal-readme",
    }
    try:
        response = requests.post(
            "https://api.github.com/graphql",
            headers=headers,
            json={"query": query, "variables": variables},
            timeout=30,
        )
        if response.status_code >= 400:
            return None
        payload = response.json()
        if payload.get("errors"):
            return None
        return payload.get("data")
    except requests.RequestException:
        return None


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
    return years, months, (now.date() - cursor.date()).days


def iso_utc(day: dt.date, end_of_day: bool = False) -> str:
    if end_of_day:
        return f"{day.isoformat()}T23:59:59Z"
    return f"{day.isoformat()}T00:00:00Z"


def fetch_contribution_activity(username: str, created_at: str | None, auth_token: str | None) -> dict[str, Any]:
    if not auth_token:
        return {
            "active_days": None,
            "first_active": None,
            "days_since_first": None,
            "total_contributions": None,
        }

    today = dt.datetime.now(dt.UTC).date()
    if created_at:
        start_day = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00")).date()
    else:
        start_day = today - dt.timedelta(days=365)

    query = """
    query($login: String!, $from: DateTime!, $to: DateTime!) {
      user(login: $login) {
        contributionsCollection(from: $from, to: $to) {
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
      }
    }
    """

    active_dates: set[str] = set()
    total_contributions = 0
    cursor = start_day
    while cursor <= today:
        chunk_end = min(cursor + dt.timedelta(days=364), today)
        data = github_graphql(
            query,
            {
                "login": username,
                "from": iso_utc(cursor),
                "to": iso_utc(chunk_end, end_of_day=True),
            },
            auth_token,
        )
        calendar = (((data or {}).get("user") or {}).get("contributionsCollection") or {}).get("contributionCalendar")
        if not calendar:
            cursor = chunk_end + dt.timedelta(days=1)
            continue
        total_contributions += int(calendar.get("totalContributions") or 0)
        for week in calendar.get("weeks") or []:
            for day in week.get("contributionDays") or []:
                date_str = day.get("date")
                if not date_str:
                    continue
                try:
                    date_obj = dt.date.fromisoformat(date_str)
                except ValueError:
                    continue
                if cursor <= date_obj <= chunk_end and int(day.get("contributionCount") or 0) > 0:
                    active_dates.add(date_str)
        cursor = chunk_end + dt.timedelta(days=1)

    if not active_dates:
        return {
            "active_days": None,
            "first_active": None,
            "days_since_first": None,
            "total_contributions": total_contributions or None,
        }

    first_active = min(active_dates)
    first_active_date = dt.date.fromisoformat(first_active)
    return {
        "active_days": len(active_dates),
        "first_active": first_active,
        "days_since_first": (today - first_active_date).days,
        "total_contributions": total_contributions,
    }


def list_repositories(username: str, auth_token: str | None) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []

    # Public owner repositories.
    page = 1
    encoded = urllib.parse.quote(username)
    while page <= 10:
        data = api_get(
            f"https://api.github.com/users/{encoded}/repos?per_page=100&page={page}&sort=updated&type=owner",
            auth_token,
        )
        if not isinstance(data, list) or not data:
            break
        repos.extend(data)
        if len(data) < 100:
            break
        page += 1

    # Optional private repositories when PROFILE_STATS_TOKEN is a real user token.
    if os.getenv("PROFILE_STATS_TOKEN"):
        page = 1
        while page <= 10:
            data = api_get(
                f"https://api.github.com/user/repos?per_page=100&page={page}&visibility=all&affiliation=owner&sort=updated",
                auth_token,
            )
            if not isinstance(data, list) or not data:
                break
            repos.extend([r for r in data if ((r.get("owner") or {}).get("login") or "").lower() == username.lower()])
            if len(data) < 100:
                break
            page += 1

    by_full_name: dict[str, dict[str, Any]] = {}
    for repo in repos:
        if repo.get("fork"):
            continue
        full_name = repo.get("full_name")
        if full_name:
            by_full_name[full_name.lower()] = repo
    return list(by_full_name.values())


def should_count_file(path: pathlib.Path) -> bool:
    parts = set(path.parts)
    if parts & SKIP_PARTS:
        return False
    if path.name in CODE_FILENAMES:
        return True
    if path.name.lower().endswith((".min.js", ".min.css", ".map")):
        return False
    return path.suffix.lower() in CODE_EXTENSIONS


def count_repo_lines(repo: dict[str, Any], auth_token: str | None, root: pathlib.Path) -> tuple[int, int]:
    clone_url = repo.get("clone_url")
    full_name = repo.get("full_name") or repo.get("name") or "repo"
    if not clone_url:
        return 0, 0

    target = root / full_name.replace("/", "__")
    if auth_token and os.getenv("PROFILE_STATS_TOKEN"):
        parsed = urllib.parse.urlparse(clone_url)
        clone_url = urllib.parse.urlunparse(
            parsed._replace(netloc=f"x-access-token:{urllib.parse.quote(auth_token)}@{parsed.netloc}")
        )

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", clone_url, str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
        )
        tracked = subprocess.check_output(["git", "-C", str(target), "ls-files", "-z"], timeout=30)
    except Exception:
        return 0, 0

    total_lines = 0
    total_files = 0
    for raw in tracked.split(b"\0"):
        if not raw:
            continue
        rel = pathlib.Path(raw.decode("utf-8", errors="ignore"))
        if not should_count_file(rel):
            continue
        file_path = target / rel
        try:
            if file_path.stat().st_size > 1_500_000:
                continue
            with file_path.open("r", encoding="utf-8", errors="ignore") as fh:
                total_lines += sum(1 for _ in fh)
            total_files += 1
        except OSError:
            continue
    return total_lines, total_files


def count_code_lines(repos: list[dict[str, Any]], auth_token: str | None, max_repos: int) -> dict[str, Any]:
    if not repos:
        return {"lines_code": None, "files_code": None, "repos_scanned": None}
    total_lines = 0
    total_files = 0
    scanned = 0
    with tempfile.TemporaryDirectory(prefix="profile-stats-") as tmp:
        tmp_path = pathlib.Path(tmp)
        for repo in repos[:max_repos]:
            lines, files = count_repo_lines(repo, auth_token, tmp_path)
            if files > 0:
                scanned += 1
            total_lines += lines
            total_files += files
    return {
        "lines_code": total_lines if total_files else None,
        "files_code": total_files if total_files else None,
        "repos_scanned": scanned,
    }


def collect_stats(cfg: dict[str, Any]) -> dict[str, Any]:
    username = cfg["github_username"]
    auth_token = token()
    user = api_get(f"https://api.github.com/users/{urllib.parse.quote(username)}", auth_token) or {}
    created_at = user.get("created_at")
    repos = list_repositories(username, auth_token)
    repo_count = len(repos) if user or repos else None
    languages = Counter(r.get("language") for r in repos if r.get("language"))
    max_repos = int((cfg.get("stats") or {}).get("max_repos_to_clone") or 80)
    line_stats = count_code_lines(repos, auth_token, max_repos=max_repos)
    activity = fetch_contribution_activity(username, created_at, auth_token)
    return {
        "repo_count_scanned": repo_count,
        "top_langs": [lang for lang, _ in languages.most_common(5)] or None,
        "github_created": created_at[:10] if isinstance(created_at, str) else None,
        **line_stats,
        **activity,
    }


def fmt_int(value: Any) -> str:
    if value is None:
        return "sync pending"
    try:
        return f"{int(value):,}"
    except Exception:
        return str(value)


def fmt_value(value: Any) -> str:
    if value is None or value == "":
        return "sync pending"
    return str(value)


def text(x: int, y: int, value: str, color: str = FG, size: float = 14, weight: str = "400") -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" xml:space="preserve">{escape(value)}</text>'


def tspan_line(x: int, y: int, label: str, value: str, width: int = 57, value_color: str = BLUE) -> str:
    label_txt = f"{label}:"
    dots_count = max(3, width - len(label_txt) - len(value))
    dots = " " + "." * dots_count + " "
    return (
        f'<text x="{x}" y="{y}" font-size="14" xml:space="preserve">'
        f'<tspan fill="{ORANGE}" font-weight="700">{escape(label_txt)}</tspan>'
        f'<tspan fill="{DIM}">{escape(dots)}</tspan>'
        f'<tspan fill="{value_color}" font-weight="700">{escape(value)}</tspan>'
        f'</text>'
    )


def section(x: int, y: int, title: str, width_chars: int = 58) -> str:
    left = "─ " + title + " "
    return text(x, y, left + ("─" * max(10, width_chars - len(left))), WHITE, 14, "700")


def box(x: int, y: int, w: int, h: int, title: str) -> list[str]:
    return [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" fill="{PANEL_2}" stroke="{BORDER}" stroke-width="1"/>',
        text(x + 18, y + 16, title, WHITE, 14, "700"),
    ]


def truncate(value: str, max_len: int = 48) -> str:
    return value if len(value) <= max_len else value[: max_len - 3] + "..."


def write_readme(cache_bust: str) -> None:
    repo = os.getenv("GITHUB_REPOSITORY", "iMoein/iMoein")
    owner, name = repo.split("/", 1)
    image_url = f"https://raw.githubusercontent.com/{owner}/{name}/main/assets/terminal.svg?v={cache_bust}"
    README_PATH.write_text(
        f'<p align="center">\n  <img src="{image_url}" alt="Moein Ghezelbash GitHub server profile" width="1120" />\n</p>\n',
        encoding="utf-8",
    )


def generate_svg() -> str:
    cfg = load_config()
    stats = collect_stats(cfg)
    username = cfg["github_username"]

    years, months, days = age_parts(cfg["birth_datetime"])
    birth_dt = dt.datetime.fromisoformat(cfg["birth_datetime"])
    uptime = f"{years} years, {months} months, {days} days"
    unix_time = str(int(birth_dt.timestamp()))

    width, height = 1120, 620
    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" rx="14" fill="{BG}"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace;dominant-baseline:hanging}</style>',
        f'<rect x="12" y="12" width="1096" height="596" rx="12" fill="{PANEL}" stroke="{BORDER}" stroke-width="1"/>',
    ]

    out.append(text(38, 34, "●", GREEN, 13, "700"))
    out.append(text(58, 34, f"{username.lower()}@github", WHITE, 18, "700"))
    out.append(text(250, 39, "server profile telemetry", MUTED, 12, "400"))
    out.append(text(930, 39, "status: online", GREEN, 12, "700"))

    # Left column: runtime / identity.
    out += box(38, 80, 500, 210, "runtime")
    y = 120
    runtime_lines = [
        ("Name", cfg["name"], BLUE),
        ("Role", cfg["role"], BLUE),
        ("OS", ", ".join(cfg["os"]), BLUE),
        ("Kernel", cfg.get("kernel", "XNU / NT / Linux"), BLUE),
        ("Uptime", uptime, GREEN),
        ("UnixTime", unix_time, CYAN),
    ]
    for label, value, color in runtime_lines:
        out.append(tspan_line(58, y, label, truncate(value, 43), width=50, value_color=color))
        y += 26

    out += box(38, 312, 500, 232, "toolchain")
    y = 352
    tool_lines = [
        ("Editor", cfg["ide"], BLUE),
        ("Langs", ", ".join(cfg["programming_languages"]), BLUE),
        ("Tools", ", ".join(cfg["tools"]), BLUE),
        ("Services", ", ".join(cfg["focus"]), BLUE),
        ("LinkedIn", "linkedin.com/in/moeinghezelbash", BLUE),
    ]
    for label, value, color in tool_lines:
        out.append(tspan_line(58, y, label, truncate(value, 43), width=50, value_color=color))
        y += 28

    # Right column: GitHub activity / code telemetry.
    out += box(570, 80, 512, 236, "github activity")
    y = 120
    activity_lines = [
        ("GitHub.Created", fmt_value(stats.get("github_created")), BLUE),
        ("GitHub.ActiveDays", fmt_int(stats.get("active_days")), GREEN),
        ("GitHub.FirstActive", fmt_value(stats.get("first_active")), CYAN),
        ("GitHub.DaysOnline", fmt_int(stats.get("days_since_first")), GREEN),
        ("Contributions", fmt_int(stats.get("total_contributions")), BLUE),
    ]
    for label, value, color in activity_lines:
        out.append(tspan_line(590, y, label, truncate(value, 42), width=50, value_color=color))
        y += 30

    out += box(570, 342, 512, 202, "code telemetry")
    y = 382
    top_langs = stats.get("top_langs")
    code_lines = [
        ("Lines.Code", fmt_int(stats.get("lines_code")), GREEN),
        ("Files.Code", fmt_int(stats.get("files_code")), BLUE),
        ("Repos.Scanned", fmt_int(stats.get("repos_scanned")), BLUE),
        ("Repos.Visible", fmt_int(stats.get("repo_count_scanned")), BLUE),
        ("Top.Langs", ", ".join(top_langs) if top_langs else "sync pending", BLUE),
    ]
    for label, value, color in code_lines:
        out.append(tspan_line(590, y, label, truncate(value, 42), width=50, value_color=color))
        y += 28

    updated = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    out.append(text(58, height - 42, f"last update: {updated}", MUTED, 12, "400"))
    out.append(text(860, height - 42, "cache-busted README image", DIM, 12, "400"))
    out.append("</svg>")

    write_readme(dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S"))
    return "\n".join(out)


if __name__ == "__main__":
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(generate_svg(), encoding="utf-8")
    print(f"Generated {SVG_PATH.relative_to(ROOT)} and refreshed README.md")
