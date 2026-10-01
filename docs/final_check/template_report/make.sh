#!/bin/bash
# assemble blocks -> build -> PDF -> page numbers for Contents -> rebuild
set -e
cd /tmp/claude-0/short
node build_short.js > build.log 2>&1 || { cat build.log; exit 1; }
soffice --headless --convert-to pdf CA2_short.docx >/dev/null 2>&1
python3 - <<'PY'
import subprocess, json, re
pages=subprocess.run(["pdftotext","-layout","CA2_short.pdf","-"],capture_output=True,text=True).stdout.split("\f")
toc=json.load(open("build_report.json"))["toc"]
sq=lambda s: re.sub(r'[^a-z0-9]','',s.lower())
out={}; cur=2
for t in toc:
    if t=="References":
        cand=[i for i,p in enumerate(pages) if i>cur and re.search(r'^\s*References\s*$',p,re.M) and '[1]' in p]
    else:
        num,title=t.split('. ',1)
        cand=[i for i,p in enumerate(pages) if i>=cur and re.search(r'^\s*'+re.escape(num)+r'\.\s+',p,re.M) and sq(title)[:40] in sq(p)]
    if cand: out[t]=cand[0]+1; cur=cand[0]
    else: print("TOC MISS",t)
json.dump(out,open("toc.json","w")); print("toc",len(out),"of",len(toc))
PY
node build_short.js toc.json > build.log 2>&1 && cat build.log
soffice --headless --convert-to pdf CA2_short.docx >/dev/null 2>&1
pdftotext -layout CA2_short.pdf CA2_short.txt
echo "pages: $(pdfinfo CA2_short.pdf | awk '/Pages/{print $2}')"
