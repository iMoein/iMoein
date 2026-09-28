#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
from concurrent.futures import ThreadPoolExecutor
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import requests

USERNAME = os.getenv("PROFILE_GITHUB_USERNAME", "iMoein")
PROFILE_REPO = os.getenv("PROFILE_REPOSITORY", "iMoein/iMoein")
API = "https://api.github.com"


def github_token() -> str:
    proc = subprocess.run(
        ["git", "credential", "fill"],
        input="protocol=https\nhost=github.com\n\n",
        text=True,
        capture_output=True,
        check=True,
        timeout=10,
    )
    for line in proc.stdout.splitlines():
        if line.startswith("password="):
            token = line.split("=", 1)[1].strip()
            if token:
                return token
    raise RuntimeError("GitHub credential was not found in the configured Git credential helper")


def make_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "imoein-daily-profile-telemetry",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    return session


def get_json(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> Any | None:
    response = session.get(url, params=params, timeout=30)
    if response.status_code in (404, 409, 422):
        return None
    response.raise_for_status()
    return response.json()


def owned_repositories(session: requests.Session) -> list[dict[str, Any]]:
    repos: list[dict[str, Any]] = []
    page = 1
    while True:
        data = get_json(
            session,
            f"{API}/user/repos",
            {
                "per_page": 100,
                "page": page,
                "visibility": "all",
                "affiliation": "owner",
                "sort": "full_name",
            },
        )
        if not isinstance(data, list) or not data:
            break

        for repo in data:
            owner = ((repo.get("owner") or {}).get("login") or "")
            full_name = repo.get("full_name") or ""
            if owner.lower() != USERNAME.lower():
                continue
            if full_name.lower() == PROFILE_REPO.lower():
                continue
            repos.append(repo)

        if len(data) < 100:
            break
        page += 1

    return repos


def local_day_window(day: dt.date) -> tuple[dt.date, dt.datetime, dt.datetime]:
    local_tz = dt.datetime.now().astimezone().tzinfo
    start = dt.datetime.combine(day, dt.time.min, tzinfo=local_tz)
    end = start + dt.timedelta(days=1)
    return day, start.astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc)


def repository_may_have_activity(
    repo: dict[str, Any],
    start: dt.datetime,
) -> bool:
    pushed_at = repo.get("pushed_at")
    if not isinstance(pushed_at, str) or not pushed_at:
        return True
    try:
        pushed = dt.datetime.fromisoformat(pushed_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    return pushed >= start


def repository_branches(
    session: requests.Session,
    full_name: str,
) -> list[str]:
    branches: list[str] = []
    page = 1
    while True:
        data = get_json(
            session,
            f"{API}/repos/{full_name}/branches",
            {"per_page": 100, "page": page},
        )
        if not isinstance(data, list) or not data:
            break
        for branch in data:
            name = branch.get("name")
            if isinstance(name, str) and name:
                branches.append(name)
        if len(data) < 100:
            break
        page += 1
    return branches
def repo_activity(
    session: requests.Session,
    full_name: str,
    start: dt.datetime,
    end: dt.datetime,
) -> tuple[int, int, int]:
    commits_by_sha: dict[str, dict[str, Any]] = {}
    for branch in repository_branches(session, full_name):
        page = 1
        while True:
            data = get_json(
                session,
                f"{API}/repos/{full_name}/commits",
                {
                    "sha": branch,
                    "author": USERNAME,
                    "since": start.isoformat().replace("+00:00", "Z"),
                    "until": end.isoformat().replace("+00:00", "Z"),
                    "per_page": 100,
                    "page": page,
                },
            )
            if not isinstance(data, list) or not data:
                break
            for commit in data:
                sha = commit.get("sha")
                if isinstance(sha, str) and sha:
                    commits_by_sha[sha] = commit
            if len(data) < 100:
                break
            page += 1

    additions = 0
    deletions = 0
    commit_count = 0
    for sha, commit in commits_by_sha.items():
        if len(commit.get("parents") or []) > 1:
            continue
        detail = get_json(session, f"{API}/repos/{full_name}/commits/{sha}")
        if not isinstance(detail, dict):
            continue
        stats = detail.get("stats") or {}
        additions += int(stats.get("additions") or 0)
        deletions += int(stats.get("deletions") or 0)
        commit_count += 1
    return commit_count, additions, deletions


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit(
            "usage: collect_github_yesterday.py /path/to/stats/yesterday.json [YYYY-MM-DD]"
        )

    output_path = Path(sys.argv[1]).expanduser().resolve()
    if len(sys.argv) == 3:
        day = dt.date.fromisoformat(sys.argv[2])
    else:
        day = dt.datetime.now().astimezone().date() - dt.timedelta(days=1)

    token = github_token()
    session = make_session(token)
    day, start, end = local_day_window(day)
    repos = owned_repositories(session)

    totals = {
        "date": day.isoformat(),
        "repos_checked": len(repos),
        "commits": 0,
        "lines_added": 0,
        "lines_deleted": 0,
        "net_lines": 0,
        "active_repos": 0,
    }

    def collect(repo: dict[str, Any]) -> tuple[int, int, int]:
        full_name = repo.get("full_name")
        if not full_name:
            return 0, 0, 0
        return repo_activity(make_session(token), full_name, start, end)

    candidates = [repo for repo in repos if repository_may_have_activity(repo, start)]
    workers = max(1, min(6, len(candidates)))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for commits, added, deleted in pool.map(collect, candidates):
            if commits:
                totals["active_repos"] += 1
            totals["commits"] += commits
            totals["lines_added"] += added
            totals["lines_deleted"] += deleted

    totals["net_lines"] = totals["lines_added"] - totals["lines_deleted"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(totals, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(json.dumps(totals, separators=(",", ":")))


if __name__ == "__main__":
    main()
