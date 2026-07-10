#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import shutil
import subprocess
import tempfile
import time
import urllib.parse
from collections import Counter
from html import escape
from typing import Any

import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "profile.json"
ASCII_PATH = ROOT / "assets" / "photo-ascii.txt"
SVG_PATH = ROOT / "assets" / "terminal.svg"
README_PATH = ROOT / "README.md"
METRICS_PATH = ROOT / "assets" / "code-metrics.json"

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
YELLOW = "#fde68a"

CODE_EXTS = {
    ".astro", ".awk", ".bash", ".bat", ".c", ".cc", ".cfg", ".clj", ".cmake", ".conf",
    ".cpp", ".cs", ".css", ".csv", ".dart", ".dockerfile", ".env", ".erl", ".ex", ".exs",
    ".go", ".gradle", ".graphql", ".groovy", ".h", ".hpp", ".htm", ".html", ".ini", ".java",
    ".js", ".jsx", ".json", ".kt", ".kts", ".less", ".lua", ".m", ".md", ".mdx", ".php",
    ".pl", ".plist", ".prisma", ".properties", ".py", ".r", ".rb", ".rs", ".sass", ".scala",
    ".scss", ".sh", ".sql", ".svelte", ".swift", ".toml", ".ts", ".tsx", ".txt", ".vue",
    ".xml", ".yaml", ".yml", ".zsh",
}
SPECIAL_FILENAMES = {
    "dockerfile", "makefile", "rakefile", "gemfile", "podfile", "jenkinsfile", "procfile",
    "compose.yaml", "compose.yml", "docker-compose.yaml", "docker-compose.yml",
}
SKIP_PARTS = {
    ".git", ".next", ".nuxt", ".turbo", ".vercel", ".cache", "node_modules", "vendor", "dist",
    "build", "coverage", "target", ".idea", ".vscode", "__pycache__", ".pytest_cache", ".mypy_cache",
}
MAX_FILE_BYTES = int(os.getenv("PROFILE_MAX_FILE_BYTES", "2000000"))
MAX_REPOS = int(os.getenv("PROFILE_MAX_REPOS", "80"))
CLONE_TIMEOUT = int(os.getenv("PROFILE_CLONE_TIMEOUT", "120"))


def load_config() -> dict[str, Any]:
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
        nm, ny = cursor.month + 1, cursor.year
        if nm == 13:
            nm, ny = 1, ny + 1
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


def auth_headers(token: str | None) -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "github-profile-terminal-readme",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def api_get(url: str, token: str | None = None, allow_202: bool = False):
    try:
        response = requests.get(url, headers=auth_headers(token), timeout=30)
        if allow_202 and response.status_code == 202:
            return {"_status": 202}
        if response.status_code >= 400:
            return None
        return response.json()
    except requests.RequestException:
        return None


def github_graphql(query: str, variables: dict[str, Any], token: str | None):
    if not token:
        return None
    try:
        response = requests.post(
            "https://api.github.com/graphql",
            headers={"Authorization": f"Bearer {token}", "User-Agent": "github-profile-terminal-readme"},
            json={"query": query, "variables": variables},
            timeout=30,
        )
        if response.status_code >= 400:
            return None
        return response.json().get("data")
    except requests.RequestException:
        return None


def stats_token() -> str | None:
    # Do not use the workflow GITHUB_TOKEN for cross-repository public stats.
    # It is scoped to the profile repository and can return 404/0 for other repos.
    return os.getenv("PROFILE_STATS_TOKEN") or os.getenv("GH_STATS_TOKEN")


def fetch_repos(username: str, token: str | None) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    include_forks = os.getenv("PROFILE_INCLUDE_FORKS", "0") == "1"
    include_archived = os.getenv("PROFILE_INCLUDE_ARCHIVED", "0") == "1"

    while page <= 10 and len(repos) < MAX_REPOS:
        encoded = urllib.parse.quote(username)
        url = f"https://api.github.com/users/{encoded}/repos?per_page=100&page={page}&sort=updated&type=owner"
        data = api_get(url, token)
        if not isinstance(data, list) or not data:
            break
        for repo in data:
            if not include_forks and repo.get("fork"):
                continue
            if not include_archived and repo.get("archived"):
                continue
            if repo.get("disabled"):
                continue
            repos.append(repo)
            if len(repos) >= MAX_REPOS:
                break
        if len(data) < 100:
            break
        page += 1
    return repos


def safe_clone_url(repo: dict[str, Any], token: str | None) -> str:
    owner = (repo.get("owner") or {}).get("login") or ""
    name = repo.get("name") or ""
    if repo.get("private") and token:
        return f"https://x-access-token:{urllib.parse.quote(token)}@github.com/{owner}/{name}.git"
    return f"https://github.com/{owner}/{name}.git"


