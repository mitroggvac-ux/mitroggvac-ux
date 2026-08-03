#!/usr/bin/env python3
"""
Трассировка растрового логотипа ZAMMER в векторный контур.

    pip install pillow numpy scikit-image
    python3 trace_logo.py IMG_0919.jpeg

Пишет рядом logo_path.txt — путь SVG (только абсолютные M/L/Z), который
подхватывает build.py. Нужен только при замене исходника логотипа.
"""

import sys
import os
from PIL import Image, ImageFilter
import numpy as np
from skimage import measure

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "logo.jpeg")

im = Image.open(SRC).convert("L")
a = np.asarray(im).astype(float)
h, w = a.shape

# у присланного JPEG первые 4 строки и последний столбец — артефакт рамки
core = a[4:h, 0:w - 1]

# апсемпл x3 со сглаживанием: даёт субпиксельную точность на скруглениях R и A
S = 3
big = (Image.fromarray(core.astype(np.uint8))
       .resize(((w - 1) * S, (h - 4) * S), Image.LANCZOS)
       .filter(ImageFilter.GaussianBlur(0.8)))
b = np.asarray(big).astype(float)

# логотип обрезан впритык к краям — паддинг нужен, чтобы контуры замкнулись
pad = 6
bp = np.pad(b, pad, constant_values=255)

paths = []
for c in measure.find_contours(bp, 140):
    c = measure.approximate_polygon(c, tolerance=0.9)
    if len(c) < 4:
        continue
    pts = [((x - pad) / S, (y - pad) / S) for y, x in c]
    area = abs(sum(pts[i][0] * pts[(i + 1) % len(pts)][1] -
                   pts[(i + 1) % len(pts)][0] * pts[i][1]
                   for i in range(len(pts)))) / 2
    if area < 30:                       # отсев мусора от компрессии
        continue
    paths.append((area, pts))

paths.sort(key=lambda t: -t[0])


def fmt(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("-0", "") else "0"


d = "".join("M" + " ".join(f"{fmt(x)},{fmt(y)}" for x, y in pts) + "Z"
            for _, pts in paths)

open(os.path.join(HERE, "logo_path.txt"), "w").write(d)

# фактический бокс контуров — именно его ждёт build.py в LOGO_SRC_W/LOGO_SRC_H
xs = [x for _, pts in paths for x, _ in pts]
ys = [y for _, pts in paths for _, y in pts]
print(f"контуров: {len(paths)}  символов в пути: {len(d)}")
print(f"бокс контуров: {max(xs) - min(xs):.2f} x {max(ys) - min(ys):.2f}"
      f"  (сверьте LOGO_SRC_W / LOGO_SRC_H в build.py)")
