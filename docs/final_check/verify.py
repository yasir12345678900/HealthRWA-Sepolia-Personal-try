import re,collections,sys
fn=sys.argv[1]; t=open(fn).read()
print("== marker leaks:", len(re.findall("[⟪⟫⟦⟧⟮⟯⟬⟭⦃⦄⦅⦆⧼⧽]",t)))
for m in re.finditer("[⟪⟫⟦⟧⟮⟯⟬⟭⦃⦄⦅⦆⧼⧽]",t): print("   ", t[max(0,m.start()-60):m.start()+20].replace("\n"," "))
body=t.split("\nReferences\n")[0] if "\nReferences\n" in t else t
cites=set(int(n) for g in re.findall(r"\[(\d+(?:[,–-]\s*\d+)*)\]",body) for n in re.findall(r"\d+",g))
# expand ranges like [35]–[78]
for a,b in re.findall(r"\[(\d+)\]\s*[–-]\s*\[(\d+)\]",body): cites|=set(range(int(a),int(b)+1))
print("== uncited refs 1-81:", [n for n in range(1,82) if n not in cites])
refs=re.findall(r"^\[(\d+)\] ",t.split("\nReferences\n")[-1],re.M) if "\nReferences\n" in t else []
print("== reference list entries:", len(refs), "first/last", refs[:1], refs[-1:])
eqs=[int(x) for x in re.findall(r"\((\d{1,2})\)\s*$",t,re.M)]
seq=[e for e in eqs if e<=76]
gaps=[(a,b) for a,b in zip(seq,seq[1:]) if b!=a+1 and b!=a]
print("== equation labels 1..76 present:", sorted(set(seq))==list(range(1,77)), "gaps:", gaps[:10])
for kind,mx in (("Table",17),("Figure",40)):
    caps=collections.Counter(int(x) for x in re.findall(rf"^\s*{kind} (\d+): ",t,re.M))
    print(f"== {kind} captions:", [n for n in range(1,mx+1) if caps[n]!=1], "(missing/dup)", "extra:", [n for n in caps if n>mx])
    ment=set(int(x) for x in re.findall(rf"{kind}s? (\d+)",t))
    print(f"   {kind}s mentioned but > {mx}:", sorted(n for n in ment if n>mx))
print("== AI/tool words:", re.findall(r"(?i)\b(claude|github|chatgpt|openai|as an ai)\b",t)[:5])
print("== 'Status:' lines:", [l for l in t.split("\n") if l.startswith("Status:")])
t2=re.sub(r"\n\s*\d+\s*\n","\n",t); w=re.sub(r"\s+"," ",t2).split(" ")
seen=collections.defaultdict(list)
for i in range(len(w)-12): seen[" ".join(w[i:i+12])].append(i)
out=[];last=-100
for g,p in sorted(((g,p) for g,p in seen.items() if len(p)>1),key=lambda x:x[1][0]):
    if p[0]-last>12 and not re.match(r"^(Study|Req|S\d|✓|~|×|Decision|¬|VA|VT|VP|\||is defined as)",g): out.append((g,p))
    last=p[0]
print("== 12-gram duplicate spans:", len(out))
for g,p in out: print("   ",p[:3], g[:100])
