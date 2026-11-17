#!/usr/bin/env python3
"""Build the "Pastel Paws" cursor theme for KDE Plasma 6.

Produces, under build/PastelPaws/:
  cursors_scalable/<name>/  SVG cursors + metadata.json (used by KWin, Plasma >= 6.2)
  cursors/<name>            XCursor fallback for XWayland/GTK/Electron apps
  index.theme

Every design is drawn on a 32x32 canvas with nominal size 24, like Breeze,
so at the default 24 px setting the paws are about as big as the Breeze arrow.

Usage: build.py [--install]   (--install copies to ~/.icons/PastelPaws: the Plasma cursor KCM does not scan ~/.local/share/icons)
Needs: python3, ImageMagick with the librsvg delegate (only for the XCursor files).
"""
import json
import math
import os
import shutil
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
THEME = "PastelPaws"
OUT_DIR = os.path.join(HERE, "build", THEME)
NOMINAL = 24
XCUR_SIZES = [24, 30, 36, 48, 60, 72, 96]

# palette
OUT = "#3b2b3f"      # outline (dark plum)
WHITE = "#ffffff"
FUR_SH = "#bccaf2"   # lavender shade of the white fur
PINK = "#f78f9b"     # toe beans
PINK_D = "#d9667a"   # bean rim
PINK_L = "#ffd0d4"   # bean highlight
RED = "#e8414f"
BEIGE = "#f3d8ae"
PAD_D = ("M0-3.1C1.9-3.1 3-1.3 3.9.4C4.8 2.1 4.3 4.1 2.6 4.1C1.7 4.1 1 3.65 0 3.65"
         "S-1.7 4.1-2.6 4.1C-4.3 4.1-4.8 2.1-3.9.4C-3-1.3-1.9-3.1 0-3.1Z")
OW = 2.2             # outline stroke width (1.1 px each side at 24 px)


def f(v):
    return f"{v:.2f}".rstrip("0").rstrip(".")


# --------------------------------------------------------------- primitives
def pad_shapes():
    """Paw print in local units: main pad + 4 toes, centred roughly on (0,0)."""
    pad = f"<path d='{PAD_D}'/>"
    toes = [(-4.3, -4.0, -32), (-1.55, -6.1, -10), (1.55, -6.1, 10), (4.3, -4.0, 32)]
    toe_el = "".join(
        f"<ellipse cx='{f(x)}' cy='{f(y)}' rx='1.45' ry='1.85' transform='rotate({a} {f(x)} {f(y)})'/>"
        for x, y, a in toes)
    return pad, toe_el, toes


def paw_print(x, y, s=1.0, rot=0, outline=False, color=PINK):
    """Pink paw print. outline=True adds a dark rim so it reads on any background."""
    pad, toes, toe_list = pad_shapes()
    shapes = pad + toes
    g = [f"<g transform='translate({f(x)} {f(y)}) rotate({f(rot)}) scale({f(s)}) translate(0 1.2)'>"]
    if outline:
        g.append(f"<g fill='{OUT}' stroke='{OUT}' stroke-width='{f(OW / s)}' stroke-linejoin='round'>{shapes}</g>")
    g.append(f"<g fill='{color}' stroke='{PINK_D}' stroke-width='{f(0.55 / s if not outline else 0.01)}'>{shapes}</g>")
    # little highlights
    hl = [("-1.5", "-.4", "1.1", ".65")] + [(f(tx - .45), f(ty - .6), ".5", ".65") for tx, ty, _ in toe_list]
    g.append("".join(f"<ellipse cx='{a}' cy='{b}' rx='{c}' ry='{d}' fill='{PINK_L}'/>" for a, b, c, d in hl))
    g.append("</g>")
    return "".join(g)


def mitten(shapes, cx, cy):
    """White furry body: dark outline, lavender shade, white fill offset up-left."""
    return (f"<g fill='{OUT}' stroke='{OUT}' stroke-width='{OW}' stroke-linejoin='round'>{shapes}</g>"
            f"<g fill='{FUR_SH}'>{shapes}</g>"
            f"<g fill='{WHITE}' transform='translate({f(cx - .45)} {f(cy - .55)}) scale(.86) translate({f(-cx)} {f(-cy)})'>{shapes}</g>")


