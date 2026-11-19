#!/usr/bin/env python3
"""Cat Paw cursor theme generator.

Writes one SVG per cursor shape (Plasma 6 `cursors_scalable` format) and
renders the same SVGs into classic Xcursor files (`cursors/`) for X11 and
XWayland apps.  Every SVG uses a 32x32 canvas at nominal size 24, like Breeze.

Usage:  python3 build.py [--variant pink|grey|soft] [output-dir]
        (default output: ./build/<theme dir of the variant>)
"""
import json
import math
import os
import shutil
import struct

import cairo
import gi

gi.require_version("Rsvg", "2.0")
from gi.repository import Rsvg  # noqa: E402

# Colour variants: theme directory, display name, comment and paw colours.
# The fixed colours below (badges, outline) are shared by every variant.
VARIANTS = {
    "pink": {"dir": "CatPaw", "name": "Cat Paw",
             "comment": "White cat paws with pink toe beans",
             "fur": "#ffffff", "bean": "#f49ab0", "bean2": "#e07a95"},
    "grey": {"dir": "CatPawGrey", "name": "Cat Paw Grey",
             "comment": "Grey cat paws with dark grey toe beans",
             "fur": "#b4b9c0", "bean": "#5e646c", "bean2": "#484d54"},
    # White fur, pink beans, thin outline, Breeze Light for the shapes
    # without a paw, pointer = open paw with one claw, openhand = all claws out.
    "soft": {"dir": "CatPawSoft", "name": "Cat Paw Soft",
             "comment": "White cat paws with pink toe beans and a thin outline",
             "fur": "#ffffff", "bean": "#f49ab0", "bean2": "#e07a95",
             "ow_scale": 0.36, "clawed": True,
             "breeze": ("text", "vertical-text", "crosshair", "cell", "x-cursor")},
}
# Where the shapes listed in a variant's "breeze" are taken from (Breeze Light,
# Plasma 6 SVG version, GPL-2.0-or-later, from the breeze package).
BREEZE_DIR = "/usr/share/icons/Breeze_Light/cursors_scalable"
VARIANT = VARIANTS["pink"]
NOMINAL = 24
CANVAS = 32
XCURSOR_SIZES = [24, 30, 36, 48, 60, 72, 96]

# Palette (Breeze Light style: light body, dark outline).  FUR, BEAN and
# BEAN_DARK are placeholders replaced with the variant's colours in Cursor.svg().
OUT = "#232629"      # outline
FUR = "@fur@"        # body
BEAN = "@bean@"      # paw pads
BEAN_DARK = "@bean2@"
WHITE = "#ffffff"    # symbols on the coloured badges
RED = "#da4453"
GREEN = "#27ae60"
BLUE = "#3daee9"
OW = 1.1             # visible outline width (canvas units)


# --------------------------------------------------------------- affine utils
class M:
    """2D affine matrix (a b c d e f) as in SVG matrix()."""

    def __init__(self, a=1, b=0, c=0, d=1, e=0, f=0):
        self.v = (a, b, c, d, e, f)

    def __mul__(self, o):
        a, b, c, d, e, f = self.v
        A, B, C, D, E, F = o.v
        return M(a * A + c * B, b * A + d * B, a * C + c * D, b * C + d * D,
                 a * E + c * F + e, b * E + d * F + f)

    def apply(self, x, y):
        a, b, c, d, e, f = self.v
        return a * x + c * y + e, b * x + d * y + f

    def svg(self):
        return "matrix(%s)" % " ".join("%.4f" % x for x in self.v)

    @property
    def scale(self):
        a, b, c, d, _, _ = self.v
        return math.sqrt(abs(a * d - b * c))


def T(x, y):
    return M(1, 0, 0, 1, x, y)


def R(deg):
    r = math.radians(deg)
    return M(math.cos(r), math.sin(r), -math.sin(r), math.cos(r), 0, 0)


def S(sx, sy=None):
    return M(sx, 0, 0, sx if sy is None else sy, 0, 0)


I = M()


# ------------------------------------------------------------- shape helpers
def E(cx, cy, rx, ry, rot=0):
    t = ' transform="rotate(%g %g %g)"' % (rot, cx, cy) if rot else ""
    return '<ellipse cx="%g" cy="%g" rx="%g" ry="%g"%s/>' % (cx, cy, rx, ry, t)


def C(cx, cy, r):
    return '<circle cx="%g" cy="%g" r="%g"/>' % (cx, cy, r)


def P(d):
    return '<path d="%s"/>' % d


def RECT(x, y, w, h, r=0):
    return '<rect x="%g" y="%g" width="%g" height="%g" rx="%g"/>' % (x, y, w, h, r)


def poly(pts):
    return P("M" + " L".join("%g,%g" % p for p in pts) + " Z")


