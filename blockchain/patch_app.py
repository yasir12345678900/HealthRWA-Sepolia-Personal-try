'''Idempotent patcher: wires on-chain mode (Sepolia) into app.py.
Run from the repo root:  python3 blockchain/patch_app.py
'''
import sys

src = open("app.py", encoding="utf-8").read()
if "onchain_ui" in src:
    print("======= ON-CHAIN UI ALREADY WIRED IN app.py =======")
    sys.exit(0)
lines = src.split("\n")


def find(pred, start=0):
    for i in range(start, len(lines)):
        if pred(lines[i]):
            return i
    return None


i = find(lambda l: l.strip() == "import streamlit as st")
if i is None:
    print("======= PATCH FAILED: no 'import streamlit as st' line =======")
    sys.exit(1)
lines.insert(i + 1, "from blockchain import onchain_ui  # on-chain mode (Sepolia)")

j = find(lambda l: l.startswith("role = st.sidebar.selectbox("))
if j is not None:
    k = find(lambda l: l.strip() == ")", j)
    if k is not None:
        lines.insert(k + 1, "onchain_ui.render_chain_badge()")
else:
    print("(sidebar badge skipped - role selectbox not found)")

b = find(lambda l: l.strip() == "st.balloons()")
if b is not None:
    indent = lines[b][: len(lines[b]) - len(lines[b].lstrip())]
    e = find(lambda l: "unsafe_allow_html=True)" in l, b)
    lines.insert((e if e is not None else b) + 1, indent + "onchain_ui.render_onchain_mint(consent, audit_db)")
else:
    print("======= PATCH FAILED: st.balloons() anchor (guardian mint block) not found =======")
    sys.exit(1)

out = "\n".join(lines)
compile(out, "app.py", "exec")
open("app.py", "w", encoding="utf-8").write(out)
print("======= ON-CHAIN UI WIRED INTO app.py OK =======")