def outlined_path(d, fill=PINK, extra=""):
    return (f"<path d='{d}' fill='{OUT}' stroke='{OUT}' stroke-width='{OW}' stroke-linejoin='round' stroke-linecap='round' {extra}/>"
            f"<path d='{d}' fill='{fill}' stroke='{fill}' stroke-width='.6' stroke-linejoin='round' {extra}/>")


def stroke_line(d, w=1.8, color=PINK):
    """A stroked (open) path with a dark rim."""
    return (f"<path d='{d}' fill='none' stroke='{OUT}' stroke-width='{f(w + OW)}' stroke-linecap='round' stroke-linejoin='round'/>"
            f"<path d='{d}' fill='none' stroke='{color}' stroke-width='{f(w)}' stroke-linecap='round' stroke-linejoin='round'/>")


def arc_path(cx, cy, r, a0, a1):
    x0, y0 = cx + r * math.cos(math.radians(a0)), cy + r * math.sin(math.radians(a0))
    x1, y1 = cx + r * math.cos(math.radians(a1)), cy + r * math.sin(math.radians(a1))
    large = 1 if (a1 - a0) % 360 > 180 else 0
    return f"M{f(x0)} {f(y0)}A{f(r)} {f(r)} 0 {large} 1 {f(x1)} {f(y1)}"


def svg(body):
    return ("<svg xmlns='http://www.w3.org/2000/svg' width='32' height='32' viewBox='0 0 32 32'>"
            + body + "</svg>\n")


# --------------------------------------------------------------- pointing paw
TIP_D, BODY_R = 15.2, 8.8


def pointer_paw(tip=(3.4, 3.0), angle=-35, mirror=False):
    """Teardrop paw whose tip is the hotspot. angle: tilt of the tip from vertical."""
    a = math.radians(angle)
    # vector from body centre to tip, rotated
    vx, vy = -(-TIP_D) * math.sin(a), -TIP_D * math.cos(a)
    cx, cy = tip[0] - vx, tip[1] - vy
    # teardrop in local coords (tip up)
    t = math.acos(BODY_R / TIP_D)
    p1 = (BODY_R * math.cos(-math.pi / 2 + t), BODY_R * math.sin(-math.pi / 2 + t))
    p2 = (BODY_R * math.cos(-math.pi / 2 - t), BODY_R * math.sin(-math.pi / 2 - t))
    d = (f"M0 {f(-TIP_D)}L{f(p1[0])} {f(p1[1])}A{BODY_R} {BODY_R} 0 1 1 {f(p2[0])} {f(p2[1])}Z")
    body = (f"<g transform='translate({f(cx)} {f(cy)})'>"
            + mitten(f"<path d='{d}' transform='rotate({angle})'/>", 0, 0) + "</g>")
    body += paw_print(cx, cy, 0.86, angle)
    # shift the print a bit away from the tip
    if mirror:
        body = f"<g transform='translate(32 0) scale(-1 1)'>{body}</g>"
    return body


def default():
    return pointer_paw(), (3.4, 3.0)


def right_ptr():
    return pointer_paw(mirror=True), (32 - 3.4, 3.0)


def center_ptr():
    return pointer_paw(tip=(16, 2.6), angle=0), (16, 2.6)


def badge(x, y, glyph, fill=PINK, r=5.2):
    return (f"<circle cx='{f(x)}' cy='{f(y)}' r='{f(r)}' fill='{OUT}' stroke='{OUT}' stroke-width='{OW}'/>"
            f"<circle cx='{f(x)}' cy='{f(y)}' r='{f(r)}' fill='{fill}'/>"
            f"<g transform='translate({f(x)} {f(y)})'>{glyph}</g>")


G_QUESTION = (f"<path d='M-1.8-1.5C-1.8-3.6 1.8-3.6 1.8-1.5 1.8 0 0 0 0 1.3' fill='none' stroke='{WHITE}' "
              f"stroke-width='1.6' stroke-linecap='round' stroke-linejoin='round'/><circle cx='0' cy='3.3' r='.95' fill='{WHITE}'/>")
