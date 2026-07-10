#!/usr/bin/env python3
from __future__ import annotations
import datetime as dt
import json, os, pathlib, urllib.parse
from collections import Counter
from html import escape
import requests

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONFIG_PATH = ROOT / "profile.json"
ASCII_PATH = ROOT / "assets" / "photo-ascii.txt"
SVG_PATH = ROOT / "assets" / "terminal.svg"
README_PATH = ROOT / "README.md"

BG = "#0d1117"; FG = "#d1d7e0"; WHITE = "#f0f6fc"; MUTED = "#8b949e"; DIM = "#5f6b7a"; ORANGE = "#ff9d57"; BLUE = "#b6d7ff"

def load_config() -> dict:
    cfg = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    if os.getenv("GH_USERNAME"): cfg["github_username"] = os.getenv("GH_USERNAME")
    return cfg

def age_parts(birth_iso: str) -> tuple[int,int,int]:
    birth = dt.datetime.fromisoformat(birth_iso); now = dt.datetime.now()
    years = now.year - birth.year
    if (now.month, now.day, now.time()) < (birth.month, birth.day, birth.time()): years -= 1
    cursor = birth.replace(year=birth.year + years); months = 0
    while True:
        nm = cursor.month + 1; ny = cursor.year
        if nm == 13: nm = 1; ny += 1
        try: nxt = cursor.replace(year=ny, month=nm)
        except ValueError: nxt = cursor.replace(year=ny, month=nm, day=28)
        if nxt <= now: months += 1; cursor = nxt
        else: break
    days = (now.date() - cursor.date()).days
    return years, months, days

def api_get(url: str, token: str | None):
    headers = {"Accept":"application/vnd.github+json","User-Agent":"github-profile-terminal-readme","X-GitHub-Api-Version":"2022-11-28"}
    if token: headers["Authorization"] = f"Bearer {token}"
    try:
        r = requests.get(url, headers=headers, timeout=20)
        return None if r.status_code >= 400 else r.json()
    except requests.RequestException:
        return None

def github_graphql(query: str, variables: dict, token: str | None):
    if not token: return None
    headers = {"Authorization": f"Bearer {token}", "User-Agent": "github-profile-terminal-readme"}
    try:
        r = requests.post("https://api.github.com/graphql", headers=headers, json={"query": query, "variables": variables}, timeout=20)
        return None if r.status_code >= 400 else r.json().get("data")
    except requests.RequestException:
        return None

def fetch_github_stats(username: str, token: str | None) -> dict:
    encoded = urllib.parse.quote(username)
    user = api_get(f"https://api.github.com/users/{encoded}", token) or {}
    repos = []; page = 1
    while page <= 10:
        data = api_get(f"https://api.github.com/users/{encoded}/repos?per_page=100&page={page}&sort=updated&type=owner", token)
        if not isinstance(data, list) or not data: break
        repos.extend(data)
        if len(data) < 100: break
        page += 1
    owned_non_forks = [r for r in repos if not r.get("fork")]
    stars = sum(int(r.get("stargazers_count", 0)) for r in repos)
    forks = sum(int(r.get("forks_count", 0)) for r in repos)
    lang_counter = Counter(r.get("language") for r in owned_non_forks if r.get("language"))
    top_langs = [lang for lang, _ in lang_counter.most_common(5)]
    now = dt.datetime.now(dt.UTC); year_ago = now - dt.timedelta(days=365)
    gql = github_graphql("""
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
    """, {"login": username, "from": year_ago.isoformat(timespec="seconds").replace("+00:00", "Z"), "to": now.isoformat(timespec="seconds").replace("+00:00", "Z")}, token)
    c = (((gql or {}).get("user") or {}).get("contributionsCollection") or {})
    total_contributions = (c.get("contributionCalendar") or {}).get("totalContributions")
    return {"repos": user.get("public_repos") or len(repos) or 0, "stars": stars, "forks": forks, "followers": user.get("followers", 0), "following": user.get("following", 0), "contribs_1y": total_contributions if total_contributions is not None else 0, "commits_1y": c.get("totalCommitContributions", 0), "prs_1y": c.get("totalPullRequestContributions", 0), "issues_1y": c.get("totalIssueContributions", 0), "top_langs": top_langs or ["—"]}

def text_line(x:int,y:int,text:str,color:str=FG,size:float=14,weight:str="400") -> str:
    return f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" font-weight="{weight}" xml:space="preserve">{escape(text)}</text>'

def section_title(x:int,y:int,title:str) -> str:
    left = "─ " + title + " "; right_len = max(10, 60 - len(left))
    return text_line(x, y, left + ("─" * right_len), WHITE, 14, "700")

