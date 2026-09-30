#!/bin/bash
# render.sh deck.pptx outdir  -> outdir/slide-NN.png
set -e
DECK=$(realpath $1); OUT=$(realpath -m $2); SK=/root/.claude/skills/synced/00578ed4-301e-40ae-af05-0dbb005ee2ab_49610a22-0858-4237-b254-3a64e4f62ac5/pptx/scripts/office
mkdir -p $OUT; rm -f $OUT/*.png $OUT/*.pdf
python3 $SK/soffice.py --headless --convert-to pdf --outdir $OUT $DECK >/dev/null 2>&1
python3 - "$OUT" <<'PY'
import sys, glob, pymupdf
out=sys.argv[1]; pdf=glob.glob(out+"/*.pdf")[0]
doc=pymupdf.open(pdf)
for i,p in enumerate(doc): p.get_pixmap(dpi=90).save(f"{out}/slide-{i+1:02d}.png")
print(len(doc), "pages")
PY