G_PLUS = f"<path d='M-2.8 0H2.8M0-2.8V2.8' stroke='{WHITE}' stroke-width='1.8' stroke-linecap='round'/>"
G_MINUS = f"<path d='M-2.8 0H2.8' stroke='{WHITE}' stroke-width='1.8' stroke-linecap='round'/>"
G_LINK = (f"<path d='M-2.6 2.6C-2.6-1 -.5-2 2-2' fill='none' stroke='{WHITE}' stroke-width='1.5' stroke-linecap='round'/>"
          f"<path d='M.6-4 2.8-2 .6 0' fill='none' stroke='{WHITE}' stroke-width='1.5' stroke-linecap='round' stroke-linejoin='round'/>")
G_MENU = f"<path d='M-2.6-2H2.6M-2.6 0H2.6M-2.6 2H2.6' stroke='{WHITE}' stroke-width='1.2' stroke-linecap='round'/>"
G_NO = (f"<circle r='2.9' fill='none' stroke='{WHITE}' stroke-width='1.4'/>"
        f"<path d='M-2 2 2-2' stroke='{WHITE}' stroke-width='1.4' stroke-linecap='round'/>")


def help_():
    return pointer_paw() + badge(25.4, 7.2, G_QUESTION), (3.4, 3.0)


def copy():
    return pointer_paw() + badge(25.0, 25.0, G_PLUS), (3.4, 3.0)


def alias():
    return pointer_paw() + badge(25.0, 25.0, G_LINK, fill="#8fa6ea"), (3.4, 3.0)


def context_menu():
    return pointer_paw() + badge(25.0, 25.0, G_MENU, fill="#8fa6ea"), (3.4, 3.0)


def no_drop():
    return pointer_paw() + badge(25.0, 25.0, G_NO, fill=RED), (3.4, 3.0)


PROGRESS_FRAMES, WAIT_FRAMES, FRAME_MS = 12, 16, 55


def progress_frames():
    frames = []
    for i in range(PROGRESS_FRAMES):
        a = i * 360 / PROGRESS_FRAMES
        spin = (f"<circle cx='25' cy='25' r='5.2' fill='{OUT}' stroke='{OUT}' stroke-width='{OW}'/>"
                f"<circle cx='25' cy='25' r='5.2' fill='{WHITE}'/>"
                f"<path d='{arc_path(25, 25, 3.2, a, a + 200)}' fill='none' stroke='{PINK}' stroke-width='1.9' stroke-linecap='round'/>")
        frames.append(pointer_paw() + spin)
    return frames, (3.4, 3.0)


def wait_frames():
    frames = []
    cx, cy, r = 16, 16, 10.6
    for i in range(WAIT_FRAMES):
        a = i * 360 / WAIT_FRAMES - 90
        b = (f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='{OUT}' stroke='{OUT}' stroke-width='{OW}'/>"
             f"<circle cx='{cx}' cy='{cy}' r='{r}' fill='{FUR_SH}'/>"
             f"<circle cx='{f(cx - .4)}' cy='{f(cy - .5)}' r='{f(r - 1.1)}' fill='{WHITE}'/>"
             f"<path d='{arc_path(cx, cy, r - 1.6, a, a + 110)}' fill='none' stroke='{PINK}' stroke-width='2' stroke-linecap='round'/>"
             + paw_print(cx, cy + .6, 0.95))
        frames.append(b)
    return frames, (16, 16)


