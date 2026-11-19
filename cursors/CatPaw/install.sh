#!/bin/sh
# Build the theme and install it for the current user.
# Usage: ./install.sh [pink|grey|soft]    (default: pink)
set -e
cd "$(dirname "$0")"
variant=${1:-pink}
case "$variant" in
    pink) theme=CatPaw ;;
    grey) theme=CatPawGrey ;;
    soft) theme=CatPawSoft ;;
    *) echo "unknown variant: $variant (pink, grey or soft)" >&2; exit 1 ;;
esac
python3 build.py --variant "$variant"
rm -rf "$HOME/.local/share/icons/$theme"
cp -a "build/$theme" "$HOME/.local/share/icons/"
# plasma-apply-cursortheme / the KCM only scan ~/.icons, not ~/.local/share/icons
mkdir -p "$HOME/.icons"
ln -sfn "../.local/share/icons/$theme" "$HOME/.icons/$theme"
echo "Installed. Apply with: plasma-apply-cursortheme $theme"