class Cursor:
    def __init__(self, hot):
        self.hot = hot
        self.body = []
        self.shadow = []

    def sil(self, shapes, m=I, fill=FUR, ow=None, outline=OUT):
        """Outlined silhouette: union of shapes, dark outline, solid fill."""
        ow = (OW if ow is None else ow) * VARIANT.get("ow_scale", 1.0)
        sw = 2 * ow / m.scale
        inner = "".join(shapes)
        self.shadow.append('<g transform="%s" stroke-width="%.3f">%s</g>'
                           % (m.svg(), sw, inner))
        self.body.append(
            '<g transform="%s"><g fill="%s" stroke="%s" stroke-width="%.3f" '
            'stroke-linejoin="round" stroke-linecap="round">%s</g>'
            '<g fill="%s">%s</g></g>' % (m.svg(), outline, outline, sw, inner, fill, inner))

    def add(self, shapes, m=I, fill=None, stroke=None, sw=1.0, extra=""):
        attrs = 'fill="%s"' % (fill or "none")
        if stroke:
            attrs += (' stroke="%s" stroke-width="%.3f" stroke-linecap="round" '
                      'stroke-linejoin="round"' % (stroke, sw / m.scale))
        self.body.append('<g transform="%s" %s %s>%s</g>'
                         % (m.svg(), attrs, extra, "".join(shapes)))

    def svg(self):
        text = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="%d" height="%d" '
            'viewBox="0 0 %d %d">\n'
            '<defs><filter id="sh" x="-20%%" y="-20%%" width="140%%" height="140%%" '
            'color-interpolation-filters="sRGB">'
            '<feGaussianBlur stdDeviation=".7"/></filter></defs>\n'
            '<g opacity=".3" filter="url(#sh)"><g transform="translate(.4 1)" '
            'fill="#000" stroke="#000" stroke-linejoin="round">%s</g></g>\n%s\n</svg>\n'
            % (CANVAS, CANVAS, CANVAS, CANVAS, "".join(self.shadow), "\n".join(self.body)))
        return (text.replace(FUR, VARIANT["fur"]).replace(BEAN_DARK, VARIANT["bean2"])
                .replace(BEAN, VARIANT["bean"]))


# ------------------------------------------------------------------ the paw
# Local coordinates: upright paw, roughly centred on (0, 0), ~15 x 15 units.
PALM_BEAN = ("M-3.5,5.6 C-3.9,3.0 -1.8,1.3 0,1.3 C1.8,1.3 3.9,3.0 3.5,5.6 "
             "C3.3,7.1 2.0,7.3 1.2,6.8 C0.6,6.4 -0.6,6.4 -1.2,6.8 "
             "C-2.0,7.3 -3.3,7.1 -3.5,5.6 Z")


def paw_shapes(style="open"):
    """Return (fur, beans) shape lists for an upright paw."""
    if style == "open":
        toes = [(-2.35, -3.55, 2.45, 2.85, -6), (2.35, -3.55, 2.45, 2.85, 6),
                (-5.6, -0.15, 2.2, 2.6, -30), (5.6, -0.15, 2.2, 2.6, 30)]
        fur = [E(0, 3.7, 5.8, 4.9), E(0, 0.8, 5.3, 3.6)]
    elif style == "closed":  # toes curled in: tighter, lower, rounder
        toes = [(-2.0, -2.2, 2.3, 2.3, 0), (2.0, -2.2, 2.3, 2.3, 0),
                (-4.9, 0.6, 2.0, 2.2, -25), (4.9, 0.6, 2.0, 2.2, 25)]
        fur = [E(0, 3.6, 5.6, 4.6), E(0, 1.2, 5.2, 3.4)]
    elif style == "point":  # one toe raised and stretched ("boop")
        toes = [(-1.4, -4.9, 2.2, 3.5, -4), (2.9, -3.1, 2.3, 2.7, 10),
                (-5.4, -0.4, 2.1, 2.5, -30), (5.8, 0.3, 2.1, 2.5, 30)]
        fur = [E(0, 3.7, 5.8, 4.9), E(0, 0.8, 5.3, 3.6)]
    else:
        raise ValueError(style)
    beans = []
    for (x, y, rx, ry, rot) in toes:
        fur.append(E(x, y, rx, ry, rot))
        beans.append(E(x, y - 0.1, rx - 0.95, ry - 1.0, rot))
    beans.append(P(PALM_BEAN))
    return fur, beans


def claw_shape(x, y, length=3.6, width=2.1, rot=0):
    """Thorn-like claw whose base sits at (x, y), pointing 'up' rotated by rot."""
    w = width / 2
    d = ("M%g,%g Q%g,%g 0,%g Q%g,%g %g,%g Z"
         % (-w, 0.8, -w * 0.5, -length * 0.55, -length, w * 0.6, -length * 0.45, w, 0.8))
    return '<path transform="translate(%g %g) rotate(%g)" d="%s"/>' % (x, y, rot, d)


