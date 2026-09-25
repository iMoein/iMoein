#!/usr/bin/env python3
from __future__ import annotations

from html import escape
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
CYAN = "#67e8f9"
PURPLE = "#c4b5fd"
YELLOW = "#fde68a"

PALETTE = [
    "#67e8f9", "#86efac", "#bfdbfe", "#c4b5fd", "#fde68a",
    "#fdba74", "#f9a8d4", "#a7f3d0", "#93c5fd", "#d8b4fe",
]


def txt(x: float, y: float, value: str, color: str = WHITE, size: float = 12,
        weight: str = "400", anchor: str = "start") -> str:
    return (
        f'<text x="{x}" y="{y}" fill="{color}" font-size="{size}" '
        f'font-weight="{weight}" text-anchor="{anchor}" '
        f'xml:space="preserve">{escape(str(value))}</text>'
    )


def panel(x: int, y: int, w: int, h: int, title: str) -> list[str]:
    return [
        f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="10" '
        f'fill="{PANEL_2}" stroke="{BORDER}" stroke-width="1"/>',
        txt(x + 18, y + 15, title, WHITE, 14, "700"),
    ]


def compact(value: int) -> str:
    n = abs(int(value))
    if n >= 1_000_000:
        return f"{value / 1_000_000:.2f}M".rstrip("0").rstrip(".")
    if n >= 1_000:
        return f"{value / 1_000:.1f}K".rstrip("0").rstrip(".")
    return f"{value:,}"


def render_summary(stack: dict[str, Any]) -> list[str]:
    cards = [
        ("CODE LINES", compact(int(stack.get("total_lines") or 0)), GREEN),
        ("CODE FILES", f'{int(stack.get("total_files") or 0):,}', BLUE),
        ("LANGUAGES", str(len(stack.get("languages") or [])), CYAN),
        ("TECHNOLOGIES", str(len(stack.get("technologies") or [])), PURPLE),
        ("REPOS SCANNED", str(int(stack.get("repos_scanned") or 0)), YELLOW),
    ]
    out: list[str] = []
    for x, (label, value, color) in zip([38, 248, 458, 668, 878], cards):
        out.append(
            f'<rect x="{x}" y="78" width="184" height="70" rx="9" '
            f'fill="{PANEL_2}" stroke="{BORDER}" stroke-width="1"/>'
        )
        out.append(txt(x + 14, 92, label, MUTED, 10.5, "700"))
        out.append(txt(x + 14, 113, value, color, 19, "700"))
    return out


def language_color(index: int) -> str:
    return PALETTE[index % len(PALETTE)]


def render_language_panel(
    languages: list[dict[str, Any]], panel_h: int
) -> list[str]:
    x, y, w = 38, 168, 690
    out = panel(x, y, w, panel_h, "language distribution // physical lines")
    out.append(txt(x + 18, y + 42, "LANGUAGE", MUTED, 9.5, "700"))
    out.append(txt(x + 432, y + 42, "%", MUTED, 9.5, "700", "end"))
    out.append(txt(x + 540, y + 42, "LINES", MUTED, 9.5, "700", "end"))
    out.append(txt(x + 655, y + 42, "FILES", MUTED, 9.5, "700", "end"))
    row_y = y + 66
    bar_x = x + 150
    bar_w = 235
    for index, item in enumerate(languages):
        name = str(item.get("name") or "Unknown")
        percent = float(item.get("percent") or 0)
        lines = int(item.get("lines") or 0)
        files = int(item.get("files") or 0)
        color = language_color(index)

        out.append(txt(x + 18, row_y + 4, name[:18], WHITE, 11.5, "700"))
        out.append(
            f'<rect x="{bar_x}" y="{row_y + 4}" width="{bar_w}" height="13" '
            f'rx="6.5" fill="{BG}"/>'
        )
        fill = (percent / 100) * bar_w
        out.append(
            f'<rect x="{bar_x}" y="{row_y + 4}" width="{max(2, fill):.1f}" '
            f'height="13" rx="6.5" fill="{color}"/>'
        )
        out.append(txt(x + 432, row_y + 3, f"{percent:.2f}%", color, 10.5, "700", "end"))
        out.append(txt(x + 540, row_y + 3, f"{lines:,}", BLUE, 10.5, "700", "end"))
        out.append(txt(x + 655, row_y + 3, f"{files:,}", MUTED, 10.5, "700", "end"))
        row_y += 28

    # Full composition strip.
    strip_y = y + panel_h - 44
    strip_x = x + 18
    strip_w = w - 36
    cursor = strip_x
    out.append(txt(strip_x, strip_y - 17, "code composition", MUTED, 9.5, "700"))
    for index, item in enumerate(languages):
        percent = float(item.get("percent") or 0)
        width = strip_w * percent / 100
        if width <= 0:
            continue
        out.append(
            f'<rect x="{cursor:.1f}" y="{strip_y}" width="{max(1, width):.1f}" '
            f'height="14" fill="{language_color(index)}"/>'
        )
        cursor += width
    return out