# --------------------------------------------------------------- front paws
def front_paw(spread=1.0, claw=False, s=0.92, cy=17.6):
    """Paw seen from the front: big pad body + 4 toe bumps."""
    cx = 16
    toes = [(-6.1, -5.4), (-2.3, -8.5), (2.3, -8.5), (6.1, -5.4)]
    shapes = f"<circle cx='0' cy='1.8' r='7.6'/><ellipse cx='0' cy='{f(-4.6 * spread)}' rx='{f(6.4 * spread)}' ry='4.2'/>"
    for tx, ty in toes:
        shapes += f"<circle cx='{f(tx * spread)}' cy='{f(ty * spread + (1 - spread) * 2)}' r='3.2'/>"
    body = ""
    if claw:
        body += outlined_path("M-1.5-11.3 0-15.4 1.5-11.3Z", fill=PINK)
    body += mitten(shapes, 0, 0)
    # beans on the front paw
    body += f"<path d='{PAD_D}' transform='translate(0 2.2) scale(1.22)' fill='{PINK}' stroke='{PINK_D}' stroke-width='.45'/>"
    body += f"<ellipse cx='-1.6' cy='1.4' rx='1.3' ry='.75' transform='rotate(-30 -1.6 1.4)' fill='{PINK_L}'/>"
    for tx, ty in toes:
        x, y = tx * spread, ty * spread + (1 - spread) * 2
        body += f"<ellipse cx='{f(x)}' cy='{f(y + .2)}' rx='1.4' ry='1.7' fill='{PINK}' stroke='{PINK_D}' stroke-width='.55'/>"
        body += f"<ellipse cx='{f(x - .45)}' cy='{f(y - .35)}' rx='.5' ry='.65' fill='{PINK_L}'/>"
    return f"<g transform='translate({cx} {f(cy)}) scale({s})'>{body}</g>"


def pointer():
    s, cy = 0.9, 17.8
    return front_paw(claw=True, s=s, cy=cy), (16, f_round(cy - 15.4 * s))


def f_round(v):
    return round(v, 2)


def openhand():
    return front_paw(spread=1.08, s=0.9, cy=17.0), (16, 16)


def dnd_move():
    return front_paw(spread=0.86, s=0.88, cy=16.6), (16, 16)


def not_allowed():
    body = front_paw(spread=1.0, s=0.66, cy=16.8)
    ring = (f"<circle cx='16' cy='16' r='9.6' fill='none' stroke='{OUT}' stroke-width='{f(2.6 + OW)}'/>"
            f"<path d='M9.2 22.8 22.8 9.2' stroke='{OUT}' stroke-width='{f(2.6 + OW)}' stroke-linecap='round'/>"
            f"<circle cx='16' cy='16' r='9.6' fill='none' stroke='{RED}' stroke-width='2.6'/>"
            f"<path d='M9.2 22.8 22.8 9.2' stroke='{RED}' stroke-width='2.6' stroke-linecap='round'/>")
    return body + ring, (16, 16)


def dnd_no_drop():
    return front_paw(spread=0.86, s=0.8, cy=15.0) + badge(24.6, 24.6, G_NO, fill=RED), (16, 16)


# --------------------------------------------------------------- arrows
def head(x, y, rot, size=1.0):
    d = "M0-4.6 5.2 0 0 4.6Z"
    return (f"<g transform='translate({f(x)} {f(y)}) rotate({rot}) scale({size})'>"
            + outlined_path(d) + "</g>")


def double_arrow(rot, bar=False):
    inner = head(25.2, 16, 0) + head(6.8, 16, 180)
    if bar:
        inner += stroke_line("M16 8.5V23.5", w=2.4, color=WHITE)
    g = f"<g transform='rotate({rot} 16 16)'>{inner}</g>"
    if not bar:
        g += paw_print(16, 16, 0.62, 0, outline=True)
    return g, (16, 16)


def size_hor():
    return double_arrow(0)


def size_ver():
    return double_arrow(90)


def size_fdiag():
    return double_arrow(45)


def size_bdiag():
    return double_arrow(-45)


def col_resize():
    return double_arrow(0, bar=True)


def row_resize():
    return double_arrow(90, bar=True)


def fleur():
    g = head(25.2, 16, 0) + head(6.8, 16, 180) + head(16, 6.8, -90) + head(16, 25.2, 90)
    return g + paw_print(16, 16, 0.6, 0, outline=True), (16, 16)


def single_arrow(rot):
    # arrow pointing up with the paw below; hotspot at the arrow tip
    g = f"<g transform='rotate({rot} 16 16)'>" + head(16, 7.6, -90, 1.0) + "</g>"
    px, py = 16, 18.4
    tipx, tipy = 16, 2.4
    # rotate paw position & tip around the centre
    a = math.radians(rot)

    def r(x, y):
        x, y = x - 16, y - 16
        return 16 + x * math.cos(a) - y * math.sin(a), 16 + x * math.sin(a) + y * math.cos(a)
    px, py = r(px, py)
    tx, ty = r(tipx, tipy)
    return g + paw_print(px, py, 0.62, 0, outline=True), (f_round(tx), f_round(ty))