CLAW_BASE = (-2.6, -5.9)  # top of the left inner toe
CLAW_LEN = 3.6


def claw_tip(rot=0, base=CLAW_BASE, length=CLAW_LEN):
    r = math.radians(rot)
    return base[0] + length * math.sin(r), base[1] - length * math.cos(r)


def draw_paw(c, m, style="open", claws=()):
    """claws: (base_x, base_y, rotation[, length]) in paw coordinates."""
    fur, beans = paw_shapes(style)
    for claw in claws:
        bx, by, rot = claw[:3]
        fur.append(claw_shape(bx, by, length=claw[3] if len(claw) > 3 else CLAW_LEN, rot=rot))
    c.sil(fur, m)
    c.add(beans, m, fill=BEAN)


def pointer_paw(hot=(3.5, 3.0), angle=-32, scale=1.08, mirror=False):
    """Matrix placing a clawed paw so that the claw tip lands on `hot`."""
    claw_rot = -8
    tx, ty = claw_tip(claw_rot)
    base = R(angle) * S(scale)
    if mirror:
        base = S(-1, 1) * base
    px, py = base.apply(tx, ty)
    return T(hot[0] - px, hot[1] - py) * base, [(CLAW_BASE[0], CLAW_BASE[1], claw_rot)]


def mini_paw(c, cx, cy, scale, fill=BEAN, m=I):
    _, beans = paw_shapes("open")
    c.add(beans, m * T(cx, cy) * S(scale), fill=fill)


def paw_disc(c, cx, cy, r=5.2, m=I):
    c.sil([C(cx, cy, r)], m)
    mini_paw(c, cx, cy + 0.2, r / 8.3, m=m)


# ----------------------------------------------------------------- cursors
CURSORS = {}


def cursor(name):
    def deco(f):
        CURSORS[name] = f
        return f
    return deco


def base_pointer(c, scale=1.08, hot=(3.5, 3.0)):
    m, claws = pointer_paw(hot=hot, scale=scale)
    draw_paw(c, m, claws=claws)


@cursor("default")
def _default():
    c = Cursor((3.5, 3.0))
    base_pointer(c)
    return c


@cursor("wayland-cursor")
def _wayland():
    return _default()


@cursor("right_ptr")
def _right_ptr():
    c = Cursor((28.5, 3.0))
    m, claws = pointer_paw(hot=(28.5, 3.0), mirror=True)
    draw_paw(c, m, claws=claws)
    return c


@cursor("center_ptr")
def _center_ptr():
    c = Cursor((16, 2.5))
    tx, ty = claw_tip(0, base=(0, -6.35))
    m = T(16 - tx * 1.1, 2.5 - ty * 1.1) * S(1.1)
    draw_paw(c, m, claws=[(0, -6.35, 0)])
    return c


# Open paw toes as (x, y, ry, rotation), for placing claws on top of them.
OPEN_TOES = [(-2.35, -3.55, 2.85, -6), (2.35, -3.55, 2.85, 6),
             (-5.6, -0.15, 2.6, -30), (5.6, -0.15, 2.6, 30)]


def toe_claw(toe, length):
    """Claw on top of a toe, pointing along the toe; returns (claw, tip)."""
    x, y, ry, rot = toe
    r = math.radians(rot)
    d = ry - 0.6
    bx, by = x + d * math.sin(r), y - d * math.cos(r)
    return (bx, by, rot, length), (bx + length * math.sin(r), by - length * math.cos(r))


@cursor("pointer")
def _pointer():
    if VARIANT.get("clawed"):
        # open paw, one claw out from the left inner toe to point with
        hot = (13.5, 2.5)
        claw, (tx, ty) = toe_claw(OPEN_TOES[0], 4.2)
        base = R(-10) * S(1.1)
        px, py = base.apply(tx, ty)
        c = Cursor(hot)
        draw_paw(c, T(hot[0] - px, hot[1] - py) * base, claws=[claw])
        return c
    c = Cursor((14.5, 2.6))
    # tip of the raised toe in local coords: about (-1.8, -9.5)
    m = T(14.5, 2.6) * R(-8) * S(1.12) * T(1.8, 9.5)
    draw_paw(c, m, style="point")
    return c


@cursor("openhand")
def _openhand():
    c = Cursor((16, 16))
    if VARIANT.get("clawed"):  # every claw out
        claws = [toe_claw(t, 2.6)[0] for t in OPEN_TOES]
        draw_paw(c, T(16, 17.2) * S(1.12), claws=claws)
        return c
    draw_paw(c, T(16, 15.5) * S(1.2))
    return c


@cursor("dnd-move")
def _closedhand():
    c = Cursor((16, 16))
    draw_paw(c, T(16, 15.8) * S(1.2), style="closed")
    return c


