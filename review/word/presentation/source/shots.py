# Crops of the HALAH screenshots for the deck (the report keeps the full images).
from PIL import Image
import numpy as np
S = "v3/r5/shots/"; F = "deck/fig/"

def rows_with_content(im, thr=40):
    a = np.asarray(im.convert("RGB")).astype(int)
    bg = a[5, a.shape[1] - 5]
    d = np.abs(a - bg).sum(axis=2)
    return (d > thr).sum(axis=1) > 3, d

def blocks(im, gap=90):
    rows, _ = rows_with_content(im)
    out, start, last = [], None, None
    for y, r in enumerate(rows):
        if r:
            if start is None: start = y
            elif y - last > gap: out.append((start, last)); start = y
            last = y
    if start is not None: out.append((start, last))
    return out

def bbox_x(im, y0, y1, thr=40):
    _, d = rows_with_content(im.crop((0, y0, im.width, y1)))
    cols = np.where((d > thr).sum(axis=0) > 1)[0]
    return int(cols.min()), int(cols.max())

# 7.1 and 7.2: drop the HALAH banner and the empty band above the subsystem heading
Image.open(S + "image1.png").crop((0, 835, 1534, 1885)).save(F + "f7_1c.png")
Image.open(S + "image2.png").crop((0, 835, 1534, 1972)).save(F + "f7_2c.png")
# 7.3: from 'Consent Information' to the end (state, decision matrix, authorised scope)
Image.open(S + "image3.png").crop((0, 1135, 1534, 2426)).save(F + "f7_3c.png")
# 7.4: request, decision banner and the first MEDICATION rows
Image.open(S + "image4_final.png").crop((0, 0, 1530, 1250)).save(F + "f7_4c.png")

# 7.5: six lifecycle events in time order, 3 across x 2 down
im5 = Image.open(S + "image5.png"); im5b = Image.open(S + "image5b.png")
bl = blocks(im5)
print("blocks in image5:", bl)
ev = []
for k, (y0, y1) in enumerate(bl):
    if k == 0: y0 = 155                 # first block starts under the 'Consent Lifecycle' heading
    x0, x1 = bbox_x(im5, y0, y1 + 1)
    ev.append(im5.crop((max(0, x0 - 14), y0 - 14, x1 + 16, y1 + 16)))
bb = blocks(im5b, gap=200)
y0, y1 = bb[0][0], bb[-1][1]
x0, x1 = bbox_x(im5b, y0, y1 + 1)
ev.append(im5b.crop((max(0, x0 - 14), y0 - 14, x1 + 16, y1 + 16)))
print("events:", [e.size for e in ev])
assert len(ev) == 6
bgc = tuple(np.asarray(im5.convert("RGB"))[5, im5.width - 5])
pad, gx, gy, top = 40, 70, 70, 70   # top: room for the numbered chips drawn in PowerPoint
cw = [max(ev[c].width, ev[c + 3].width) for c in range(3)]
rh = [max(e.height for e in ev[:3]), max(e.height for e in ev[3:])]
W = pad * 2 + sum(cw) + gx * 2; H = pad + top * 2 + sum(rh) + gy
g = Image.new("RGB", (W, H), bgc)
pos = []
def flatten(e):
    # the app background has a faint gradient; set near-background pixels to one colour so the pasted blocks match
    a = np.asarray(e.convert("RGB")).astype(int)
    loc = a[3, 3]
    mask = np.abs(a - loc).sum(axis=2) < 24
    a[mask] = bgc
    return Image.fromarray(a.astype("uint8"))
ev = [flatten(e) for e in ev]
for i, e in enumerate(ev):
    r, c = divmod(i, 3)
    x = pad + sum(cw[:c]) + gx * c
    y = top + (rh[0] + gy + top) * r
    g.paste(e, (x, y)); pos.append((x, y, e.width, e.height))
g.save(F + "f7_5g.png")
import json
json.dump({"size": [W, H], "pos": pos, "top": top}, open(F + "f7_5g.json", "w"))
print("grid", g.size, pos)
