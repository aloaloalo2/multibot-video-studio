#!/usr/bin/env python3
"""Cuts one generated 16:9 sheet into its four pictures (a 2 × 2 grid) — the studio's default way to make pictures.

Codex draws four pictures on one 16:9 sheet: cheaper and faster than four separate requests (user, 14 November 2026).
The sheet is cut along its real gaps near the middle (a light or transparent band), not at a fixed half, and each
picture is trimmed of the gap colour at its edges, so no white line stays on a side. A picture drawn in a vertical
cell keeps its own shape. Order: top left, top right, bottom left, bottom right.

  python3 tools/sheet_2x2.py SHEET.png OUT1.png OUT2.png OUT3.png OUT4.png
  python3 tools/sheet_2x2.py SHEET.png --out-dir "кадри" --names кадр_012,кадр_013,кадр_014,кадр_015

A name "-" skips that cell (a sheet with fewer than four needed pictures).
"""
from __future__ import annotations
import argparse
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def _gap_mask(rgba: np.ndarray, tolerance: int) -> np.ndarray:
    """Pixels that belong to the gap: transparent, or close to the sheet's border colour (usually white)."""
    rgb = rgba[..., :3].astype(np.int16)
    border = np.concatenate([rgb[0], rgb[-1], rgb[:, 0], rgb[:, -1]])
    colour = np.median(border, axis=0)
    near = np.abs(rgb - colour).max(axis=2) <= tolerance
    return near | (rgba[..., 3] < 20)


def _split(profile: np.ndarray, size: int) -> tuple[int, int]:
    """The gap band closest to the middle: (first, last) index of a run of gap lines; a plain half when there is none."""
    lo, hi = int(size * .3), int(size * .7)
    best = None
    i = lo
    while i < hi:
        if profile[i] >= .97:
            j = i
            while j + 1 < size and profile[j + 1] >= .97:
                j += 1
            k = i
            while k - 1 >= 0 and profile[k - 1] >= .97:
                k -= 1
            centre = (k + j) / 2
            if best is None or abs(centre - size / 2) < abs((best[0] + best[1]) / 2 - size / 2):
                best = (k, j)
            i = j + 1
        else:
            i += 1
    return best or (size // 2, size // 2 - 1)


def _trim(gap: np.ndarray) -> tuple[int, int, int, int] | None:
    """The box of a cell without the gap colour around it (a line is trimmed when 97% of it is gap)."""
    rows = np.where(gap.mean(axis=1) < .97)[0]
    cols = np.where(gap.mean(axis=0) < .97)[0]
    if not len(rows) or not len(cols):
        return None
    return int(cols[0]), int(rows[0]), int(cols[-1]) + 1, int(rows[-1]) + 1


def cut(sheet: Path, tolerance: int = 18) -> list[Image.Image]:
    image = Image.open(sheet).convert("RGBA")
    rgba = np.array(image)
    gap = _gap_mask(rgba, tolerance)
    h, w = gap.shape
    x0, x1 = _split(gap.mean(axis=0), w)
    y0, y1 = _split(gap.mean(axis=1), h)
    cells = [(0, 0, x0, y0), (x1 + 1, 0, w, y0), (0, y1 + 1, x0, h), (x1 + 1, y1 + 1, w, h)]
    out = []
    for left, top, right, bottom in cells:
        box = _trim(gap[top:bottom, left:right])
        if box is None:
            raise SystemExit(f"{sheet.name}: an empty cell at {left},{top}")
        a, b, c, d = box
        piece = image.crop((left + a, top + b, left + c, top + d))
        if piece.width < w * .1 or piece.height < h * .2:
            raise SystemExit(f"{sheet.name}: a cell came out {piece.width}×{piece.height}; is this a 2×2 sheet?")
        out.append(piece)
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("sheet")
    ap.add_argument("outs", nargs="*", help="four output files in reading order ('-' skips a cell)")
    ap.add_argument("--out-dir")
    ap.add_argument("--names", help="comma-separated names for --out-dir, .png added")
    ap.add_argument("--tolerance", type=int, default=18, help="how far from the gap colour a pixel still counts as gap")
    args = ap.parse_args()
    outs = list(args.outs)
    if args.names:
        folder = Path(args.out_dir or Path(args.sheet).parent)
        outs = [n.strip() if n.strip() == "-" else str(folder / (n.strip().removesuffix(".png") + ".png"))
                for n in args.names.split(",")]
    if len(outs) != 4:
        sys.exit("give four outputs (use '-' to skip a cell)")
    pieces = cut(Path(args.sheet), args.tolerance)
    for piece, out in zip(pieces, outs):
        if out == "-":
            continue
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        has_alpha = piece.getchannel("A").getextrema()[0] < 255
        (piece if has_alpha else piece.convert("RGB")).save(out)
        print(f"{out}  {piece.width}×{piece.height}")


if __name__ == "__main__":
    main()