# ---- badge cursors (small pointer paw + round badge bottom-right)
def badge(c, color, cx=23.5, cy=23.5, r=5.6):
    c.sil([C(cx, cy, r)], fill=color, ow=1.0, outline=WHITE)
    # thin dark ring outside the white ring for contrast on light backgrounds
    c.add([C(cx, cy, r + 1.0)], stroke=OUT, sw=0.6)


def badge_pointer(symbol):
    def make():
        c = Cursor((3.0, 2.5))
        base_pointer(c, scale=0.95, hot=(3.0, 2.5))
        symbol(c)
        return c
    return make


def sym_help(c):
    badge(c, BLUE)
    c.add([P("M21.4,21.9 C21.4,20.6 22.4,19.9 23.5,19.9 C24.7,19.9 25.6,20.7 25.6,21.8 "
             "C25.6,23.4 23.5,23.4 23.5,25.0")], stroke=WHITE, sw=1.5)
    c.add([C(23.5, 27.0, 0.95)], fill=WHITE)


def sym_copy(c):
    badge(c, GREEN)
    c.add([P("M23.5,20.2 V26.8 M20.2,23.5 H26.8")], stroke=WHITE, sw=1.8)


def sym_alias(c):
    badge(c, BLUE)
    c.add([P("M20.8,26.6 C20.8,22.8 22.4,21.5 25.2,21.5")], stroke=WHITE, sw=1.5)
    c.add([poly([(24.6, 19.3), (27.4, 21.5), (24.6, 23.7)])], fill=WHITE, stroke=WHITE, sw=0.6)


def sym_menu(c):
    badge(c, BLUE)
    c.add([P("M20.8,21.3 H26.2 M20.8,23.5 H26.2 M20.8,25.7 H26.2")], stroke=WHITE, sw=1.2)


def sym_nodrop(c):
    badge(c, RED)
    c.add([P("M21.1,21.1 L25.9,25.9 M25.9,21.1 L21.1,25.9")], stroke=WHITE, sw=1.7)


def sym_progress(c, frame=0, nframes=1):
    # three small beans orbiting inside a white disc
    c.sil([C(23.5, 23.5, 5.6)])
    a0 = 360.0 * frame / nframes
    for i, (r, op) in enumerate([(1.45, 1.0), (1.2, 0.7), (1.0, 0.45)]):
        a = math.radians(a0 - i * 50)
        x, y = 23.5 + 3.0 * math.sin(a), 23.5 - 3.0 * math.cos(a)
        c.add([C(x, y, r)], fill=BEAN_DARK, extra='opacity="%g"' % op)


CURSORS["help"] = badge_pointer(sym_help)
CURSORS["copy"] = badge_pointer(sym_copy)
CURSORS["alias"] = badge_pointer(sym_alias)
CURSORS["context-menu"] = badge_pointer(sym_menu)
CURSORS["no-drop"] = badge_pointer(sym_nodrop)


@cursor("dnd-no-drop")
def _dnd_no_drop():
    c = Cursor((14, 14))
    draw_paw(c, T(14, 13.5) * S(1.05), style="closed")
    sym_nodrop(c)
    return c


# ---- animated
WAIT_FRAMES = 24
PROGRESS_FRAMES = 12


def wait_frame(i):
    """Four paw prints walking around a circle, fading trail."""
    c = Cursor((16, 16))
    step = 360.0 / WAIT_FRAMES
    _, beans = paw_shapes("open")
    _, _ = beans, None
    for k in range(4):
        a = i * step - k * 62
        ar = math.radians(a)
        x, y = 16 + 8.6 * math.sin(ar), 16 - 8.6 * math.cos(ar)
        side = 1.6 if (k % 2) else -1.6  # alternate left / right feet
        x += side * math.sin(ar) * 0.6
        y -= side * math.cos(ar) * 0.6
        m = T(x, y) * R(a + 90) * S(0.5 - k * 0.03)
        fur, beans = paw_shapes("open")
        op = [1.0, 0.8, 0.6, 0.4][k]
        cc = Cursor((0, 0))
        cc.sil(fur, m, ow=0.9)
        cc.add(beans, m, fill=BEAN)
        c.body.append('<g opacity="%g">%s</g>' % (op, "".join(cc.body)))
        if k == 0:
            c.shadow.extend(cc.shadow)
    return c


def progress_frame(i):
    c = Cursor((3.0, 2.5))
    base_pointer(c, scale=0.95, hot=(3.0, 2.5))
    sym_progress(c, i, PROGRESS_FRAMES)
    return c


class BreezeCursor:
    """A Breeze Light shape used as is (same 32 canvas, nominal size 24)."""

    def __init__(self, name):
        d = os.path.join(BREEZE_DIR, name)
        with open(os.path.join(d, "metadata.json")) as f:
            meta = json.load(f)
        assert len(meta) == 1 and meta[0]["nominal_size"] == NOMINAL, name
        self.hot = (meta[0]["hotspot_x"], meta[0]["hotspot_y"])
        with open(os.path.join(d, meta[0]["filename"])) as f:
            self.text = f.read()

    def svg(self):
        return self.text