def run_command(args: list[str], cwd: pathlib.Path | None = None, timeout: int = 60) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            args,
            cwd=str(cwd) if cwd else None,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=timeout,
            check=False,
        )
    except Exception:
        return None


def should_count_file(relative_path: str) -> bool:
    p = pathlib.PurePosixPath(relative_path.replace(os.sep, "/"))
    lower_parts = {part.lower() for part in p.parts}
    if lower_parts & SKIP_PARTS:
        return False
    name = p.name.lower()
    if name in SPECIAL_FILENAMES:
        return True
    if p.suffix.lower() in CODE_EXTS:
        return True
    return False


def count_file_lines(path: pathlib.Path) -> int:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            return 0
        data = path.read_bytes()
    except OSError:
        return 0
    if not data or b"\0" in data[:8192]:
        return 0
    return data.count(b"\n") + (0 if data.endswith(b"\n") else 1)


def count_repo_lines(repo_dir: pathlib.Path) -> tuple[int, Counter[str]]:
    result = run_command(["git", "ls-files", "-z"], cwd=repo_dir, timeout=30)
    if result is None or result.returncode != 0:
        return 0, Counter()
    total = 0
    lang_counter: Counter[str] = Counter()
    files = [item for item in result.stdout.split("\0") if item]
    for rel in files:
        if not should_count_file(rel):
            continue
        path = repo_dir / rel
        lines = count_file_lines(path)
        if lines <= 0:
            continue
        total += lines
        suffix = pathlib.PurePosixPath(rel.replace(os.sep, "/")).suffix.lower().lstrip(".") or pathlib.PurePosixPath(rel).name.lower()
        lang_counter[suffix] += lines
    return total, lang_counter


def fetch_code_frequency(owner: str, name: str, token: str | None) -> tuple[int | None, int | None]:
    url = f"https://api.github.com/repos/{urllib.parse.quote(owner)}/{urllib.parse.quote(name)}/stats/code_frequency"
    for attempt in range(8):
        data = api_get(url, token, allow_202=True)
        if isinstance(data, dict) and data.get("_status") == 202:
            time.sleep(1.5 + attempt * 0.75)
            continue
        if isinstance(data, list):
            added = 0
            deleted = 0
            for row in data:
                if isinstance(row, list) and len(row) >= 3:
                    added += int(row[1] or 0)
                    deleted += abs(int(row[2] or 0))
            return added, deleted
        break
    return None, None


def cache_metrics(metrics: dict[str, Any]) -> None:
    METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
    METRICS_PATH.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")


def load_cached_metrics() -> dict[str, Any] | None:
    if not METRICS_PATH.exists():
        return None
    try:
        data = json.loads(METRICS_PATH.read_text(encoding="utf-8"))
        if int(data.get("lines_total") or 0) > 0:
            return data
    except Exception:
        return None
    return None


def calculate_code_metrics(username: str) -> dict[str, Any]:
    if os.getenv("SKIP_GITHUB_FETCH") == "1":
        return load_cached_metrics() or {}

    token = stats_token()
    repos = fetch_repos(username, token)
    if not repos:
        return load_cached_metrics() or {}

    total_lines = 0
    total_added = 0
    total_deleted = 0
    counted_repos = 0
    movement_repos = 0
    lang_counter: Counter[str] = Counter()

    with tempfile.TemporaryDirectory(prefix="profile-lines-") as tmp:
        tmp_path = pathlib.Path(tmp)
        for repo in repos:
            owner = (repo.get("owner") or {}).get("login") or username
            name = repo.get("name") or "repo"
            dest = tmp_path / f"{owner}-{name}"
            clone = run_command(
                ["git", "clone", "--depth", "1", "--single-branch", "--quiet", safe_clone_url(repo, token), str(dest)],
                timeout=CLONE_TIMEOUT,
            )
            if clone is None or clone.returncode != 0 or not dest.exists():
                continue

            lines, langs = count_repo_lines(dest)
            if lines > 0:
                counted_repos += 1
                total_lines += lines
                lang_counter.update(langs)

            added, deleted = fetch_code_frequency(owner, name, token)
            if added is not None and deleted is not None:
                movement_repos += 1
                total_added += added
                total_deleted += deleted

            shutil.rmtree(dest, ignore_errors=True)

    metrics: dict[str, Any] = {
        "generated_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "repo_count_seen": len(repos),
        "repo_count_lines": counted_repos,
        "repo_count_movement": movement_repos,
        "lines_total": total_lines if counted_repos else None,
        "lines_added": total_added if movement_repos else None,
        "lines_deleted": total_deleted if movement_repos else None,
        "top_langs": [item[0] for item in lang_counter.most_common(5)] or [],
    }

    if metrics.get("lines_total"):
        cache_metrics(metrics)
        return metrics
    return load_cached_metrics() or metrics


