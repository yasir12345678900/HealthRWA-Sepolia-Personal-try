"""Read-only screenshot capture for the CA2 report figures (36, 38, 39, 40).
It never clicks Sign / Revoke / Request Data Access, so the audit ledger is not changed.
Start the app first (streamlit run app.py), then:  python3 tools/report_shots.py
Env: POC_URL (default http://localhost:8501), POC_OUT (default docs/final_check/shots), CONSENT (default f050c29a-...)."""
import os, re, sys, time, subprocess
from playwright.sync_api import sync_playwright

URL = os.environ.get("POC_URL", "http://localhost:8501")
OUT = os.environ.get("POC_OUT", "docs/final_check/shots")
CID = os.environ.get("CONSENT", "f050c29a-3d92-4131-8605-63bcb1ff8d92")
os.makedirs(OUT, exist_ok=True)

def wait_idle(p, t=60):
    time.sleep(0.8)
    p.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=t * 1000)
    time.sleep(0.8)

def full_shot(p, name, width=1440):
    wait_idle(p)
    h = p.evaluate("""() => { const m=document.querySelector('[data-testid="stMain"]')||document.body;
        return m.scrollHeight + 40 }""")
    p.set_viewport_size({"width": width, "height": max(900, min(h, 14000))})
    time.sleep(1.0)
    p.screenshot(path=f"{OUT}/{name}.png", full_page=True)
    p.set_viewport_size({"width": width, "height": 900})
    print("shot", name, flush=True)

def role(p, r):
    p.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').first.click()
    p.get_by_role("option", name=r, exact=True).click()
    wait_idle(p)

def step(name, fn):
    try:
        fn(); print("OK ", name, flush=True)
    except Exception as e:
        print("FAIL", name, "->", repr(e)[:300], flush=True)

with sync_playwright() as pw:
    b = pw.chromium.launch(**({'executable_path': os.environ['CHROMIUM']} if os.environ.get('CHROMIUM') else {}))
    p = b.new_page(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
    p.goto(URL); p.wait_for_selector('[data-testid="stSidebar"]'); wait_idle(p)

    # ---- Auditor: indicators + lifecycle cards + tables for the evaluated consent
    def auditor():
        role(p, "Auditor")
        box = p.locator('[data-testid="stSelectbox"]').filter(has_text="Select Consent to Audit")
        box.click()
        p.get_by_role("option", name=CID, exact=True).click()
        wait_idle(p)
        full_shot(p, "auditor_full_page")
    step("auditor page", auditor)

    def table_fullscreen():
        df = p.locator('[data-testid="stDataFrame"]').first
        df.scroll_into_view_if_needed(); df.hover(); time.sleep(0.6)
        btn = p.locator('[data-testid="stElementToolbarButton"]').filter(has_text="").last
        clicked = False
        for sel in ['button[title="Fullscreen"]', 'button[aria-label="Fullscreen"]', '[data-testid="StyledFullScreenButton"]']:
            loc = p.locator(sel)
            if loc.count():
                loc.first.click(); clicked = True; break
        if not clicked:
            p.get_by_role("button", name=re.compile("fullscreen", re.I)).first.click()
        time.sleep(1.2)
        p.set_viewport_size({"width": 1600, "height": 1400}); time.sleep(1.2)
        p.screenshot(path=f"{OUT}/auditor_table_fullscreen.png", full_page=False)
        p.keyboard.press("Escape"); time.sleep(0.8)
        p.set_viewport_size({"width": 1440, "height": 900})
        print("shot auditor_table_fullscreen", flush=True)
    step("detailed table fullscreen", table_fullscreen)

    # ---- Doctor: look up the revoked consent (no access request is submitted)
    def doctor():
        role(p, "Doctor")
        f = p.get_by_label("Enter Authorised Consent ID", exact=True)
        f.fill(CID); f.press("Enter"); wait_idle(p)
        full_shot(p, "doctor_revoked_lookup")
    step("doctor lookup", doctor)
    b.close()

# ---- Independent verification tool: save the terminal output as text (rendered later)
try:
    r = subprocess.run([sys.executable, "-m", "tools.verify_poc"], capture_output=True, text=True, timeout=600)
    open(f"{OUT}/verify_poc_output.txt", "w").write(r.stdout + ("\n[stderr]\n" + r.stderr if r.stderr.strip() else ""))
    print("OK  verify_poc ->", OUT + "/verify_poc_output.txt", "| exit", r.returncode, flush=True)
except Exception as e:
    print("FAIL verify_poc ->", repr(e)[:300], flush=True)
print("done. Now: git add docs/final_check/shots && git commit -m 'Report screenshots' && git push")