def shape_table():
    """{name: (frames, delay)} for the current VARIANT."""
    shapes = {}
    for name, fn in CURSORS.items():
        if name in VARIANT.get("breeze", ()):
            shapes[name] = ([BreezeCursor(name)], 0)
        else:
            shapes[name] = ([fn()], 0)
    shapes["wait"] = ([wait_frame(i) for i in range(WAIT_FRAMES)], 45)
    shapes["progress"] = ([progress_frame(i) for i in range(PROGRESS_FRAMES)], 70)
    return shapes


# ---- text
@cursor("text")
def _text():
    c = Cursor((16, 16))
    beam = P("M12.6,6.2 C14.6,6.2 15.6,6.8 16,7.6 C16.4,6.8 17.4,6.2 19.4,6.2 "
             "M16,7.6 V24.4 M12.6,25.8 C14.6,25.8 15.6,25.2 16,24.4 "
             "C16.4,25.2 17.4,25.8 19.4,25.8")
    c.add([beam], stroke=OUT, sw=2 * OW + 1.6)
    c.add([beam], stroke=FUR, sw=1.6)
    c.add([C(16, 16, 1.25)], fill=BEAN)
    return c


@cursor("vertical-text")
def _vtext():
    c = _text()
    c2 = Cursor((16, 16))
    c2.body = ['<g transform="rotate(90 16 16)">%s</g>' % "".join(c.body)]
    c2.shadow = ['<g transform="rotate(90 16 16)">%s</g>' % "".join(c.shadow)]
    return c2


# ---- crosshair / cell
@cursor("crosshair")
def _crosshair():
    c = Cursor((16, 16))
    lines = P("M16,4.5 V12.5 M16,19.5 V27.5 M4.5,16 H12.5 M19.5,16 H27.5")
    c.add([lines], stroke=OUT, sw=2 * OW + 1.4)
    c.add([lines], stroke=FUR, sw=1.4)
    c.add([C(16, 16, 1.0)], fill=OUT)
    mini_paw(c, 24.0, 24.2, 0.42, fill=BEAN_DARK)
    return c


@cursor("cell")
def _cell():
    c = Cursor((16, 16))
    plus = P("M13.4,6 H18.6 V13.4 H26 V18.6 H18.6 V26 H13.4 V18.6 H6 V13.4 H13.4 Z")
    c.sil([plus])
    c.add([C(16, 16, 1.6)], fill=BEAN)
    return c


@cursor("not-allowed")
def _not_allowed():
    c = Cursor((16, 16))
    c.sil([C(16, 16, 11.2)], fill=RED)
    c.add([C(16, 16, 8.2)], fill=FUR)
    mini_paw(c, 16, 16.3, 0.82)
    c.add([P("M10.2,10.2 L21.8,21.8")], stroke=RED, sw=3.0)
    return c


@cursor("pirate")
def _pirate():
    c = Cursor((16, 16))
    bone = [RECT(-9.5, -1.3, 19, 2.6, 1.2)] + [C(sx * 10.0, sy * 1.5, 1.9)
                                                for sx in (-1, 1) for sy in (-1, 1)]
    c.sil(bone, T(16, 17) * R(40))
    c.sil(bone, T(16, 17) * R(-40))
    draw_paw(c, T(16, 15.5) * S(0.8))
    return c


@cursor("x-cursor")
def _x_cursor():
    c = Cursor((16, 16))
    x = P("M8,8 L24,24 M24,8 L8,24")
    c.add([x], stroke=OUT, sw=4.2 + 2 * OW)
    c.add([x], stroke=FUR, sw=4.2)
    c.add([C(16, 16, 1.4)], fill=BEAN)
    return c


# ---- pencil / draft / color picker / zoom
def pencil(c, eraser=BEAN):
    # tip at (4, 28); axis at 45 degrees up-right
    m = T(4, 28) * R(-45)
    body = [P("M0,0 L5.0,-2.4 H22.5 A1.5,1.5 0 0 1 24,-0.9 V0.9 "
              "A1.5,1.5 0 0 1 22.5,2.4 H5.0 Z")]
    c.sil(body, m)
    c.add([P("M18.4,-2.4 H22.5 A1.5,1.5 0 0 1 24,-0.9 V0.9 A1.5,1.5 0 0 1 22.5,2.4 H18.4 Z")],
          m, fill=eraser)
    c.add([P("M0,0 L2.0,-0.95 V0.95 Z")], m, fill=OUT)
    c.add([P("M5.0,-2.4 V2.4")], m, stroke=OUT, sw=0.7)
    return m


@cursor("pencil")
def _pencil():
    c = Cursor((4, 28))
    pencil(c)
    return c


