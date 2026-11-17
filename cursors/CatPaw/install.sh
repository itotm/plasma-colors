#!/bin/sh
# Build the theme and install it for the current user.
set -e
cd "$(dirname "$0")"
python3 build.py
rm -rf "$HOME/.local/share/icons/CatPaw"
cp -a build/CatPaw "$HOME/.local/share/icons/"
# plasma-apply-cursortheme / the KCM only scan ~/.icons, not ~/.local/share/icons
mkdir -p "$HOME/.icons"
ln -sfn ../.local/share/icons/CatPaw "$HOME/.icons/CatPaw"
echo "Installed. Apply with: plasma-apply-cursortheme CatPaw"
