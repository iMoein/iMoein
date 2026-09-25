#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from typing import Any

from collect_github_yesterday import (
    API,
    USERNAME,
    get_json,
    github_token,
    make_session,
    owned_repositories,
)

GRAPHQL = "https://api.github.com/graphql"


def local_window(days: int) -> tuple[dt.date, dt.date, dt.datetime, dt.datetime]:
    local_tz = dt.datetime.now().astimezone().tzinfo
    end_day = dt.datetime.now().astimezone().date() - dt.timedelta(days=1)
    start_day = end_day - dt.timedelta(days=max(1, days) - 1)
    start = dt.datetime.combine(start_day, dt.time.min, tzinfo=local_tz)
    end = dt.datetime.combine(end_day + dt.timedelta(days=1), dt.time.min, tzinfo=local_tz)
    return start_day, end_day, start.astimezone(dt.timezone.utc), end.astimezone(dt.timezone.utc)
def empty_days(start: dt.date, end: dt.date, repos_checked: int) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        result[key] = {
            "date": key,
            "repos_checked": repos_checked,
            "commits": 0,
            "lines_added": 0,
            "lines_deleted": 0,
            "net_lines": 0,
            "active_repos": 0,
        }
        cursor += dt.timedelta(days=1)
    return result


def user_node_id(session) -> str:
    user = get_json(session, f"{API}/users/{USERNAME}")
    node_id = user.get("node_id") if isinstance(user, dict) else None
    if not node_id:
        raise RuntimeError("Unable to resolve GitHub user node id")
    return str(node_id)


def graphql_history_page(
    session,
    owner: str,
    name: str,
    author_id: str,
    since: dt.datetime,
    until: dt.datetime,
    cursor: str | None,
) -> dict[str, Any] | None:
    query = """
    query(
      $owner: String!,
      $name: String!,
      $author: ID!,
      $since: GitTimestamp!,
      $until: GitTimestamp!,
      $after: String
    ) {
      repository(owner: $owner, name: $name) {
        defaultBranchRef {
          target {
            ... on Commit {
              history(
                first: 100,
                after: $after,
                author: {id: $author},
                since: $since,
                until: $until
              ) {
                pageInfo { hasNextPage endCursor }
                nodes {
                  authoredDate
                  additions
                  deletions
                  parents(first: 2) { totalCount }
                }
              }
            }
          }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {
            "owner": owner,
            "name": name,
            "author": author_id,
            "since": since.isoformat().replace("+00:00", "Z"),
            "until": until.isoformat().replace("+00:00", "Z"),
            "after": cursor,
        },
    }
    response = session.post(GRAPHQL, json=payload, timeout=45)
    response.raise_for_status()
    data = response.json()
    if data.get("errors"):
        message = "; ".join(error.get("message", "GraphQL error") for error in data["errors"])
        raise RuntimeError(f"{owner}/{name}: {message}")

    repository = (data.get("data") or {}).get("repository") or {}
    branch = repository.get("defaultBranchRef") or {}
    target = branch.get("target") or {}
    history = target.get("history")
    return history if isinstance(history, dict) else None


def local_day(stamp: str) -> str | None:
    try:
        when = dt.datetime.fromisoformat(stamp.replace("Z", "+00:00"))
    except (AttributeError, ValueError):
        return None
    return when.astimezone().date().isoformat()


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: backfill_history.py OUTPUT [DAYS]")

    output = Path(sys.argv[1]).expanduser().resolve()
    days_count = int(sys.argv[2]) if len(sys.argv) == 3 else 365
    start_day, end_day, start, end = local_window(days_count)

    session = make_session(github_token())
    repos = owned_repositories(session)
    author_id = user_node_id(session)
    totals = empty_days(start_day, end_day, len(repos))
    active: dict[str, set[str]] = {key: set() for key in totals}
    commit_count = 0
    page_count = 0

    for index, repo in enumerate(repos, start=1):
        full_name = repo.get("full_name") or ""
        if "/" not in full_name:
            continue
        owner, name = full_name.split("/", 1)
        cursor: str | None = None
        repo_commits = 0

        while True:
            history = graphql_history_page(
                session, owner, name, author_id, start, end, cursor
            )
            if not history:
                break

            page_count += 1
            for node in history.get("nodes") or []:
                parents = ((node.get("parents") or {}).get("totalCount") or 0)
                if int(parents) > 1:
                    continue

                date_key = local_day(node.get("authoredDate"))
                if date_key not in totals:
                    continue

                additions = int(node.get("additions") or 0)
                deletions = int(node.get("deletions") or 0)
                totals[date_key]["commits"] += 1
                totals[date_key]["lines_added"] += additions
                totals[date_key]["lines_deleted"] += deletions
                active[date_key].add(full_name)
                repo_commits += 1
                commit_count += 1

            page_info = history.get("pageInfo") or {}
            if not page_info.get("hasNextPage"):
                break
            cursor = page_info.get("endCursor")
            if not cursor:
                break
        print(
            f"[{index}/{len(repos)}] history pages={page_count}, "
            f"repo commits={repo_commits}, total commits={commit_count}",
            file=sys.stderr,
        )

    ordered: list[dict[str, Any]] = []
    for key in sorted(totals):
        day = totals[key]
        day["net_lines"] = day["lines_added"] - day["lines_deleted"]
        day["active_repos"] = len(active[key])
        ordered.append(day)

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps({"days": ordered}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    active_days = sum(1 for day in ordered if day["commits"] > 0)
    print(
        f"history backfilled: {start_day}..{end_day}, {len(ordered)} days, "
        f"{active_days} active days, {commit_count} commits, {page_count} GraphQL pages"
    )


if __name__ == "__main__":
    main()
