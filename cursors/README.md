# Cursor themes

Four cat-paw cursor themes for KDE Plasma 6. Both ship scalable SVG cursors
(`cursors_scalable/`, used by KWin since Plasma 6.2) plus an XCursor fallback
(`cursors/`, 24 to 96 px) for XWayland, GTK and Electron apps.

| Theme | Look |
|---|---|
| [Pastel Paws](PastelPaws/) | pastel white-and-lavender paws with pink beans, teardrop pointer |
| [Cat Paw](CatPaw/) | white paws with pink beans and a dark outline, Breeze Light style |
| [Cat Paw Grey](CatPaw/) | the same shapes as a grey cat: grey paws with dark grey beans |
| [Cat Paw Soft](CatPaw/) | white paws with pink beans and a thin outline, clawed pointer and open hand, Breeze Light text and cross cursors |

Each folder has its own `build.py` that generates every shape, so edit the
script and rebuild instead of editing the SVGs.

## Install

Download a release archive and use **Install from File…** in
System Settings → Colors & Themes → Cursors, or extract it into `~/.icons`.
The cursor settings page does not look in `~/.local/share/icons`.

## Release archives

```
./package.sh            # builds every theme -> dist/<Theme>-<version>.tar.gz
./package.sh CatPaw     # only one theme
```

Versions are in `VERSIONS`.
