#!/usr/bin/env python3
"""
Генератор анимированного баннера ZAMMER (1920x90).

Собирает самодостаточные SVG-файлы: геометрия логотипа и весь текст
переведены в кривые, шрифты на стороне сайта не нужны.

    python3 build.py

На выходе (рядом со скриптом):
    zammer-logo.svg          — чистый вектор логотипа
    zammer-banner.svg        — вариант A: АКЦИЯ слева, 37% справа  (основной)
    zammer-banner-b.svg      — вариант B: АКЦИЯ 37% единым блоком справа
    zammer-banner-light.svg  — вариант A на светлом фоне

Зависимости для пересборки: fonttools (pip install fonttools).
Сами SVG-файлы никаких зависимостей не имеют.
"""

import os
from string import Template

HERE = os.path.dirname(os.path.abspath(__file__))

# ── Геометрия логотипа ───────────────────────────────────────────────────────
# Контуры получены трассировкой исходного растра (src/trace_logo.py).
LOGO_D = open(os.path.join(HERE, "src", "logo_path.txt")).read().strip()


def path_bbox(d):
    xs, ys = [], []
    for seg in d.split("M"):
        for q in seg.rstrip("Z").split(" "):
            if not q:
                continue
            x, y = q.split(",")
            xs.append(float(x))
            ys.append(float(y))
    return min(xs), min(ys), max(xs), max(ys)


LOGO_X0, LOGO_Y0, _lx1, _ly1 = path_bbox(LOGO_D)
LOGO_SRC_W = _lx1 - LOGO_X0
LOGO_SRC_H = _ly1 - LOGO_Y0

# ── Холст и раскладка ────────────────────────────────────────────────────────
W, H = 1920, 90
CX = W / 2

LOGO_H = 66.0                       # высота логотипа в баннере
LOGO_W = LOGO_H * LOGO_SRC_W / LOGO_SRC_H
LOGO_Y = (H - LOGO_H) / 2

GAP = 44.0                          # отступы вокруг логотипа
AK_SIZE = 36.0                      # кегль «АКЦИЯ»
PC_SIZE = 60.0                      # кегль «37%»
PLATE_PAD_X = 17.0
PLATE_PAD_Y = 11.0
PLATE_R = 11.0

# ── Тайминг (секунды) ────────────────────────────────────────────────────────
LOOP = 6.0                          # длительность цикла
INTRO = 0.9                         # появление (проигрывается один раз)

WAVE_T0, WAVE_T1 = 0.30, 3.00       # окно прохода световой волны
WAVE_X0, WAVE_X1 = -340.0, 2260.0   # путь волны
SPEED = (WAVE_X1 - WAVE_X0) / (WAVE_T1 - WAVE_T0)

HOLD_END = 5.20                     # конец «зажжённого» состояния
DIM_END = 5.85                      # возврат к исходному состоянию


def t_at(x):
    """Момент времени, когда фронт волны проходит координату x."""
    return WAVE_T0 + (x - WAVE_X0) / SPEED


def p(t):
    """Секунды -> проценты кадра анимации."""
    return f"{max(0.0, min(100.0, t / LOOP * 100)):.4g}%"