def up_arrow():
    return single_arrow(0)


def right_arrow():
    return single_arrow(90)


def down_arrow():
    return single_arrow(180)


def left_arrow():
    return single_arrow(270)


# --------------------------------------------------------------- precision
def crosshair():
    d = "M16 4.5V12.5M16 19.5V27.5M4.5 16H12.5M19.5 16H27.5"
    g = stroke_line(d, w=1.7)
    g += f"<circle cx='16' cy='16' r='1.3' fill='{OUT}'/><circle cx='16' cy='16' r='.75' fill='{PINK}'/>"
    g += paw_print(24.5, 24.0, 0.5, 15, outline=True)
    return g, (16, 16)


def cell():
    d = "M16 7V25M7 16H25"
    return stroke_line(d, w=4.2, color=WHITE) + stroke_line(d, w=2.2) , (16, 16)


def x_cursor():
    d = "M9.5 9.5 22.5 22.5M22.5 9.5 9.5 22.5"
    return stroke_line(d, w=3.4), (16, 16)


def text():
    d = "M12.6 6.2C14.6 6.2 16 6.8 16 8.6V23.4C16 25.2 14.6 25.8 12.6 25.8M19.4 6.2C17.4 6.2 16 6.8 16 8.6M16 23.4C16 25.2 17.4 25.8 19.4 25.8"
    return stroke_line(d, w=1.6) + paw_print(22.4, 22.6, 0.36, 10, outline=True), (16, 16)


def vertical_text():
    g, hs = text()
    return f"<g transform='rotate(90 16 16)'>{g}</g>", hs


def pencil():
    # drawn horizontally with the tip at (0,0), then rotated to point bottom-left
    body = (outlined_path("M0 0 7-3.1H21.5V3.1H7Z", fill=BEIGE)
            + f"<path d='M0 0 2.6-1.15V1.15Z' fill='{OUT}'/>"
            + f"<path d='M7-3.1H21.5V3.1H7Z' fill='{PINK}'/>"
            + f"<path d='M7-3.1H21.5V-1.2H7Z' fill='{PINK_L}'/>"
            + f"<path d='M7-3.1H21.5V3.1H7Z' fill='none' stroke='{OUT}' stroke-width='.8'/>"
            + f"<path d='M21.5-3.1H23.6V3.1H21.5Z' fill='{FUR_SH}' stroke='{OUT}' stroke-width='.8'/>"
            + f"<path d='M23.6-3.1H24.6C26.4-3.1 27-1.7 27 0S26.4 3.1 24.6 3.1H23.6Z' fill='{WHITE}' stroke='{OUT}' stroke-width='.8'/>")
    g = f"<g transform='translate(3 29) rotate(-45)'>{body}</g>"
    g += paw_print(23.5, 24.5, 0.45, 0, outline=True)
    return g, (3, 29)


def zoom(plus):
    g = stroke_line("M19.3 19.3 27 27", w=3.4)
    lens = (f"<circle cx='13.5' cy='13.5' r='8' fill='{OUT}'/>"
            f"<circle cx='13.5' cy='13.5' r='6.9' fill='{PINK}'/>"
            f"<circle cx='13.5' cy='13.5' r='5.2' fill='{FUR_SH}'/>"
            f"<circle cx='13.1' cy='13' r='4.7' fill='{WHITE}'/>")
    glyph = "M10.5 13.5H16.5" + ("M13.5 10.5V16.5" if plus else "")
    lens += f"<path d='{glyph}' stroke='{PINK_D}' stroke-width='1.8' stroke-linecap='round'/>"
    return g + lens, (13.5, 13.5)


