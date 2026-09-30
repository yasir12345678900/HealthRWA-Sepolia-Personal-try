#!/usr/bin/env python3
"""Apply reviewer findings: kind fix/cite -> pink ⦅…⦆ in place; kind add -> blue ⦃…⦄ new paragraph
(or appended sentence when the anchor lives in a HUMAN override).
usage: apply_pink.py findings.json [--dry]  (env SKIP=id1,id2 to skip)"""
import json, re, sys, os
DRY = "--dry" in sys.argv
SKIP = set(filter(None, os.environ.get("SKIP", "").split(",")))
MKS = "⟪⟫⟦⟧⟮⟯⟬⟭⦃⦄⦅⦆"
MK = "[" + MKS + "~_*]*"
PINK, BLUE = ("⦅", "⦆"), ("⦃", "⦄")
SRC = {f: f"ch_{f}_fixed.json" for f in "ABCDEF"}; SRC["I"] = "impl_blocks.json"
for f in "ABCF": SRC["T" + f] = f"tables_{f}.json"
blocks = {k: json.load(open(v)) for k, v in SRC.items()}
human = json.load(open("human_all.json"))

def norm(s):
    return (s.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
             .replace("–", "-").replace("—", "-").replace(" ", " "))

def pat(cur):
    cur = norm(cur.strip())
    parts = []
    for ch in cur:
        if ch.isspace(): parts.append(r"\s*" + MK)
        elif ch == "'": parts.append("[’‘']" + MK)
        elif ch == '"': parts.append("[“”\"]" + MK)
        elif ch == "-": parts.append("[-–—]" + MK)
        else: parts.append(re.escape(ch) + MK)
    return re.compile(MK + "".join(parts))

SUBS = [(r"\bV([IAPTLS])\b", r"V~\1~"), (r"\bS([CR])\b", r"S~\1~"), (r"\bP([RCu])\b", r"P~\1~"),
        (r"\bA(v)\b", r"A~\1~"), (r"\bt([se])\b", r"t~\1~"), (r"\bI(p)\b", r"I~\1~"), (r"\bid(C)\b", r"id~\1~")]
def subs(rep):
    for a, b in SUBS: rep = re.sub(a, b, rep)
    return rep
def sub_span(text, m, repl, wrap):
    span = text[m.start():m.end()]
    marks = "".join(c for c in span if c in MKS)
    # markers inside the span are re-emitted after the wrapper so every pair stays balanced
    if repl == "": return text[:m.start()] + marks + text[m.end():]
    return text[:m.start()] + wrap[0] + subs(repl) + wrap[1] + marks + text[m.end():]

def fields(b):
    for k in ("text", "title", "caption", "require", "ensure"):
        if isinstance(b.get(k), str): yield k, None
    if isinstance(b.get("lines"), list):
        for i in range(len(b["lines"])): yield "lines", i
    if isinstance(b.get("rows"), list):
        for i, r in enumerate(b["rows"]):
            for j in range(len(r)): yield "rows", (i, j)

def get(b, k, i):
    if i is None: return b[k]
    if k == "lines": return b[k][i]
    return b[k][i[0]][i[1]]

def put(b, k, i, v):
    if i is None: b[k] = v
    elif k == "lines": b[k][i] = v
    else: b[k][i[0]][i[1]] = v

def find(cur):
    """yield (where, getter, setter) for every place `cur` occurs"""
    p = pat(cur)
    hits = []
    for f, bl in blocks.items():
        for bi, b in enumerate(bl):
            for k, i in fields(b):
                v = get(b, k, i)
                if isinstance(v, str) and p.search(v):
                    hits.append((f"{f}{bi}.{k}", (f, bi, k, i)))
    for hk, hv in human.items():
        if isinstance(hv, str) and p.search(hv):
            hits.append((f"H{hk}", ("H", hk)))
    return p, hits

log = []
items = json.load(open(sys.argv[1]))
for it in items:
    iid = it.get("id")
    if iid == "SUMMARY" or iid in SKIP: continue
    kind = it.get("kind", "fix")
    if kind == "style" and it.get("whole_paragraph"):
        cur, rep = it.get("current", ""), it.get("replacement", "")
        if not cur or not rep: log.append((iid, "SKIP-empty")); continue
        p, hits = find(cur)
        if it.get("only"): hits = [h for h in hits if h[0].startswith(it["only"])]
        if len(hits) == 0: log.append((iid, "NOMATCH", cur[:60])); continue
        if len(hits) > 1: log.append((iid, "MULTI", [h[0] for h in hits])); continue
        where, loc = hits[0]
        if not DRY:
            if loc[0] == "H": human[loc[1]] = PINK[0] + subs(rep) + PINK[1]
            else:
                f, bi, k, i = loc; b = blocks[f][bi]
                if k == "text" and i is None: b["text"] = PINK[0] + subs(rep) + PINK[1]
                else: log.append((iid, "SKIP-nonpara", where)); continue
        log.append((iid, "OK-para", where)); continue
    if kind == "style": kind = "fix"
    if kind in ("fix", "cite"):
        cur, rep = it.get("current", ""), it.get("replacement", "")
        if not cur: log.append((iid, "SKIP-empty")); continue
        p, hits = find(cur)
        if len(hits) == 0: log.append((iid, "NOMATCH", cur[:60])); continue
        if it.get("only"): hits = [h for h in hits if h[0].startswith(it["only"])]
        if len(hits) > 1 and not it.get("all"): log.append((iid, "MULTI", [h[0] for h in hits])); continue
        def fixall(v):
            while True:
                m = p.search(v)
                if not m: return v
                v2 = sub_span(v, m, rep, PINK)
                if not it.get("all"): return v2
                # continue after the inserted wrapper
                head = v[:m.start()] + PINK[0] + subs(rep) + PINK[1]
                tail = fixall(v2[len(head):]) if rep else v2[len(head):]
                return head + tail
        for where, loc in hits:
            if not DRY:
                if loc[0] == "H": human[loc[1]] = fixall(human[loc[1]])
                else:
                    f, bi, k, i = loc; b = blocks[f][bi]; put(b, k, i, fixall(get(b, k, i)))
            log.append((iid, "OK-pink", where))
    elif kind == "add":
        anc, rep = it.get("after", ""), it.get("replacement", "")
        if not anc or not rep: log.append((iid, "SKIP-empty")); continue
        p, hits = find(anc)
        if len(hits) == 0: log.append((iid, "NOMATCH", anc[:60])); continue
        if len(hits) > 1: log.append((iid, "MULTI", [h[0] for h in hits])); continue
        where, loc = hits[0]
        if not DRY:
            if loc[0] == "H":
                human[loc[1]] = human[loc[1]].rstrip() + " " + BLUE[0] + subs(rep) + BLUE[1]
            else:
                f, bi, k, i = loc; b = blocks[f][bi]
                if b["t"] == "p" and k == "text":
                    blocks[f].insert(bi + 1, {"t": "p", "text": BLUE[0] + subs(rep) + BLUE[1]})
                else:  # heading/caption/table anchor: append a sentence after that block as a paragraph
                    blocks[f].insert(bi + 1, {"t": "p", "text": BLUE[0] + subs(rep) + BLUE[1]})
        log.append((iid, "OK-blue", where))
    else:
        log.append((iid, "SKIP-kind", kind))

for l in log: print(*l)
if not DRY:
    for f, fn in SRC.items(): json.dump(blocks[f], open(fn, "w"), ensure_ascii=False, indent=1)
    json.dump(human, open("human_all.json", "w"), ensure_ascii=False, indent=1)
    print("written")
