#!/bin/bash
# Contact sheet of all cursors: big (x4) on light and dark, and at real size (24 px setting)
set -e
B=build/PastelPaws/cursors_scalable
T=$(mktemp -d)
for d in $B/*/; do n=$(basename $d); [ -L "${d%/}" ] && continue
  f=$(ls $d*.svg | head -1)
  magick -background none -density 384 rsvg:$f -resize 128x128! $T/$n-big.png
  magick -background none rsvg:$f $T/$n-1x.png
  magick -size 136x136 xc:'#f4f1ee' $T/$n-big.png -gravity center -composite \
    \( -size 136x136 xc:'#2b2d31' $T/$n-big.png -gravity center -composite \) +append \
    \( -size 40x136 xc:'#f4f1ee' $T/$n-1x.png -gravity center -composite \) +append \
    \( -size 40x136 xc:'#2b2d31' $T/$n-1x.png -gravity center -composite \) +append \
    -gravity south -background white -splice 0x18 -pointsize 14 -annotate +0+1 "$n" $T/$n-tile.png
done
magick montage $T/*-tile.png -tile 4x -geometry +6+6 -background white ${1:-preview.png}
rm -rf $T