# --------------------------------------------------------------- name map
DESIGNS = {
    "default": default, "help": help_, "copy": copy, "alias": alias,
    "context-menu": context_menu, "no-drop": no_drop, "right_ptr": right_ptr,
    "center_ptr": center_ptr, "pointer": pointer, "openhand": openhand,
    "dnd-move": dnd_move, "not-allowed": not_allowed, "dnd-no-drop": dnd_no_drop,
    "size_hor": size_hor, "size_ver": size_ver, "size_fdiag": size_fdiag,
    "size_bdiag": size_bdiag, "col-resize": col_resize, "row-resize": row_resize,
    "fleur": fleur, "up-arrow": up_arrow, "down-arrow": down_arrow,
    "left-arrow": left_arrow, "right-arrow": right_arrow, "crosshair": crosshair,
    "cell": cell, "x-cursor": x_cursor, "text": text, "vertical-text": vertical_text,
    "pencil": pencil, "zoom-in": lambda: zoom(True), "zoom-out": lambda: zoom(False),
}
ANIMATED = {"progress": progress_frames, "wait": wait_frames}

# cursors that reuse another design (same hotspot)
SAME_AS = {
    "all-scroll": "fleur", "draft": "pencil", "color-picker": "pencil",
    "pirate": "x-cursor", "wayland-cursor": "default",
    "left_side": "size_hor", "right_side": "size_hor",
    "top_side": "size_ver", "bottom_side": "size_ver",
    "top_left_corner": "size_fdiag", "bottom_right_corner": "size_fdiag",
    "top_right_corner": "size_bdiag", "bottom_left_corner": "size_bdiag",
}

# alias names, same set as Breeze
LINKS = {"00000000000000020006000e7e9ffc3f": "progress", "00008160000006810000408080010102": "size_ver", "03b6e0fcb3499374a867c041f52298f0": "circle", "08e8e1c95fe2fc01f976f1e063a24ccd": "progress", "1081e37283d90000800003c07f3ef6bf": "copy", "3085a0e285430894940527032f8b26df": "alias", "3ecb610c1bf2410f44200f48c40d3599": "progress", "4498f0e0c1937ffe01fd06f973665830": "dnd-move", "5c6cd98b3f3ebcb1f9c7f1c204630408": "help", "6407b0e94181790501fd1e167b474872": "copy", "640fb0e74195791501fd1ed57b41487f": "alias", "9081237383d90e509aa00f00170e968f": "dnd-move", "9d800788f1b08800ae810202380a0822": "pointer", "a2a266d0498c3104214a47bd64ab0fc8": "alias", "arrow": "default", "b66166c04f8c3109214a4fbd64a50fc8": "copy", "circle": "not-allowed", "closedhand": "dnd-move", "cross": "crosshair", "crossed_circle": "not-allowed", "d9ce0ab605698f320427677b458ad60b": "help", "dnd-copy": "copy", "dnd-none": "dnd-move", "e29285e634086352946a0e7090d73106": "pointer", "e-resize": "size_hor", "ew-resize": "size_hor", "fcf21c00b30f7e3f83fe0dfd12e71cff": "dnd-move", "forbidden": "no-drop", "grab": "openhand", "grabbing": "closedhand", "half-busy": "progress", "hand1": "pointer", "hand2": "pointer", "h_double_arrow": "size_hor", "ibeam": "text", "left_ptr": "default", "left_ptr_help": "help", "left_ptr_watch": "progress", "link": "alias", "move": "dnd-move", "ne-resize": "size_bdiag", "nesw-resize": "size_bdiag", "n-resize": "size_ver", "ns-resize": "size_ver", "nw-resize": "size_fdiag", "nwse-resize": "size_fdiag", "plus": "cell", "pointing_hand": "pointer", "question_arrow": "help", "sb_h_double_arrow": "size_hor", "sb_v_double_arrow": "size_ver", "se-resize": "size_fdiag", "size_all": "fleur", "size-bdiag": "size_bdiag", "size-fdiag": "size_fdiag", "size-hor": "size_hor", "size-ver": "size_ver", "split_h": "col-resize", "split_v": "row-resize", "s-resize": "size_ver", "sw-resize": "size_bdiag", "tcross": "crosshair", "top_left_arrow": "default", "v_double_arrow": "size_ver", "watch": "wait", "whats_this": "help", "w-resize": "size_hor", "xterm": "text"}


# --------------------------------------------------------------- output
def render_png(svg_path, px, png_path):
    subprocess.run(["magick", "-background", "none", "-density", str(96 * px / 32),
                    "rsvg:" + svg_path, "-resize", f"{px}x{px}!", "png32:" + png_path], check=True)