@cursor("draft")
def _draft():
    c = Cursor((4, 28))
    m = pencil(c, eraser=BEAN_DARK)
    mini_paw(c, 12.5, 0, 0.26, fill=BEAN_DARK, m=m)
    return c


@cursor("color-picker")
def _color_picker():
    c = Cursor((3.5, 28.5))
    m = T(3.5, 28.5) * R(-45)
    c.sil([P("M0,0 L3,-1.2 H13 V1.2 H3 Z"),
           RECT(12, -2.6, 3.2, 5.2, 0.8),
           P("M15,-3.6 H20 A3.6,3.6 0 0 1 20,3.6 H15 Z")], m)
    c.add([P("M15.6,-3.0 H20 A3.0,3.0 0 0 1 20,3.0 H15.6 Z")], m, fill=BEAN)
    c.add([P("M0.6,-0.25 L3,-0.6 H8 V0.6 H3 Z")], m, fill=BEAN_DARK)
    return c


def magnifier(c, sign):
    m = T(13, 13)
    c.sil([P("M6.0,4.2 L13.8,12.0 A1.9,1.9 0 0 1 11.2,14.6 L4.2,6.0 Z"),
           C(0, 0, 9.0)], m)
    c.add([C(0, 0, 6.6)], m, stroke=OUT, sw=1.1)
    c.add([C(12.2, 12.6, 1.35)], m, fill=BEAN)
    s = "M-3.4,0 H3.4" + (" M0,-3.4 V3.4" if sign == "+" else "")
    c.add([P(s)], m, stroke=OUT, sw=1.8)


@cursor("zoom-in")
def _zoom_in():
    c = Cursor((13, 13))
    magnifier(c, "+")
    return c


@cursor("zoom-out")
def _zoom_out():
    c = Cursor((13, 13))
    magnifier(c, "-")
    return c


# ---- arrows & resize
HEAD = [(0, 0), (5.6, 5.6), (2.3, 5.6), (2.3, 6.6), (-2.3, 6.6), (-2.3, 5.6), (-5.6, 5.6)]


def double_arrow(c, m, length=24, disc=True):
    """Double-headed arrow along local y, centred on origin, tips at +-length/2."""
    h = length / 2.0
    shape = poly([(0, -h), (5.4, -h + 5.6), (1.6, -h + 5.6), (1.6, h - 5.6),
                  (5.4, h - 5.6), (0, h), (-5.4, h - 5.6), (-1.6, h - 5.6),
                  (-1.6, -h + 5.6), (-5.4, -h + 5.6)])
    c.sil([shape], m)
    if disc:
        paw_disc(c, 0, 0, 4.6, m=m)


@cursor("size_ver")
def _size_ver():
    c = Cursor((16, 16))
    double_arrow(c, T(16, 16), 26)
    return c


@cursor("size_hor")
def _size_hor():
    c = Cursor((16, 16))
    double_arrow(c, T(16, 16) * R(90), 26)
    # keep the paw upright
    c.body.pop()
    c.body.pop()
    paw_disc(c, 16, 16, 4.6)
    return c


def diag(angle):
    c = Cursor((16, 16))
    double_arrow(c, T(16, 16) * R(angle), 27, disc=False)
    paw_disc(c, 16, 16, 4.6)
    return c


CURSORS["size_bdiag"] = lambda: diag(45)
CURSORS["size_fdiag"] = lambda: diag(-45)


@cursor("fleur")
def _fleur():
    c = Cursor((16, 16))
    pts = []
    h, w, s = 13.0, 4.6, 1.5   # tip distance, head half width, shaft half width
    hb = h - 4.8
    for k in range(4):
        r = R(90 * k)
        for p in [(-s, -s), (-s, -hb), (-w, -hb), (0, -h), (w, -hb), (s, -hb)]:
            pts.append(r.apply(*p))
    c.sil([poly(pts)], T(16, 16))
    paw_disc(c, 16, 16, 4.8)
    return c


@cursor("all-scroll")
def _all_scroll():
    c = Cursor((16, 16))
    tris = []
    for k in range(4):
        r = R(90 * k)
        tris.append(poly([r.apply(0, -12.5), r.apply(4.2, -8.2), r.apply(-4.2, -8.2)]))
    c.sil(tris, T(16, 16))
    paw_disc(c, 16, 16, 5.6)
    return c


def single_arrow(c, m, length=14):
    """Arrow pointing up (local), tip at origin."""
    shape = poly([(0, 0), (5.4, 5.6), (1.6, 5.6), (1.6, length), (-1.6, length),
                  (-1.6, 5.6), (-5.4, 5.6)])
    c.sil([shape], m)


def arrow_cursor(angle):
    def make():
        c = Cursor((16, 16))
        m = T(16, 16) * R(angle) * T(0, -12)
        single_arrow(c, m, 17)
        x, y = m.apply(0, 18.5)
        paw_disc(c, x, y, 4.3)
        return c
    return make


