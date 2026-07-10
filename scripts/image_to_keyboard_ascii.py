#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import numpy as np
from PIL import Image, ImageOps, ImageEnhance, ImageFilter

try:
    import cv2
except Exception:
    cv2 = None

RAMP = " .:-=+*#%@"


def foreground_mask(arr: np.ndarray) -> np.ndarray:
    h, w, _ = arr.shape
    if cv2 is not None:
        mask = np.zeros((h, w), np.uint8)
        bgd = np.zeros((1, 65), np.float64)
        fgd = np.zeros((1, 65), np.float64)
        rect = (20, 10, max(1, w - 40), max(1, h - 20))
        cv2.grabCut(arr, mask, rect, bgd, fgd, 7, cv2.GC_INIT_WITH_RECT)
        mask_np = np.where((mask == 2) | (mask == 0), 0, 1).astype("uint8")
        mask_np = cv2.morphologyEx(mask_np, cv2.MORPH_CLOSE, np.ones((9, 9), np.uint8))
        return mask_np

    arr_i = arr.astype(np.int16)
    edge = np.concatenate([arr_i[:, :30, :], arr_i[:, -30:, :]], axis=1)
    bg_row = np.median(edge, axis=1)
    dist = np.linalg.norm(arr_i - bg_row[:, None, :], axis=2)
    lum = 0.299 * arr_i[:, :, 0] + 0.587 * arr_i[:, :, 1] + 0.114 * arr_i[:, :, 2]
    return ((dist > 24) | (lum < 95)).astype("uint8")


def make_keyboard_ascii(image_path: Path, cols: int = 68) -> str:
    img = Image.open(image_path).convert("RGB")
    w, h = img.size

    # Stable manual portrait crop: head + shoulders, avoids noisy full-body silhouette.
    left = int(w * 0.07)
    top = int(h * 0.03)
    right = int(w * 0.95)
    bottom = int(h * 0.82)
    crop = img.crop((left, top, right, bottom))

    arr = np.asarray(crop)
    mask_np = foreground_mask(arr)
    mask_img = Image.fromarray(mask_np * 255).filter(ImageFilter.MaxFilter(3))

    cw, ch = crop.size
    rows = max(30, int(cols * ch / cw * 0.47))

    gray = ImageOps.grayscale(crop)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.75)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1, percent=150, threshold=3))
    edges = gray.filter(ImageFilter.FIND_EDGES)

    g = gray.resize((cols, rows), Image.Resampling.LANCZOS)
    e = edges.resize((cols, rows), Image.Resampling.LANCZOS)
    m = mask_img.resize((cols, rows), Image.Resampling.LANCZOS)

    lines: list[str] = []
    for y in range(rows):
        line = ""
        for x in range(cols):
            if m.getpixel((x, y)) < 35:
                line += " "
                continue
            v = g.getpixel((x, y))
            ed = e.getpixel((x, y))
            idx = int((255 - v) / 255 * (len(RAMP) - 1))
            idx = max(1, idx)
            if ed > 55 and idx < len(RAMP) - 1:
                idx += 1
            line += RAMP[idx]
        lines.append(line.rstrip())

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Create a clean keyboard-only ASCII portrait.")
    parser.add_argument("image", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--cols", type=int, default=68)
    args = parser.parse_args()
    ascii_art = make_keyboard_ascii(args.image, cols=args.cols)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(ascii_art, encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