def read_png_argb(png_path):
    out = subprocess.run(["magick", png_path, "-depth", "8", "rgba:-"], check=True, capture_output=True).stdout
    px = []
    for i in range(0, len(out), 4):
        r, g, b, a = out[i:i + 4]
        # XCursor wants premultiplied ARGB
        px.append((a << 24) | ((r * a // 255) << 16) | ((g * a // 255) << 8) | (b * a // 255))
    return px


def write_xcursor(path, images):
    """images: list of (nominal, size_px, xhot, yhot, delay, argb_pixels)"""
    ntoc = len(images)
    header = struct.pack("<4sIII", b"Xcur", 16, 0x10000, ntoc)
    pos = 16 + 12 * ntoc
    toc, chunks = b"", b""
    for nominal, w, xh, yh, delay, px in images:
        toc += struct.pack("<III", 0xFFFD0002, nominal, pos)
        chunk = struct.pack("<IIIIIIIII", 36, 0xFFFD0002, nominal, 1, w, w, xh, yh, delay)
        chunk += struct.pack(f"<{len(px)}I", *px)
        chunks += chunk
        pos += len(chunk)
    with open(path, "wb") as fh:
        fh.write(header + toc + chunks)


def build():
    if os.path.isdir(OUT_DIR):
        shutil.rmtree(OUT_DIR)
    sdir = os.path.join(OUT_DIR, "cursors_scalable")
    xdir = os.path.join(OUT_DIR, "cursors")
    os.makedirs(sdir)
    os.makedirs(xdir)
    tmp = tempfile.mkdtemp(prefix="pastelpaws-")

    jobs = {}
    for name, fn in DESIGNS.items():
        body, hs = fn()
        jobs[name] = ([body], hs, None)
    for name, fn in ANIMATED.items():
        frames, hs = fn()
        jobs[name] = (frames, hs, FRAME_MS)
    for name, src in SAME_AS.items():
        jobs[name] = jobs[src]

    for name, (frames, (hx, hy), delay) in jobs.items():
        d = os.path.join(sdir, name)
        os.makedirs(d)
        meta, ximgs = [], []
        for i, body in enumerate(frames):
            fname = f"{name}.svg" if len(frames) == 1 else f"{name}-{i + 1:02d}.svg"
            fpath = os.path.join(d, fname)
            with open(fpath, "w") as fh:
                fh.write(svg(body))
            entry = {"filename": fname, "hotspot_x": hx, "hotspot_y": hy, "nominal_size": NOMINAL}
            if delay:
                entry["delay"] = delay
            meta.append(entry)
            for nominal in XCUR_SIZES:
                px = round(nominal * 32 / NOMINAL)
                png = os.path.join(tmp, f"{name}-{i}-{px}.png")
                render_png(fpath, px, png)
                k = px / 32
                ximgs.append((nominal, px, min(px - 1, int(hx * k)), min(px - 1, int(hy * k)),
                              delay or 50, read_png_argb(png)))
        with open(os.path.join(d, "metadata.json"), "w") as fh:
            json.dump(meta, fh, indent=4)
        ximgs.sort(key=lambda t: t[0])
        write_xcursor(os.path.join(xdir, name), ximgs)

    for link, target in LINKS.items():
        os.symlink(target, os.path.join(sdir, link))
        os.symlink(target, os.path.join(xdir, link))

    with open(os.path.join(OUT_DIR, "index.theme"), "w") as fh:
        fh.write("[Icon Theme]\nName=Pastel Paws\n"
                 "Comment=Cute pastel cat-paw cursors (SVG for Plasma 6, XCursor fallback)\n"
                 "Inherits=breeze_cursors\n")
    shutil.rmtree(tmp)
    print(f"built {len(jobs)} cursors + {len(LINKS)} aliases in {OUT_DIR}")


def install():
    dest = os.path.expanduser(f"~/.icons/{THEME}")
    if os.path.isdir(dest):
        shutil.rmtree(dest)
    shutil.copytree(OUT_DIR, dest, symlinks=True)
    print(f"installed to {dest}")


if __name__ == "__main__":
    build()
    if "--install" in sys.argv:
        install()
