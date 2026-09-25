#!/usr/bin/env python3
from __future__ import annotations

import datetime as dt
import json
import math
from html import escape
from pathlib import Path
from typing import Any

BG = "#08111f"
PANEL = "#0f172a"
PANEL_2 = "#111c2f"
BORDER = "#233044"
WHITE = "#f8fafc"
MUTED = "#94a3b8"
DIM = "#475569"
BLUE = "#bfdbfe"
GREEN = "#86efac"
RED = "#fca5a5"
CYAN = "#67e8f9"

HEAT = ["#182231", "#123b2a", "#166534", "#22c55e", "#86efac"]


def svg_text(x: float, y: float, value: str, color: str = WHITE, size: float = 12, weight: str = "400") -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
        f'font-weight="{weight}" xml:space="preserve">{escape(value)}</text>'
    )
def panel(x: int, y: int, w: int, h: int, title: str) -> list[str]:
    return [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
        f'fill="{PANEL_2}" stroke="{BORDER}" stroke-width="1"/>',
        svg_text(x + 18, y + 15, title, WHITE, 14, "700"),
    ]


def load_history(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    days = data.get("days") if isinstance(data, dict) else None
    if not isinstance(days, list):
        return []
    clean = [
        day for day in days
        if isinstance(day, dict) and isinstance(day.get("date"), str)
    ]
    return sorted(clean, key=lambda day: day["date"])


def int_value(day: dict[str, Any], key: str) -> int:
    try:
        return int(day.get(key) or 0)
    except (TypeError, ValueError):
        return 0


def compact(value: int) -> str:
    sign = "-" if value < 0 else ""
    n = abs(value)
    if n >= 1_000_000:
        return f"{sign}{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{sign}{n / 1_000:.1f}K"
    return f"{value:,}"


def signed(value: int) -> str:
    return f"{value:+,}"


def activity_score(day: dict[str, Any]) -> int:
    return int_value(day, "lines_added") + int_value(day, "lines_deleted")


def date_map(history: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {day["date"]: day for day in history}


def calendar_days(history: list[dict[str, Any]], count: int, end: dt.date) -> list[dict[str, Any]]:
    mapped = date_map(history)
    start = end - dt.timedelta(days=count - 1)
    result: list[dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        result.append(mapped.get(key, {"date": key}))
        cursor += dt.timedelta(days=1)
    return result


def heat_thresholds(days: list[dict[str, Any]]) -> list[int]:
    scores = sorted(activity_score(day) for day in days if activity_score(day) > 0)
    if not scores:
        return [1, 2, 3, 4]
    def q(frac: float) -> int:
        index = min(len(scores) - 1, max(0, math.ceil(len(scores) * frac) - 1))
        return max(1, scores[index])
    return [q(0.25), q(0.50), q(0.75), q(0.90)]
def heat_color(score: int, thresholds: list[int]) -> str:
    if score <= 0:
        return HEAT[0]
    for index, threshold in enumerate(thresholds, start=1):
        if score <= threshold:
            return HEAT[min(index, len(HEAT) - 1)]
    return HEAT[-1]


def render_summary(history: list[dict[str, Any]], end: dt.date) -> list[str]:
    recent = calendar_days(history, 365, end)
    commits = sum(int_value(day, "commits") for day in recent)
    added = sum(int_value(day, "lines_added") for day in recent)
    deleted = sum(int_value(day, "lines_deleted") for day in recent)
    code_days = sum(1 for day in recent if activity_score(day) > 0)
    net = added - deleted

    cards = [
        ("CODE DAYS", f"{code_days:,}", CYAN),
        ("COMMITS", f"{commits:,}", BLUE),
        ("LINES +", signed(added), GREEN),
        ("LINES -", f"-{deleted:,}", RED),
        ("NET", signed(net), GREEN if net >= 0 else RED),
    ]

    out: list[str] = []
    xs = [38, 248, 458, 668, 878]
    for x, (label, value, color) in zip(xs, cards):
        out.append(
            f'<rect x="{x}" y="78" width="184" height="70" rx="9" '
            f'fill="{PANEL_2}" stroke="{BORDER}" stroke-width="1"/>'
        )
        out.append(svg_text(x + 14, 92, label, MUTED, 10.5, "700"))
        out.append(svg_text(x + 14, 113, value, color, 19, "700"))
    return out
def render_bar_chart(history: list[dict[str, Any]], end: dt.date) -> list[str]:
    out = panel(38, 168, 1044, 222, "14d // code change velocity")
    days = calendar_days(history, 14, end)

    chart_x = 68
    chart_y = 208
    chart_w = 984
    chart_h = 142
    zero_y = chart_y + 74
    upper = 62
    lower = 52

    max_lines = max(
        [1]
        + [int_value(day, "lines_added") for day in days]
        + [int_value(day, "lines_deleted") for day in days]
    )
    max_commits = max([1] + [int_value(day, "commits") for day in days])

    group_w = chart_w / 14
    bar_w = 12
    commit_points: list[tuple[float, float]] = []

    out.append(
        f'<line x1="{chart_x}" y1="{zero_y}" x2="{chart_x + chart_w}" y2="{zero_y}" '
        f'stroke="{DIM}" stroke-width="1"/>'
    )
    out.append(svg_text(chart_x, chart_y - 2, f"+{compact(max_lines)}", DIM, 9))
    out.append(svg_text(chart_x, zero_y + lower - 2, f"-{compact(max_lines)}", DIM, 9))

    for index, day in enumerate(days):
        center = chart_x + group_w * index + group_w / 2
        added = int_value(day, "lines_added")
        deleted = int_value(day, "lines_deleted")
        commits = int_value(day, "commits")

        add_h = (added / max_lines) * upper if max_lines else 0
        del_h = (deleted / max_lines) * lower if max_lines else 0

        out.append(
            f'<rect x="{center - bar_w - 1:.1f}" y="{zero_y - add_h:.1f}" '
            f'width="{bar_w}" height="{max(1, add_h):.1f}" rx="2.5" fill="{GREEN}" opacity="0.95"/>'
        )
        out.append(
            f'<rect x="{center + 1:.1f}" y="{zero_y:.1f}" width="{bar_w}" '
            f'height="{max(1, del_h):.1f}" rx="2.5" fill="{RED}" opacity="0.9"/>'
        )

        commit_y = chart_y + 8 + (1 - commits / max_commits) * 44
        commit_points.append((center, commit_y))

        date_label = day["date"][5:]
        out.append(svg_text(center - 16, zero_y + 60, date_label, MUTED, 8.5))

    if commit_points:
        points = " ".join(f"{x:.1f},{y:.1f}" for x, y in commit_points)
        out.append(
            f'<polyline points="{points}" fill="none" stroke="{BLUE}" stroke-width="2" '
            f'stroke-linecap="round" stroke-linejoin="round" opacity="0.9"/>'
        )
        for x, y in commit_points:
            out.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="3" fill="{BLUE}"/>')

    out.append(svg_text(790, 185, "■ Added", GREEN, 10.5, "700"))
    out.append(svg_text(866, 185, "■ Deleted", RED, 10.5, "700"))
    out.append(svg_text(950, 185, "● Commits", BLUE, 10.5, "700"))
    return out
def render_heatmap(history: list[dict[str, Any]], end: dt.date) -> list[str]:
    out = panel(38, 410, 1044, 188, "365d // activity heatmap · changed lines intensity")

    mapped = date_map(history)
    start = end - dt.timedelta(days=364)
    # Align the first column to Sunday like GitHub's contribution grid.
    start -= dt.timedelta(days=(start.weekday() + 1) % 7)

    cursor = start
    all_days: list[dict[str, Any]] = []
    while cursor <= end:
        all_days.append(mapped.get(cursor.isoformat(), {"date": cursor.isoformat()}))
        cursor += dt.timedelta(days=1)

    thresholds = heat_thresholds(all_days)
    grid_x = 94
    grid_y = 455
    cell = 12
    gap = 4
    step = cell + gap

    month_marked: set[tuple[int, int]] = set()
    cursor = start
    while cursor <= end:
        week = (cursor - start).days // 7
        month_key = (cursor.year, cursor.month)
        if cursor.day <= 7 and month_key not in month_marked:
            out.append(svg_text(grid_x + week * step, 435, cursor.strftime("%b"), MUTED, 10.5))
            month_marked.add(month_key)
        cursor += dt.timedelta(days=1)

    out.append(svg_text(52, grid_y + 17, "Mon", MUTED, 9.5))
    out.append(svg_text(52, grid_y + 49, "Wed", MUTED, 9.5))
    out.append(svg_text(52, grid_y + 81, "Fri", MUTED, 9.5))

    cursor = start
    while cursor <= end:
        key = cursor.isoformat()
        day = mapped.get(key, {"date": key})
        week = (cursor - start).days // 7
        weekday = (cursor.weekday() + 1) % 7  # Sunday=0
        x = grid_x + week * step
        y = grid_y + weekday * step
        color = heat_color(activity_score(day), thresholds)

        out.append(
            f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="2.5" '
            f'fill="{color}" stroke="{BG}" stroke-width="0.5">'
            f'<title>{key}: {activity_score(day):,} changed lines, '
            f'{int_value(day, "commits")} commits</title></rect>'
        )
        cursor += dt.timedelta(days=1)

    legend_y = 574
    out.append(svg_text(858, legend_y, "Less", MUTED, 9.5))
    for index, color in enumerate(HEAT):
        out.append(
            f'<rect x="{893 + index * 16}" y="{legend_y - 2}" width="11" height="11" '
            f'rx="2" fill="{color}"/>'
        )
    out.append(svg_text(978, legend_y, "More", MUTED, 9.5))
    return out


def render_activity_svg(history: list[dict[str, Any]]) -> str:
    if history:
        end = dt.date.fromisoformat(history[-1]["date"])
    else:
        end = dt.datetime.now().astimezone().date() - dt.timedelta(days=1)

    width, height = 1120, 640
    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        "<title>Moein Ghezelbash development activity analytics</title>",
        "<desc>Daily added and deleted lines, commits, and a yearly activity heatmap.</desc>",
        f'<rect width="{width}" height="{height}" rx="16" fill="{BG}"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace;dominant-baseline:hanging}</style>',
        f'<rect x="12" y="12" width="1096" height="616" rx="14" '
        f'fill="{PANEL}" stroke="{BORDER}" stroke-width="1"/>',
        f'<circle cx="38" cy="43" r="5" fill="{RED}"/>',
        f'<circle cx="55" cy="43" r="5" fill="#fde68a"/>',
        f'<circle cx="72" cy="43" r="5" fill="{GREEN}"/>',
        svg_text(96, 32, "activity@github", WHITE, 18, "700"),
        svg_text(275, 37, "developer analytics // rolling telemetry", MUTED, 12),
        svg_text(894, 36, f"through {end.isoformat()}", CYAN, 11.5, "700"),
    ]

    out.extend(render_summary(history, end))
    out.extend(render_bar_chart(history, end))
    out.extend(render_heatmap(history, end))

    out.append(svg_text(58, 610, "bars: daily additions/deletions · line: commits · heatmap: total changed lines", DIM, 10))
    out.append(svg_text(884, 610, f"{len(history)} stored days", MUTED, 10, "700"))
    out.append("</svg>")
    return "\n".join(out)