CURSORS["up-arrow"] = arrow_cursor(0)
CURSORS["right-arrow"] = arrow_cursor(90)
CURSORS["down-arrow"] = arrow_cursor(180)
CURSORS["left-arrow"] = arrow_cursor(270)


def side_cursor(angle):
    """Arrow pointing to an edge bar; angle 0 = top side."""
    def make():
        c = Cursor((16, 16))
        base = T(16, 16) * R(angle)
        # bar at local y = -13, arrow tip at -10.5 so hotspot (centre) lies on the arrow
        c.sil([RECT(-9, -14.6, 18, 2.6, 1.2)], base)
        single_arrow(c, base * T(0, -10.3), 13)
        paw_disc(c, *base.apply(0, 6.5), r=4.3)
        return c
    return make


CURSORS["top_side"] = side_cursor(0)
CURSORS["right_side"] = side_cursor(90)
CURSORS["bottom_side"] = side_cursor(180)
CURSORS["left_side"] = side_cursor(270)


def corner_cursor(angle):
    """angle 0 = top-left corner."""
    def make():
        c = Cursor((16, 16))
        base = T(16, 16) * R(angle)
        c.sil([P("M-13.5,-11.6 A1.3,1.3 0 0 1 -12.2,-12.9 H-0.5 V-10.3 H-10.9 "
                 "V0.1 H-13.5 Z")], base)
        single_arrow(c, base * T(-8.2, -7.6) * R(-45), 12)
        paw_disc(c, *base.apply(3.6, 4.2), r=4.3)
        return c
    return make


CURSORS["top_left_corner"] = corner_cursor(0)
CURSORS["top_right_corner"] = corner_cursor(90)
CURSORS["bottom_right_corner"] = corner_cursor(180)
CURSORS["bottom_left_corner"] = corner_cursor(270)


def split_cursor(vertical):
    def make():
        c = Cursor((16, 16))
        m = T(16, 16) * (R(90) if not vertical else I)
        # two bars across the middle, arrows away from them
        c.sil([RECT(-11, -3.2, 22, 2.0, 0.9), RECT(-11, 1.2, 22, 2.0, 0.9)], m, fill=BEAN)
        single_arrow(c, m * T(0, -14), 9.2)
        single_arrow(c, m * R(180) * T(0, -14), 9.2)
        return c
    return make


CURSORS["row-resize"] = split_cursor(True)
CURSORS["col-resize"] = split_cursor(False)


# -------------------------------------------------------------- name aliases
# Same alias layout as Breeze (target must be a real shape above).
ALIASES = {
    "arrow": "default", "left_ptr": "default", "top_left_arrow": "default",
    "size-bdiag": "size_bdiag", "size-fdiag": "size_fdiag",
    "size-hor": "size_hor", "size-ver": "size_ver",
    "circle": "not-allowed", "crossed_circle": "not-allowed",
    "forbidden": "no-drop",
    "closedhand": "dnd-move", "grabbing": "dnd-move", "move": "dnd-move",
    "dnd-none": "dnd-move", "fcf21c00b30f7e3f83fe0dfd12e71cff": "dnd-move",
    "4498f0e0c1937ffe01fd06f973665830": "dnd-move",
    "9081237383d90e509aa00f00170e968f": "dnd-move",
    "grab": "openhand", "hand1": "pointer", "hand2": "pointer",
    "pointing_hand": "pointer", "9d800788f1b08800ae810202380a0822": "pointer",
    "e29285e634086352946a0e7090d73106": "pointer",
    "dnd-copy": "copy", "1081e37283d90000800003c07f3ef6bf": "copy",
    "6407b0e94181790501fd1e167b474872": "copy",
    "b66166c04f8c3109214a4fbd64a50fc8": "copy",
    "link": "alias", "dnd-link": "alias",
    "3085a0e285430894940527032f8b26df": "alias",
    "640fb0e74195791501fd1ed57b41487f": "alias",
    "a2a266d0498c3104214a47bd64ab0fc8": "alias",
    "cross": "crosshair", "tcross": "crosshair", "plus": "cell",
    "e-resize": "size_hor", "w-resize": "size_hor", "ew-resize": "size_hor",
    "h_double_arrow": "size_hor", "sb_h_double_arrow": "size_hor",
    "n-resize": "size_ver", "s-resize": "size_ver", "ns-resize": "size_ver",
    "v_double_arrow": "size_ver", "sb_v_double_arrow": "size_ver",
    "00008160000006810000408080010102": "size_ver",
    "ne-resize": "size_bdiag", "sw-resize": "size_bdiag", "nesw-resize": "size_bdiag",
    "fd_double_arrow": "size_bdiag",
    "nw-resize": "size_fdiag", "se-resize": "size_fdiag", "nwse-resize": "size_fdiag",
    "bd_double_arrow": "size_fdiag",
    "size_all": "fleur",
    "split_h": "col-resize", "split_v": "row-resize",
    "sb_up_arrow": "up-arrow", "sb_down_arrow": "down-arrow",
    "sb_left_arrow": "left-arrow", "sb_right_arrow": "right-arrow",
    "ibeam": "text", "xterm": "text",
    "help": "help", "left_ptr_help": "help", "question_arrow": "help", "whats_this": "help",
    "5c6cd98b3f3ebcb1f9c7f1c204630408": "help",
    "d9ce0ab605698f320427677b458ad60b": "help",
    "watch": "wait", "half-busy": "progress", "left_ptr_watch": "progress",
    "00000000000000020006000e7e9ffc3f": "progress",
    "08e8e1c95fe2fc01f976f1e063a24ccd": "progress",
    "3ecb610c1bf2410f44200f48c40d3599": "progress",
    "03b6e0fcb3499374a867c041f52298f0": "not-allowed",
    "kill": "pirate", "X_cursor": "x-cursor",
    "draped_box": "cell", "dotbox": "cell", "target": "crosshair",
    "zoom_in": "zoom-in", "zoom_out": "zoom-out",
}