def info_line(x:int,y:int,label:str,value:str,width:int=56) -> str:
    label_txt = f"{label}:"; dots_count = max(3, width - len(label_txt) - len(value)); dots = " " + "."*dots_count + " "
    return f'<text x="{x}" y="{y}" font-size="14" xml:space="preserve"><tspan fill="{ORANGE}" font-weight="700">{escape(label_txt)}</tspan><tspan fill="{DIM}">{escape(dots)}</tspan><tspan fill="{BLUE}" font-weight="700">{escape(value)}</tspan></text>'

def truncate(value:str,max_len:int=46) -> str:
    return value if len(value) <= max_len else value[:max_len-3] + "..."

def write_readme(cache_bust:str) -> None:
    repo = os.getenv("GITHUB_REPOSITORY", "iMoein/iMoein"); owner, name = repo.split("/", 1)
    image_url = f"https://raw.githubusercontent.com/{owner}/{name}/main/assets/terminal.svg?v={cache_bust}"
    README_PATH.write_text(f'<p align="center">\n  <img src="{image_url}" alt="Moein Ghezelbash GitHub profile terminal" width="1120" />\n</p>\n', encoding="utf-8")

def generate_svg() -> str:
    cfg = load_config(); username = cfg["github_username"]; token = os.getenv("GITHUB_TOKEN") or os.getenv("GH_TOKEN")
    stats = fetch_github_stats(username, token)
    years, months, days = age_parts(cfg["birth_datetime"]); uptime_value = f"{years} years, {months} months, {days} days"
    birth_dt = dt.datetime.fromisoformat(cfg["birth_datetime"])
    unix_time_value = str(int(birth_dt.timestamp()))
    ascii_lines = ASCII_PATH.read_text(encoding="utf-8").splitlines()
    width, height = 1180, 675
    lines = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">', f'<rect width="{width}" height="{height}" rx="14" fill="{BG}"/>', '<style>text{font-family:ui-monospace,SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace;dominant-baseline:hanging}</style>']
    x_ascii, y_ascii = 16, 20; font_size, line_h = 9.1, 11.3
    for i, line in enumerate(ascii_lines[:44]):
        color = "#f0f6fc" if i < 16 else "#d6dde6" if i < 30 else "#9aa7b7"
        lines.append(text_line(x_ascii, int(y_ascii + i * line_h), line, color, font_size))
    x, y = 560, 28
    lines.append(section_title(x, y, f"{username.lower()}@github")); y += 40
    info = [("Name", cfg["name"]), ("OS", ", ".join(cfg["os"])), ("Kernel", cfg.get("kernel", "XNU, NT, Linux")), ("Uptime", uptime_value), ("UnixTime", unix_time_value), ("Role", cfg["role"]), ("IDE", cfg["ide"]), ("Languages.Program", ", ".join(cfg["programming_languages"])), ("Languages.Tools", ", ".join(cfg["tools"])), ("Focus", ", ".join(cfg["focus"]))]
    for label, value in info:
        lines.append(info_line(x, y, label, truncate(value))); y += 28
    y += 14; lines.append(section_title(x, y, "Contact")); y += 36; lines.append(info_line(x, y, "LinkedIn", "linkedin.com/in/moeinghezelbash")); y += 46
    lines.append(section_title(x, y, "GitHub Stats")); y += 36
    gh_lines = [("Repos", f'{stats["repos"]} | Stars: {stats["stars"]} | Forks: {stats["forks"]}'), ("Followers", f'{stats["followers"]} | Following: {stats["following"]}'), ("Contribs.1y", f'{stats["contribs_1y"]} | Commits.1y: {stats["commits_1y"]}'), ("PRs/Issues.1y", f'{stats["prs_1y"]} PRs | {stats["issues_1y"]} Issues'), ("Top.Langs", ", ".join(stats["top_langs"]))]
    for label, value in gh_lines:
        lines.append(info_line(x, y, label, truncate(str(value)))); y += 28
    updated = dt.datetime.now(dt.UTC).strftime("%Y-%m-%d %H:%M UTC"); lines.append(text_line(x, height - 34, f"Last updated: {updated}", MUTED, 12)); lines.append("</svg>")
    write_readme(dt.datetime.now(dt.UTC).strftime("%Y%m%d%H%M%S"))
    return "\n".join(lines)

if __name__ == "__main__":
    SVG_PATH.write_text(generate_svg(), encoding="utf-8")
    print(f"Generated {SVG_PATH.relative_to(ROOT)} and refreshed README.md")
