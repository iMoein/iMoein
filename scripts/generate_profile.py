#!/usr/bin/env python3
from __future__ import annotations

import base64
import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import urllib.parse
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from html import escape
from typing import Any

import requests

from render_activity import load_history, render_activity_svg

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "profile.json"
SVG_PATH = ROOT / "assets" / "terminal.svg"
README_PATH = ROOT / "README.md"
DAILY_STATS_PATH = ROOT / "stats" / "yesterday.json"
HISTORY_PATH = ROOT / "stats" / "history.json"
ACTIVITY_SVG_PATH = ROOT / "assets" / "activity.svg"

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


def load_daily_activity() -> dict[str, Any]:
    if not DAILY_STATS_PATH.exists():
        return {}
    try:
        data = json.loads(DAILY_STATS_PATH.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, json.JSONDecodeError):
        return {}


def git_credential_token() -> str | None:
    try:
        proc = subprocess.run(
            ["git", "credential", "fill"],
            input="protocol=https\nhost=github.com\n\n",
            text=True,
            capture_output=True,
            timeout=10,
            check=True,
        )
    except Exception:
        return None

    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            value = line.split("=", 1)[1].strip()
            return value or None
    return None


def token() -> str | None:
    return (
        os.getenv("PROFILE_STATS_TOKEN")
        or os.getenv("GH_TOKEN")
        or os.getenv("GITHUB_TOKEN")
        or git_credential_token()
    )


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


def age_parts(birth_iso: str) -> tuple[int, int, int, int, int]:
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
    remaining = now - cursor
    hours = remaining.seconds // 3600
    minutes = (remaining.seconds % 3600) // 60
    return years, months, remaining.days, hours, minutes


def age_seconds(birth_iso: str) -> int:
    birth = dt.datetime.fromisoformat(birth_iso)
    now = dt.datetime.now(birth.tzinfo) if birth.tzinfo else dt.datetime.now()
    return max(0, int((now - birth).total_seconds()))


def iso_utc(day: dt.date, end_of_day: bool = False) -> str:
    if end_of_day:
        return f"{day.isoformat()}T23:59:59Z"
    return f"{day.isoformat()}T00:00:00Z"


def fetch_latest_public_activity(username: str, auth_token: str | None) -> str | None:
    data = api_get(
        f"https://api.github.com/users/{urllib.parse.quote(username)}/events/public?per_page=1",
        auth_token,
    )
    if not isinstance(data, list) or not data:
        return None
    created_at = data[0].get("created_at")
    if not isinstance(created_at, str):
        return None
    try:
        event_time = dt.datetime.fromisoformat(created_at.replace("Z", "+00:00"))
    except ValueError:
        return created_at
    return event_time.strftime("%Y-%m-%d %H:%M UTC")