# ---------------------------------------------------------------- rendering
def render(svg_text, px):
    surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, px, px)
    ctx = cairo.Context(surf)
    h = Rsvg.Handle.new_from_data(svg_text.encode())
    r = Rsvg.Rectangle()
    r.x, r.y, r.width, r.height = 0, 0, px, px
    h.render_document(ctx, r)
    surf.flush()
    return surf


def write_xcursor(path, frames):
    """frames: list of (nominal_size, px, xhot, yhot, delay, surface)."""
    header = 16
    toc = 12 * len(frames)
    chunks, pos = [], header + toc
    entries = []
    for (size, px, xh, yh, delay, surf) in frames:
        stride = surf.get_stride()
        data = bytes(surf.get_data())
        rows = b"".join(data[y * stride:y * stride + px * 4] for y in range(px))
        chunk = struct.pack("<9I", 36, 0xfffd0002, size, 1, px, px, xh, yh, delay) + rows
        entries.append(struct.pack("<3I", 0xfffd0002, size, pos))
        chunks.append(chunk)
        pos += len(chunk)
    with open(path, "wb") as f:
        f.write(struct.pack("<4sIII", b"Xcur", header, 0x10000, len(frames)))
        f.write(b"".join(entries))
        f.write(b"".join(chunks))


def build(out):
    if os.path.exists(out):
        shutil.rmtree(out)
    scal = os.path.join(out, "cursors_scalable")
    xcur = os.path.join(out, "cursors")
    os.makedirs(scal)
    os.makedirs(xcur)

    shapes = shape_table()

    for name, (frames, delay) in shapes.items():
        d = os.path.join(scal, name)
        os.makedirs(d)
        meta = []
        for i, c in enumerate(frames):
            fn = "%s.svg" % name if len(frames) == 1 else "%s-%02d.svg" % (name, i + 1)
            with open(os.path.join(d, fn), "w") as f:
                f.write(c.svg())
            entry = {"filename": fn, "hotspot_x": c.hot[0], "hotspot_y": c.hot[1],
                     "nominal_size": NOMINAL}
            if len(frames) > 1:
                entry["delay"] = delay
            meta.append(entry)
        with open(os.path.join(d, "metadata.json"), "w") as f:
            json.dump(meta, f, indent=4)

        xframes = []
        for size in XCURSOR_SIZES:
            px = round(size * CANVAS / NOMINAL)
            k = px / CANVAS
            for c in frames:
                xframes.append((size, px, int(round(c.hot[0] * k)), int(round(c.hot[1] * k)),
                                delay or 50, render(c.svg(), px)))
        write_xcursor(os.path.join(xcur, name), xframes)

    for alias, target in ALIASES.items():
        if alias == target:
            continue
        assert target in shapes, (alias, target)
        for base in (scal, xcur):
            p = os.path.join(base, alias)
            if not os.path.lexists(p):
                os.symlink(target, p)

    with open(os.path.join(out, "index.theme"), "w") as f:
        f.write("[Icon Theme]\nName=%s\nComment=%s\nInherits=breeze_cursors\n"
                % (VARIANT["name"], VARIANT["comment"]))
    return shapes


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="Build the Cat Paw cursor theme.")
    ap.add_argument("--variant", choices=sorted(VARIANTS), default="pink")
    ap.add_argument("out", nargs="?", help="output dir (default: build/<theme dir>)")
    args = ap.parse_args()
    VARIANT = VARIANTS[args.variant]
    here = os.path.dirname(os.path.abspath(__file__))
    out = args.out or os.path.join(here, "build", VARIANT["dir"])
    shapes = build(out)
    print("built %d shapes into %s" % (len(shapes), out))