def fmt_int(value: Any, default: str = "sync pending") -> str:
    if value is None or value == "":
        return default
    try:
        return f"{int(value):,}"
    except Exception:
        return str(value)


def fmt_signed(value: Any, sign: str) -> str:
    if value is None or value == "":
        return "sync pending"
    try:
        return f"{sign}{int(value):,}"
    except Exception:
        return str(value)


def text_line(x: int, y: int, text: str, color: str = FG, size: float = 14, weight: str = "400") -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" xml:space="preserve">{escape(text)}</text>'


def section_title(x: int, y: int, title: str) -> str:
    left = "─ " + title + " "
    right_len = max(10, 58 - len(left))
    return text_line(x, y, left + ("─" * right_len), WHITE, 14, "700")


def info_line(x: int, y: int, label: str, value: str, width: int = 58, value_color: str = BLUE) -> str:
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


def truncate(value: str, max_len: int = 48) -> str:
    return value if len(value) <= max_len else value[: max_len - 3] + "..."


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
    metrics = calculate_code_metrics(username)

    years, months, days = age_parts(cfg["birth_datetime"])
    uptime_value = f"{years} years, {months} months, {days} days"
    unix_time_value = str(int(dt.datetime.now(dt.UTC).timestamp()))
    ascii_lines = ASCII_PATH.read_text(encoding="utf-8").splitlines()

    width, height = 1180, 700
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        f'<rect width="{width}" height="{height}" rx="14" fill="{BG}"/>',
        f'<rect x="12" y="12" width="1156" height="676" rx="12" fill="{PANEL}" stroke="{BORDER}" stroke-width="1"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace;dominant-baseline:hanging}</style>',
    ]

    x_ascii, y_ascii = 18, 22
    font_size, line_h = 9.0, 11.15
    for i, line in enumerate(ascii_lines[:46]):
        color = "#f8fafc" if i < 16 else "#e2e8f0" if i < 30 else "#94a3b8"
        lines.append(text_line(x_ascii, int(y_ascii + i * line_h), line, color, font_size))

    x, y = 585, 48
    lines.append(section_title(x, y, f"{username.lower()}@server"))
    y += 40

    system_lines = [
        ("Name", cfg["name"], BLUE),
        ("OS", ", ".join(cfg["os"]), BLUE),
        ("Kernel", cfg.get("kernel", "Darwin/XNU, Windows NT, Linux"), BLUE),
        ("Uptime", uptime_value, GREEN),
        ("UnixTime", unix_time_value, GREEN),
        ("Role", cfg["role"], BLUE),
        ("Editor", cfg.get("editor") or cfg.get("ide") or "VSCode", BLUE),
        ("Langs", ", ".join(cfg.get("programming_languages", [])), BLUE),
        ("Toolchain", ", ".join(cfg.get("toolchain", cfg.get("tools", []))), BLUE),
        ("Services", ", ".join(cfg.get("services", cfg.get("focus", []))), BLUE),
    ]
    for label, value, color in system_lines:
        lines.append(info_line(x, y, label, truncate(str(value)), value_color=color))
        y += 27

    y += 16
    lines.append(section_title(x, y, "network"))
    y += 36
    lines.append(info_line(x, y, "LinkedIn", "linkedin.com/in/moeinghezelbash", value_color=BLUE))
    y += 48

    added = metrics.get("lines_added")
    deleted = metrics.get("lines_deleted")
    net = None if added is None or deleted is None else int(added) - int(deleted)
    top_langs = metrics.get("top_langs") or []
    source_value = "git ls-files / default branches" if metrics.get("lines_total") else "waiting for next action run"

    lines.append(section_title(x, y, "telemetry"))
    y += 36
    telemetry = [
        ("Lines.Code", fmt_int(metrics.get("lines_total")), GREEN),
        ("Lines.Added", fmt_signed(added, "+"), GREEN),
        ("Lines.Deleted", fmt_signed(deleted, "-"), RED),
        ("Lines.Net", "sync pending" if net is None else f"{net:+,}", GREEN if (net or 0) >= 0 else RED),
        ("Line.Source", source_value, YELLOW),
        ("Top.Langs", ", ".join(top_langs) if top_langs else "sync pending", BLUE),
    ]
    for label, value, color in telemetry:
        lines.append(info_line(x, y, label, truncate(str(value)), value_color=color))
        y += 27

    updated = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC")
    lines.append(text_line(x, height - 36, f"Last updated: {updated}", MUTED, 12))
    lines.append("</svg>")

    write_readme(str(int(dt.datetime.now(dt.UTC).timestamp())))
    return "\n".join(lines)


if __name__ == "__main__":
    SVG_PATH.write_text(generate_svg(), encoding="utf-8")
    print(f"Generated {SVG_PATH.relative_to(ROOT)} and refreshed README.md")
