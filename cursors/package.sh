#!/bin/sh
# Build the cursor themes and make their release archives in dist/.
#
# Each archive has the theme directory at the top level and keeps the alias
# symlinks, so it can be installed with "Install from File..." in
# System Settings > Cursors, or extracted into ~/.icons.
# The name is <Theme>-<version>.tar.gz, with the version read from VERSIONS.
#
# Usage: ./package.sh [THEME ...]    (default: every theme in VERSIONS)
set -eu

root=$(cd "$(dirname "$0")" && pwd)
outdir="$root/dist"
themes=${*:-$(sed -n 's/^\([A-Za-z0-9_-]*\)=.*/\1/p' "$root/VERSIONS")}
mkdir -p "$outdir"

for name in $themes; do
    version=$(sed -n "s/^$name=//p" "$root/VERSIONS")
    [ -n "$version" ] || { echo "$name: no version in VERSIONS" >&2; exit 1; }
    case "$name" in
        PastelPaws) (cd "$root/PastelPaws" && python3 build.py >/dev/null) ;;
        CatPaw) (cd "$root/CatPaw" && python3 build.py >/dev/null) ;;
        *) echo "$name: unknown theme" >&2; exit 1 ;;
    esac
    src="$root/$name/build"
    [ -f "$src/$name/index.theme" ] || { echo "$name: build failed" >&2; exit 1; }
    out="$outdir/$name-$version.tar.gz"
    rm -f "$out"
    tar -C "$src" --sort=name --owner=0 --group=0 --numeric-owner -czf "$out" "$name"
    echo "$out ($(du -h "$out" | cut -f1))"
done