def render_technology_panel(
    technologies: list[dict[str, Any]], panel_h: int
) -> list[str]:
    x, y, w = 750, 168, 332
    out = panel(x, y, w, panel_h, "technology footprint // repositories")
    row_y = y + 52

    for index, item in enumerate(technologies):
        name = str(item.get("name") or "Unknown")
        category = str(item.get("category") or "tool")
        repos = int(item.get("repos") or 0)
        percent = float(item.get("percent") or 0)
        color = language_color(index + 2)

        out.append(
            f'<rect x="{x + 16}" y="{row_y}" width="{w - 32}" height="42" '
            f'rx="7" fill="{BG}" stroke="{BORDER}" stroke-width="1"/>'
        )
        out.append(txt(x + 28, row_y + 8, name[:24], WHITE, 11, "700"))
        out.append(txt(x + 28, row_y + 23, category.upper(), DIM, 8.5, "700"))
        out.append(txt(x + w - 28, row_y + 8, f"{repos} repos", color, 10.5, "700", "end"))
        out.append(txt(x + w - 28, row_y + 23, f"{percent:.1f}%", MUTED, 9, "700", "end"))
        row_y += 50

    return out


def render_stack_svg(stack: dict[str, Any]) -> str:
    languages = list(stack.get("languages") or [])
    technologies = list(stack.get("technologies") or [])

    language_h = 128 + len(languages) * 28
    technology_h = 76 + len(technologies) * 50
    panel_h = max(400, language_h, technology_h)
    height = 168 + panel_h + 66
    width = 1120

    out = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        "<title>Moein Ghezelbash engineering stack analytics</title>",
        "<desc>Aggregate language lines, files, percentages, and technology usage across GitHub repositories.</desc>",
        f'<rect width="{width}" height="{height}" rx="16" fill="{BG}"/>',
        '<style>text{font-family:ui-monospace,SFMono-Regular,Consolas,Liberation Mono,Menlo,monospace;dominant-baseline:hanging}</style>',
        f'<rect x="12" y="12" width="1096" height="{height - 24}" rx="14" '
        f'fill="{PANEL}" stroke="{BORDER}" stroke-width="1"/>',
        f'<circle cx="38" cy="43" r="5" fill="#fca5a5"/>',
        f'<circle cx="55" cy="43" r="5" fill="#fde68a"/>',
        f'<circle cx="72" cy="43" r="5" fill="{GREEN}"/>',
        txt(96, 32, "stack@github", WHITE, 18, "700"),
        txt(244, 37, "engineering stack // aggregate repository analytics", MUTED, 12),
        txt(890, 36, "● AUTO-SYNC", GREEN, 11.5, "700"),
    ]

    out.extend(render_summary(stack))
    out.extend(render_language_panel(languages, panel_h))
    out.extend(render_technology_panel(technologies, panel_h))
    out.append(
        txt(
            58,
            height - 36,
            "language % = physical lines share · technology % = scanned repositories using it",
            DIM,
            10,
        )
    )
    out.append(
        txt(
            856,
            height - 36,
            f'{int(stack.get("repos_scanned") or 0)} repositories aggregated',
            MUTED,
            10,
            "700",
        )
    )
    out.append("</svg>")
    return "\n".join(out)
