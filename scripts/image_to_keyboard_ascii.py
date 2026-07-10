#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ImageEnhance, ImageFilter


def make_keyboard_ascii(image_path: Path, cols: int = 82) -> str:
    img = Image.open(image_path).convert("RGB")
    w, h = img.size
    arr = np.asarray(img)

    mask_np = None
    try:
        import cv2

        mask = np.zeros((h, w), np.uint8)
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        rect = (max(1, int(w * 0.035)), max(1, int(h * 0.05)), int(w * 0.93), int(h * 0.92))
        cv2.grabCut(arr, mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)
        mask_np = np.where((mask == 2) | (mask == 0), 0, 1).astype("uint8")
        kernel = np.ones((7, 7), np.uint8)
        mask_np = cv2.morphologyEx(mask_np, cv2.MORPH_CLOSE, kernel)
        mask_np = cv2.morphologyEx(mask_np, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
    except Exception:
        arr_i = arr.astype(np.int16)
        edge = np.concatenate([arr_i[:, :30, :], arr_i[:, -30:, :]], axis=1)
        bg_row = np.median(edge, axis=1)
        dist = np.linalg.norm(arr_i - bg_row[:, None, :], axis=2)
        lum = 0.299 * arr_i[:, :, 0] + 0.587 * arr_i[:, :, 1] + 0.114 * arr_i[:, :, 2]
        mask_np = ((dist > 25) | (lum < 90)).astype("uint8")

    ys, xs = np.where(mask_np > 0)
    if len(xs) == 0:
        left, top, right, bottom = 0, 0, w, h
    else:
        pad = 20
        left, right = max(int(xs.min()) - pad, 0), min(int(xs.max()) + pad, w)
        top, bottom = max(int(ys.min()) - pad, 0), min(int(ys.max()) + pad, h)

    crop = img.crop((left, top, right, bottom))
    mask_crop = Image.fromarray(mask_np[top:bottom, left:right] * 255)

    rows = max(24, int(cols * crop.height / crop.width * 0.46))

    gray = ImageOps.grayscale(crop)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.85)

    resized = gray.resize((cols, rows), Image.Resampling.LANCZOS)
    mask_resized = mask_crop.filter(ImageFilter.MaxFilter(5)).resize((cols, rows), Image.Resampling.LANCZOS)
    edge = resized.filter(ImageFilter.FIND_EDGES)

    chars = " .`^\",:;Il!i~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"

    lines: list[str] = []
    for y in range(rows):
        line = ""
        for x in range(cols):
            m = mask_resized.getpixel((x, y))
            if m < 40:
                line += " "
                continue

            v = resized.getpixel((x, y))
            e = edge.getpixel((x, y))
            idx = int((255 - v) / 255 * (len(chars) - 1))

            if idx < 2:
                idx = 2

            if e > 50 and idx < len(chars) - 8:
                idx += 6

            line += chars[max(0, min(len(chars) - 1, idx))]

        lines.append(line.rstrip())

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Convert a profile photo to keyboard-only ASCII art.")
    parser.add_argument("image", type=Path, help="Source image path")
    parser.add_argument("output", type=Path, help="Output txt path")
    parser.add_argument("--cols", type=int, default=82, help="ASCII width in characters")
    args = parser.parse_args()

    ascii_art = make_keyboard_ascii(args.image, cols=args.cols)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(ascii_art, encoding="utf-8")
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