def n(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return s if s not in ("", "-0") else "0"


# ── Текст в кривые ───────────────────────────────────────────────────────────
def text_path(text, size, tracking=0.0, xscale=1.0, x=0.0, y=0.0):
    """Возвращает (d, width). Базовая линия в y, начало в x."""
    from fontTools.ttLib import TTFont
    from fontTools.pens.svgPathPen import SVGPathPen
    from fontTools.pens.transformPen import TransformPen
    from fontTools.misc.transform import Transform

    font = TTFont("/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf")
    upm = font["head"].unitsPerEm
    cmap = font.getBestCmap()
    glyphs = font.getGlyphSet()
    hmtx = font["hmtx"]
    s = size / upm
    pen_x = x
    out = []
    for ch in text:
        gname = cmap[ord(ch)]
        pen = SVGPathPen(glyphs, ntos=lambda v: n(v))
        glyphs[gname].draw(TransformPen(pen, Transform(s * xscale, 0, 0, -s, pen_x, y)))
        out.append(pen.getCommands())
        pen_x += hmtx[gname][0] * s * xscale + tracking
    return "".join(out), (pen_x - tracking - x)


def text_width(text, size, tracking=0.0, xscale=1.0):
    return text_path(text, size, tracking, xscale)[1]


CAP_RATIO = 1409 / 2048            # высота прописных Liberation Sans


def transform_path(d, sx, sy, tx, ty):
    """Масштаб + сдвиг для пути, состоящего только из абсолютных M/L/Z."""
    out = []
    for seg in d.split("M"):
        if not seg.strip():
            continue
        pts = [q for q in seg.rstrip("Z").split(" ") if q]
        coords = []
        for q in pts:
            x, y = q.split(",")
            coords.append(f"{n(float(x) * sx + tx)},{n(float(y) * sy + ty)}")
        out.append("M" + " ".join(coords) + "Z")
    return "".join(out)


# ── Палитры ──────────────────────────────────────────────────────────────────
DARK = dict(
    bg0="#0a0c10", bg1="#161b22", bg2="#0a0c10",
    grid="#ffffff", grid_op=".05",
    metal0="#ffffff", metal1="#dde4ec", metal2="#98a3b2", metal3="#c6cfda",
    ext0="#525c69", ext1="#20252d",
    rim="#ffffff", rim_op=".28",
    halo="#8fd8ff",
    ak_off="#68727f", ak_on="#ffffff", ak_glow="#ffffff",
    plate_off="#151a21", plate_stroke_off="#2c333d",
    dig_off="#6b7683", dig_on="#2a1502",
    hot0="#ffd85e", hot1="#ff9d1c", hot2="#ff6a00",
    hot_stroke="#ffe6a8",
    trail="#ff9d1c",
    wave="#ffffff",
)

LIGHT = dict(
    DARK,
    bg0="#eef1f5", bg1="#ffffff", bg2="#e6eaf0",
    grid="#0b0f14", grid_op=".05",
    metal0="#2b3138", metal1="#11151a", metal2="#3c444e", metal3="#1a1f26",
    ext0="#b9c2cd", ext1="#8b96a4",
    rim="#ffffff", rim_op=".55",
    halo="#39a9ff",
    ak_off="#98a2b0", ak_on="#0d1319", ak_glow="#ff9d1c",
    plate_off="#dde3ea", plate_stroke_off="#c3ccd6",
    dig_off="#98a2b0", dig_on="#3a1c00",
    wave="#7cc4ff",
)


# ══════════════════════════════════════════════════════════════════════════════
def build(layout="A", theme=DARK, out="zammer-banner.svg"):
    ak_w = text_width("АКЦИЯ", AK_SIZE, tracking=6.0, xscale=0.95)
    pc_w = text_width("37%", PC_SIZE, tracking=1.0, xscale=0.95)
    ak_stroke, pc_stroke = 1.7, 2.6

    plate_w = pc_w + pc_stroke + PLATE_PAD_X * 2
    plate_h = PC_SIZE * CAP_RATIO + pc_stroke + PLATE_PAD_Y * 2
    plate_y = (H - plate_h) / 2

    if layout == "A":
        # АКЦИЯ — слева от логотипа, 37% — справа
        total = ak_w + GAP + LOGO_W + GAP + plate_w
        x0 = CX - total / 2
        ak_x = x0
        logo_x = ak_x + ak_w + GAP
        plate_x = logo_x + LOGO_W + GAP
    else:
        # АКЦИЯ 37% — единым блоком справа от логотипа
        inner = 16.0
        total = LOGO_W + GAP + ak_w + inner + plate_w
        x0 = CX - total / 2
        logo_x = x0
        ak_x = logo_x + LOGO_W + GAP
        plate_x = ak_x + ak_w + inner

    ak_base = H / 2 + AK_SIZE * CAP_RATIO / 2
    ak_d, _ = text_path("АКЦИЯ", AK_SIZE, 6.0, 0.95, ak_x, ak_base)
    pc_x = plate_x + PLATE_PAD_X + pc_stroke / 2
    pc_base = H / 2 + PC_SIZE * CAP_RATIO / 2
    pc_d, _ = text_path("37%", PC_SIZE, 1.0, 0.95, pc_x, pc_base)

    ls = LOGO_H / LOGO_SRC_H
    logo_d = transform_path(LOGO_D, ls, ls, logo_x - LOGO_X0 * ls, LOGO_Y - LOGO_Y0 * ls)

    # ── ключевые моменты прохода волны ──────────────────────────────────────
    t_ak = t_at(ak_x + ak_w * 0.55)
    t_logo_in = t_at(logo_x)
    t_logo_out = t_at(logo_x + LOGO_W)
    t_plate = t_at(plate_x + plate_w * 0.25)
    t_trail0 = t_at(0)
    t_trail1 = t_at(W)

    # ── 3D-выдавливание: копии логотипа со сдвигом вниз-вправо ──────────────
    depth = 6
    ext = []
    for i in range(depth, 0, -1):
        k = (i - 1) / max(1, depth - 1)          # 1 — дальняя грань, 0 — ближняя
        c0 = tuple(int(theme["ext1"][j:j + 2], 16) for j in (1, 3, 5))
        c1 = tuple(int(theme["ext0"][j:j + 2], 16) for j in (1, 3, 5))
        col = "#%02x%02x%02x" % tuple(int(c0[j] + (c1[j] - c0[j]) * (1 - k)) for j in range(3))
        ext.append(f'<use href="#zm-logo" x="{n(i * 0.95)}" y="{n(i * 0.95)}" fill="{col}"/>')
    ext = "\n      ".join(ext)

    # ── искры при поджиге ───────────────────────────────────────────────────
    spark_pts = [(-6, -4, -26, -16), (24, -9, 18, -22), (58, -7, 30, -19),
                 (-4, plate_h + 4, -24, 16), (30, plate_h + 6, 12, 22),
                 (plate_w * 0.72, -8, 26, -20), (plate_w + 4, 12, 26, -6),
                 (plate_w + 2, plate_h - 14, 24, 12)]
    sparks, spark_kf = [], []
    star = [(0, -4.6), (1.35, -1.35), (4.6, 0), (1.35, 1.35),
            (0, 4.6), (-1.35, 1.35), (-4.6, 0), (-1.35, -1.35)]
    for i, (sx, sy, dx, dy) in enumerate(spark_pts):
        # координаты вшиты в путь: атрибут transform конфликтовал бы с CSS-анимацией
        cx, cy = plate_x + sx, plate_y + sy
        d = "M" + " L".join(f"{n(cx + px)},{n(cy + py)}" for px, py in star) + "Z"
        sparks.append(f'<path class="zm-spark s{i}" d="{d}"/>')
        d0 = t_plate + 0.02 * i
        spark_kf.append(Template("""
    @keyframes zm-spark-$I {
      0%, $A { opacity: 0; transform: scale(.2); }
      $B { opacity: 1; transform: scale(1) translate(${DX0}px, ${DY0}px); }
      $C, 100% { opacity: 0; transform: scale(.55) translate(${DX}px, ${DY}px); }
    }""").substitute(I=i, A=p(d0), B=p(d0 + 0.16), C=p(d0 + 0.62),
                     DX0=n(dx * 0.45), DY0=n(dy * 0.45), DX=n(dx), DY=n(dy)))
    sparks = "\n      ".join(sparks)
    spark_css = "\n    ".join(
        f'.zm-spark.s{i} {{ animation: zm-spark-{i} {LOOP}s linear {INTRO}s infinite; }}'
        for i in range(len(spark_pts)))

    halo_cx = logo_x + LOGO_W / 2
    grid = "".join(
        f'<path d="M{n(x)},90 L{n(x + 34)},0" />'
        for x in list(range(-40, int(x0) - 90, 62)) +
                 list(range(int(x0 + total) + 60, W + 40, 62)))

    tpl = Template(open(os.path.join(HERE, "src", "banner.svg.tpl")).read())
    svg = tpl.substitute(
        W=W, H=H, LOOP=LOOP, INTRO=INTRO,
        LOGO_D=logo_d, AK_D=ak_d, PC_D=pc_d,
        AK_STROKE=n(ak_stroke), PC_STROKE=n(pc_stroke),
        EXT=ext, SPARKS=sparks, SPARK_KF="".join(spark_kf), SPARK_CSS=spark_css,
        GRID_PATHS=grid,
        PLATE_X=n(plate_x), PLATE_Y=n(plate_y), PLATE_W=n(plate_w),
        PLATE_H=n(plate_h), PLATE_R=n(PLATE_R),
        PLATE_CX=n(plate_x + plate_w / 2), PLATE_CY=n(plate_y + plate_h / 2),
        HALO_CX=n(halo_cx), LOGO_X=n(logo_x), LOGO_W=n(LOGO_W),
        LOGO_HALF=n(LOGO_W / 2 + 26),
        WAVE_X0=n(WAVE_X0), WAVE_X1=n(WAVE_X1),
        P_W0=p(WAVE_T0), P_W1=p(WAVE_T1), P_WFI=p(WAVE_T0 + 0.22), P_WFO=p(WAVE_T1 - 0.45),
        P_AK0=p(t_ak - 0.12), P_AK1=p(t_ak + 0.16),
        P_LG0=p(t_logo_in - 0.20), P_LG1=p((t_logo_in + t_logo_out) / 2),
        P_LG2=p(t_logo_out + 0.55),
        P_SPEC0=p(t_logo_in - 0.34), P_SPEC1=p(t_logo_out + 0.34),
        P_PL0=p(t_plate), P_PL1=p(t_plate + 0.16), P_PL2=p(t_plate + 0.34),
        P_TR0=p(t_trail0), P_TR1=p(t_trail1),
        P_HOLD=p(HOLD_END), P_DIM=p(DIM_END),
        **{k.upper(): v for k, v in theme.items()},
    )
    path = os.path.join(HERE, out)
    open(path, "w").write(svg)
    print(f"{out:26s} {len(svg):6d} B   "
          f"АКЦИЯ x={n(ak_x)} w={n(ak_w)} | лого x={n(logo_x)} w={n(LOGO_W)} | "
          f"плашка x={n(plate_x)} w={n(plate_w)}  "
          f"| поджиг t={t_plate:.2f}s")


def build_logo():
    d = transform_path(LOGO_D, 1, 1, -LOGO_X0, -LOGO_Y0)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {n(LOGO_SRC_W)} {n(LOGO_SRC_H)}"'
           f' width="{n(LOGO_SRC_W)}" height="{n(LOGO_SRC_H)}" role="img" aria-label="ZAMMER">'
           f'<title>ZAMMER</title>'
           f'<path fill="currentColor" fill-rule="evenodd" d="{d}"/></svg>\n')
    open(os.path.join(HERE, "zammer-logo.svg"), "w").write(svg)
    print(f'{"zammer-logo.svg":26s} {len(svg):6d} B')


if __name__ == "__main__":
    build_logo()
    build("A", DARK, "zammer-banner.svg")
    build("B", DARK, "zammer-banner-b.svg")
    build("A", LIGHT, "zammer-banner-light.svg")
