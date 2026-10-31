"""Split a generated sheet of transparent props (usually 3 x 2) into separate PNGs.

The sheet is cut along its real transparent gaps, not a fixed grid: the alpha mask is closed a little so one object
stays one piece, the six largest pieces become the props, sorted by row then column, and each is cropped to its own
bounding box (plus a margin that never crosses into a neighbour). Writes assets/<name>.png for each given name,
assets/index.json (all props of the project) and a crops log next to the sheet.

  python3 tools/split_sheet.py --project projects/<slug> --sheet assets/src/A.png --names shower,tub,sink,mirror,towel,cup
"""
import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--project", required=True)
    ap.add_argument("--sheet", required=True)
    ap.add_argument("--names", required=True, help="comma-separated names in reading order")
    ap.add_argument("--min-alpha", type=int, default=150, help="alpha that counts as the object when finding the pieces")
    ap.add_argument("--close", type=int, default=15, help="closing size that keeps one object in one piece")
    ap.add_argument("--clean", type=int, default=110, help="alpha below this is set to 0 in each prop (removes soft halos)")
    args = ap.parse_args()
    project = Path(args.project).resolve()
    sheet = (project / args.sheet).resolve() if not Path(args.sheet).is_absolute() else Path(args.sheet)
    names = [n.strip() for n in args.names.split(",") if n.strip()]
    im = Image.open(sheet).convert("RGBA")
    a = np.array(im)[:, :, 3]
    if (a < 250).mean() < 0.2:
        raise SystemExit(f"{sheet.name}: no real transparency (alpha is mostly opaque)")
    mask = a > args.min_alpha
    closed = ndimage.binary_closing(mask, structure=np.ones((args.close, args.close)))
    labels, n = ndimage.label(closed)
    sizes = ndimage.sum(np.ones_like(labels), labels, range(1, n + 1))
    keep = [i + 1 for i in np.argsort(sizes)[::-1][: len(names)]]
    boxes = []
    for lab in keep:
        ys, xs = np.where(labels == lab)
        boxes.append([int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1, lab])
    if len(boxes) < len(names):
        raise SystemExit(f"{sheet.name}: found {len(boxes)} objects, expected {len(names)}")
    # reading order: group into rows by vertical centre, then left to right
    boxes.sort(key=lambda b: (b[1] + b[3]) / 2)
    rows, cur = [], [boxes[0]]
    for b in boxes[1:]:
        if (b[1] + b[3]) / 2 - (cur[-1][1] + cur[-1][3]) / 2 > im.height * 0.18:
            rows.append(cur); cur = [b]
        else:
            cur.append(b)
    rows.append(cur)
    ordered = [b for row in rows for b in sorted(row, key=lambda b: b[0])]
    out_dir = project / "assets"
    out_dir.mkdir(exist_ok=True)
    log = []
    for name, (x0, y0, x1, y1, lab) in zip(names, ordered):
        m = 12
        X0, Y0, X1, Y1 = max(0, x0 - m), max(0, y0 - m), min(im.width, x1 + m), min(im.height, y1 + m)
        crop = np.array(im)[Y0:Y1, X0:X1].copy()
        own = labels[Y0:Y1, X0:X1] == lab
        crop[:, :, 3] = np.where(ndimage.binary_dilation(own, iterations=6), crop[:, :, 3], 0)   # drop any neighbour's pixels
        crop[:, :, 3] = np.where(crop[:, :, 3] >= args.clean, crop[:, :, 3], 0)                    # drop the generator's soft glow
        ys, xs = np.where(crop[:, :, 3] > 0)
        if len(xs):
            crop = crop[max(0, ys.min() - 4):ys.max() + 5, max(0, xs.min() - 4):xs.max() + 5]
        path = out_dir / f"{name}.png"
        Image.fromarray(crop).save(path)
        log.append({"name": name, "box": [X0, Y0, X1, Y1], "size": [X1 - X0, Y1 - Y0], "sha256": hashlib.sha256(path.read_bytes()).hexdigest()})
        print(f"{name:14s} {X1 - X0}x{Y1 - Y0} from {X0},{Y0}")
    (sheet.parent / (sheet.stem + ".crops.json")).write_text(json.dumps({"sheet": sheet.name, "props": log}, indent=1))
    index = sorted(p.stem for p in out_dir.glob("*.png"))
    (out_dir / "index.json").write_text(json.dumps(index))
    # Every new prop also goes to the shared library (tools/library.py) so later videos can reuse it.
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import library
    library.add_project(project)


if __name__ == "__main__":
    main()
