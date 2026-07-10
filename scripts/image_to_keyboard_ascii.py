#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageOps, ImageEnhance, ImageFilter

CHAR_RAMP = " .'`^\",:;Il!i~+_-?][}{1)(|\\/tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"


def _foreground_mask(arr: np.ndarray) -> np.ndarray:
    h, w, _ = arr.shape
    try:
        import cv2
        mask = np.zeros((h, w), np.uint8)
        bgd_model = np.zeros((1, 65), np.float64)
        fgd_model = np.zeros((1, 65), np.float64)
        rect = (max(1, int(w * 0.06)), max(1, int(h * 0.04)), int(w * 0.88), int(h * 0.92))
        cv2.grabCut(arr, mask, rect, bgd_model, fgd_model, 5, cv2.GC_INIT_WITH_RECT)
        mask_np = np.where((mask == 2) | (mask == 0), 0, 1).astype("uint8")
        mask_np = cv2.morphologyEx(mask_np, cv2.MORPH_CLOSE, np.ones((7, 7), np.uint8))
        mask_np = cv2.morphologyEx(mask_np, cv2.MORPH_OPEN, np.ones((3, 3), np.uint8))
        return mask_np
    except Exception:
        arr_i = arr.astype(np.int16)
        edge = np.concatenate([arr_i[:, :30, :], arr_i[:, -30:, :]], axis=1)
        bg_row = np.median(edge, axis=1)
        dist = np.linalg.norm(arr_i - bg_row[:, None, :], axis=2)
        lum = 0.299 * arr_i[:, :, 0] + 0.587 * arr_i[:, :, 1] + 0.114 * arr_i[:, :, 2]
        return ((dist > 24) | (lum < 95)).astype("uint8")


def make_keyboard_ascii(image_path: Path, cols: int = 68) -> str:
    img = Image.open(image_path).convert("RGB")
    arr = np.asarray(img)
    h, w, _ = arr.shape
    mask_np = _foreground_mask(arr)

    ys, xs = np.where(mask_np > 0)
    if len(xs) == 0:
        left, top, right, bottom = 0, 0, w, h
    else:
        pad_x, pad_y = 24, 18
        left, right = max(int(xs.min()) - pad_x, 0), min(int(xs.max()) + pad_x, w)
        top, bottom = max(int(ys.min()) - pad_y, 0), min(int(ys.max()) + pad_y, h)

    crop = img.crop((left, top, right, bottom))
    mask_crop = Image.fromarray(mask_np[top:bottom, left:right] * 255)

    cw, ch = crop.size
    top2 = int(ch * 0.01)
    bottom2 = int(ch * 0.82)
    crop = crop.crop((0, top2, cw, bottom2))
    mask_crop = mask_crop.crop((0, top2, cw, bottom2))

    rows = max(26, int(cols * crop.height / crop.width * 0.50))

    gray = ImageOps.grayscale(crop)
    gray = ImageOps.autocontrast(gray, cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.75)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1, percent=170, threshold=3))
    edge = gray.filter(ImageFilter.FIND_EDGES)

    resized = gray.resize((cols, rows), Image.Resampling.LANCZOS)
    edge_resized = edge.resize((cols, rows), Image.Resampling.LANCZOS)
    mask_resized = mask_crop.filter(ImageFilter.MaxFilter(5)).resize((cols, rows), Image.Resampling.LANCZOS)

    lines = []
    for y in range(rows):
        row_chars = []
        for x in range(cols):
            if mask_resized.getpixel((x, y)) < 40:
                row_chars.append(" ")
                continue
            v = resized.getpixel((x, y))
            e = edge_resized.getpixel((x, y))
            idx = int((255 - v) / 255 * (len(CHAR_RAMP) - 1))
            idx = max(1, idx)
            if e > 60:
                idx = min(len(CHAR_RAMP) - 1, idx + 4)
            elif e > 35:
                idx = min(len(CHAR_RAMP) - 1, idx + 2)
            row_chars.append(CHAR_RAMP[idx])
        lines.append("".join(row_chars).rstrip())

    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser()
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