def fetch_contribution_activity(username: str, created_at: str | None, auth_token: str | None) -> dict[str, Any]:
    public_last_active = fetch_latest_public_activity(username, auth_token)
    if not auth_token:
        return {
            "active_days": None,
            "first_active": None,
            "last_active": public_last_active,
            "days_since_first": None,
            "total_contributions": None,
        }

    today = dt.datetime.now(dt.timezone.utc).date()
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
            "last_active": public_last_active,
            "days_since_first": None,
            "total_contributions": total_contributions or None,
        }

    first_active = min(active_dates)
    last_active = max(active_dates)
    if public_last_active and public_last_active[:10] >= last_active:
        last_active = public_last_active
    first_active_date = dt.date.fromisoformat(first_active)
    return {
        "active_days": len(active_dates),
        "first_active": first_active,
        "last_active": last_active,
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

    # Private repositories are included when the active credential can access them.
    if auth_token:
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
    clone_env = os.environ.copy()
    if auth_token and os.getenv("PROFILE_STATS_TOKEN"):
        basic = base64.b64encode(f"x-access-token:{auth_token}".encode()).decode()
        clone_env["GIT_CONFIG_COUNT"] = "1"
        clone_env["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
        clone_env["GIT_CONFIG_VALUE_0"] = f"AUTHORIZATION: basic {basic}"

    try:
        subprocess.run(
            ["git", "clone", "--depth", "1", "--quiet", clone_url, str(target)],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=120,
            env=clone_env,
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


def count_code_lines(
    repos: list[dict[str, Any]],
    auth_token: str | None,
    max_repos: int,
    max_workers: int = 4,
) -> dict[str, Any]:
    selected = repos[:max_repos]
    if not selected:
        return {"lines_code": None, "files_code": None, "repos_scanned": None}

    total_lines = 0
    total_files = 0
    scanned = 0
    workers = max(1, min(max_workers, len(selected)))

    with tempfile.TemporaryDirectory(prefix="profile-stats-") as tmp:
        tmp_path = pathlib.Path(tmp)

        def scan(repo: dict[str, Any]) -> tuple[int, int]:
            return count_repo_lines(repo, auth_token, tmp_path)

        with ThreadPoolExecutor(max_workers=workers) as pool:
            for lines, files in pool.map(scan, selected):
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
    stats_cfg = cfg.get("stats") or {}
    max_repos = int(stats_cfg.get("max_repos_to_clone") or 80)
    max_workers = int(stats_cfg.get("max_parallel_clones") or 4)
    line_stats = count_code_lines(
        repos,
        auth_token,
        max_repos=max_repos,
        max_workers=max_workers,
    )
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


def fmt_signed(value: Any) -> str:
    if value is None:
        return "sync pending"
    try:
        number = int(value)
        return f"{number:+,}"
    except Exception:
        return str(value)


def plural(value: int, unit: str) -> str:
    suffix = "" if value == 1 else "s"
    return f"{value} {unit}{suffix}"


def text(x: int, y: int, value: str, color: str = FG, size: float = 14, weight: str = "400") -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" xml:space="preserve">{escape(value)}</text>'


def tspan_line(
    x: int,
    y: int,
    label: str,
    value: str,
    value_x: int,
    value_color: str = BLUE,
    size: float = 13,
) -> str:
    label_txt = f"{label}:"
    char_width = size * 0.62
    dots_count = max(3, int((value_x - x) / char_width) - len(label_txt) - 1)
    dots = " " + "." * dots_count + " "
    return (
        f'<text x="{x}" y="{y}" font-size="{size}" xml:space="preserve">'
        f'<tspan fill="{ORANGE}" font-weight="700">{escape(label_txt)}</tspan>'
        f'<tspan fill="{DIM}">{escape(dots)}</tspan>'
        f'<tspan x="{value_x}" fill="{value_color}" font-weight="700">{escape(value)}</tspan>'
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
    terminal_url = f"https://raw.githubusercontent.com/{owner}/{name}/main/assets/terminal.svg?v={cache_bust}"
    activity_url = f"https://raw.githubusercontent.com/{owner}/{name}/main/assets/activity.svg?v={cache_bust}"
    README_PATH.write_text(
        (
            '<p align="center">\n'
            f'  <img src="{terminal_url}" alt="Moein Ghezelbash live developer telemetry dashboard" width="1120" />\n'
            '</p>\n\n'
            '<p align="center">\n'
            f'  <img src="{activity_url}" alt="Moein Ghezelbash development activity analytics" width="1120" />\n'
            '</p>\n'
        ),
        encoding="utf-8",
    )


def generate_svg() -> str:
    cfg = load_config()
    stats = collect_stats(cfg)
    daily = load_daily_activity()
    username = cfg["github_username"]

    years, months, days, hours, minutes = age_parts(cfg["birth_datetime"])
    uptime = f"{years}y {months}mo {days}d {hours}h {minutes}m"
    unix_time = str(age_seconds(cfg["birth_datetime"]))

    width, height = 1120, 720
    out: list[str] = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<title>Moein Ghezelbash developer telemetry</title>',
        '<desc>Live GitHub profile dashboard with runtime, codebase, and daily development activity metrics.</desc>',
        f'<rect width="{width}" height="{height}" rx="16" fill="{BG}"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace;dominant-baseline:hanging}</style>',
        f'<rect x="12" y="12" width="1096" height="696" rx="14" fill="{PANEL}" stroke="{BORDER}" stroke-width="1"/>',
        f'<circle cx="38" cy="43" r="5" fill="{RED}"/>',
        f'<circle cx="55" cy="43" r="5" fill="{YELLOW}"/>',
        f'<circle cx="72" cy="43" r="5" fill="{GREEN}"/>',
    ]

    out.append(text(96, 32, f"{username.lower()}@github", WHITE, 18, "700"))
    out.append(text(288, 37, "developer telemetry // live profile", MUTED, 12, "400"))
    out.append(text(913, 36, "● AUTO-SYNC", GREEN, 12, "700"))

    # Runtime / identity
    out += box(38, 80, 500, 204, "runtime // identity")
    y = 118
    runtime_lines = [
        ("Name", cfg["name"], BLUE),
        ("Role", cfg["role"], BLUE),
        ("OS", ", ".join(cfg["os"]), BLUE),
        ("Kernel", cfg.get("kernel", "XNU / NT / Linux"), BLUE),
        ("Uptime", uptime, GREEN),
        ("UnixTime", unix_time, CYAN),
    ]
    for label, value, color in runtime_lines:
        out.append(tspan_line(58, y, label, truncate(str(value), 39), value_x=188, value_color=color))
        y += 25

    # GitHub activity
    out += box(570, 80, 512, 204, "github // activity")
    y = 118
    activity_lines = [
        ("Created", fmt_value(stats.get("github_created")), BLUE),
        ("ActiveDays", fmt_int(stats.get("active_days")), GREEN),
        ("FirstActive", fmt_value(stats.get("first_active")), CYAN),
        ("LastActive", fmt_value(stats.get("last_active")), CYAN),
        ("Contributions", fmt_int(stats.get("total_contributions")), BLUE),
        ("Repos.Visible", fmt_int(stats.get("repo_count_scanned")), BLUE),
    ]
    for label, value, color in activity_lines:
        out.append(tspan_line(590, y, label, truncate(value, 34), value_x=780, value_color=color))
        y += 25

    # Toolchain
    out += box(38, 306, 500, 188, "toolchain // stack")
    y = 344
    tool_lines = [
        ("Editor", cfg["ide"], BLUE),
        ("Langs", ", ".join(cfg["programming_languages"]), BLUE),
        ("Tools", ", ".join(cfg["tools"]), BLUE),
        ("Focus", ", ".join(cfg["focus"]), BLUE),
        ("LinkedIn", "linkedin.com/in/moeinghezelbash", CYAN),
    ]
    for label, value, color in tool_lines:
        out.append(tspan_line(58, y, label, truncate(str(value), 39), value_x=188, value_color=color))
        y += 27

    # Codebase telemetry
    out += box(570, 306, 512, 188, "codebase // inventory")
    y = 344
    top_langs = stats.get("top_langs")
    code_lines = [
        ("Lines.Code", fmt_int(stats.get("lines_code")), GREEN),
        ("Files.Code", fmt_int(stats.get("files_code")), BLUE),
        ("Repos.Scanned", fmt_int(stats.get("repos_scanned")), BLUE),
        ("DaysOnline", fmt_int(stats.get("days_since_first")), GREEN),
        ("Top.Langs", ", ".join(top_langs) if top_langs else "sync pending", CYAN),
    ]
    for label, value, color in code_lines:
        out.append(tspan_line(590, y, label, truncate(value, 34), value_x=780, value_color=color))
        y += 27

    # Yesterday's aggregated development activity.
    out += box(38, 516, 1044, 142, "yesterday // development activity")
    daily_date = fmt_value(daily.get("date"))
    repos_checked = fmt_int(daily.get("repos_checked"))
    out.append(text(840, 534, f"{daily_date} // {repos_checked} repos checked", MUTED, 12, "700"))

    net_value = daily.get("net_lines")
    try:
        net_color = GREEN if int(net_value) > 0 else RED if int(net_value) < 0 else MUTED
    except Exception:
        net_color = MUTED

    metrics = [
        ("COMMITS", fmt_int(daily.get("commits")), BLUE),
        ("LINES +", fmt_signed(daily.get("lines_added")), GREEN),
        ("LINES -", fmt_signed(-int(daily.get("lines_deleted") or 0)), RED),
        ("NET", fmt_signed(net_value), net_color),
        ("ACTIVE REPOS", fmt_int(daily.get("active_repos")), CYAN),
    ]
    metric_x = [58, 260, 462, 664, 866]
    for x, (label, value, color) in zip(metric_x, metrics):
        out.append(f'<rect x="{x}" y="558" width="176" height="76" rx="8" fill="{BG}" stroke="{BORDER}" stroke-width="1"/>')
        out.append(text(x + 14, 573, label, MUTED, 11, "700"))
        out.append(text(x + 14, 596, value, color, 20, "700"))

    updated = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    out.append(text(58, height - 38, f"last sync: {updated}", MUTED, 11, "400"))
    out.append(text(752, height - 38, "GitHub API + local macOS telemetry", DIM, 11, "400"))
    out.append("</svg>")

    write_readme(dt.datetime.now(dt.timezone.utc).strftime("%Y%m%d%H%M%S"))
    return "\n".join(out)


if __name__ == "__main__":
    SVG_PATH.parent.mkdir(parents=True, exist_ok=True)
    SVG_PATH.write_text(generate_svg(), encoding="utf-8")
    history = load_history(HISTORY_PATH)
    ACTIVITY_SVG_PATH.write_text(render_activity_svg(history), encoding="utf-8")
    print(
        f"Generated {SVG_PATH.relative_to(ROOT)}, "
        f"{ACTIVITY_SVG_PATH.relative_to(ROOT)} and refreshed README.md"
    )
