#!/usr/bin/env python3
"""Contact sheet of every shape: 1x and 3x, on light and dark backgrounds.

Usage: python3 preview.py out.png [zoom] [pink|grey|soft]
A small cyan cross marks the hotspot on the zoomed copies.
"""
import os
import sys

import cairo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build  # noqa: E402

out = sys.argv[1] if len(sys.argv) > 1 else "preview.png"
Z = int(sys.argv[2]) if len(sys.argv) > 2 else 3
build.VARIANT = build.VARIANTS[sys.argv[3] if len(sys.argv) > 3 else "pink"]

items, anim = [], []
for n, (frames, _) in build.shape_table().items():
    if len(frames) == 1:
        items.append((n, frames[0]))
    else:
        for i in (0, len(frames) // 3):
            anim.append(("%s#%d" % (n, i), frames[i]))
items += anim

cols = 6
cell_w, cell_h = 32 * Z + 32 + 30, 32 * Z * 2 + 40
rows = (len(items) + cols - 1) // cols
surf = cairo.ImageSurface(cairo.FORMAT_ARGB32, cols * cell_w, rows * cell_h)
ctx = cairo.Context(surf)
ctx.set_source_rgb(0.85, 0.85, 0.85)
ctx.paint()
for idx, (name, c) in enumerate(items):
    x0, y0 = (idx % cols) * cell_w, (idx // cols) * cell_h
    svg = c.svg()
    for row, bg in enumerate([(0.98, 0.98, 0.98), (0.16, 0.17, 0.19)]):
        y = y0 + row * (32 * Z + 8)
        ctx.set_source_rgb(*bg)
        ctx.rectangle(x0 + 4, y + 4, cell_w - 8, 32 * Z + 4)
        ctx.fill()
        for (px, ox) in [(32, 8), (32 * Z, 8 + 32 + 10)]:
            s = build.render(svg, px)
            ctx.set_source_surface(s, x0 + ox, y + 6)
            ctx.paint()
            if px != 32:
                k = px / 32
                hx, hy = x0 + ox + c.hot[0] * k, y + 6 + c.hot[1] * k
                ctx.set_source_rgb(0, 0.8, 1)
                ctx.set_line_width(1)
                ctx.move_to(hx - 4, hy); ctx.line_to(hx + 4, hy)
                ctx.move_to(hx, hy - 4); ctx.line_to(hx, hy + 4)
                ctx.stroke()
    ctx.set_source_rgb(0, 0, 0)
    ctx.select_font_face("Sans")
    ctx.set_font_size(12)
    ctx.move_to(x0 + 8, y0 + cell_h - 10)
    ctx.show_text(name)
surf.write_to_png(out)
print(out)
