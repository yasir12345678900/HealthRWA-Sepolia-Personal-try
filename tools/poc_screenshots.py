"""End-to-end browser walkthrough of HALAH (Patient -> Guardian x2 -> Doctor -> Revoke -> Auditor) with full-page
screenshots. Start the app first (streamlit run app.py), then:  python3 tools/poc_screenshots.py
Env: POC_URL (default http://localhost:8501), POC_OUT (default evidence/poc_2026-09-24), CHROMIUM (optional browser path)."""
import os, re, sys, time, json
from playwright.sync_api import sync_playwright, expect
OUT = os.environ.get("POC_OUT", "evidence/poc_2026-09-24")
os.makedirs(OUT, exist_ok=True)
URL = os.environ.get("POC_URL", "http://localhost:8501")
state = {}

def wait_idle(p, t=60):
    time.sleep(0.8)
    p.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=t*1000)
    time.sleep(0.6)

def shot(p, name):
    wait_idle(p)
    h = p.evaluate("""() => { const m=document.querySelector('[data-testid="stMain"]')||document.body;
        return Math.max(m.scrollHeight, document.querySelector('[data-testid="stSidebarContent"]')?.scrollHeight||0) + 40 }""")
    p.set_viewport_size({"width": 1440, "height": max(900, min(h, 12000))})
    time.sleep(0.8)
    p.screenshot(path=f"{OUT}/{name}.png", full_page=True)
    p.set_viewport_size({"width": 1440, "height": 900})
    print("shot", name, h, flush=True)

def role(p, r):
    p.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').first.click()
    p.get_by_role("option", name=r, exact=True).click()
    wait_idle(p)

def fill(p, label, value, enter=True):
    f = p.get_by_label(label, exact=True)
    f.fill(value)
    if enter: f.press("Enter" if f.evaluate("e=>e.tagName")=="INPUT" else "Control+Enter")
    wait_idle(p)

def multiselect(p, label, options):
    box = p.locator('[data-testid="stMultiSelect"]').filter(has_text=label)
    for attempt in range(4):
        (box.get_by_role("button", name="Open") if attempt % 2 == 0 else box.get_by_role("combobox")).click()
        try:
            p.get_by_role("option", name=options[0], exact=True).wait_for(timeout=4000); break
        except Exception:
            p.keyboard.press("Escape"); time.sleep(1)
    p.get_by_role("option", name="Select all", exact=True).click(); time.sleep(1)
    p.keyboard.press("Escape"); wait_idle(p)

def click(p, name, **kw):
    p.get_by_role("button", name=name, **kw).first.click(); wait_idle(p, 120)

with sync_playwright() as pw:
    b = pw.chromium.launch(**({'executable_path': os.environ['CHROMIUM']} if os.environ.get('CHROMIUM') else {}))
    p = b.new_page(viewport={"width": 1440, "height": 900})
    p.goto(URL); p.wait_for_selector('[data-testid="stSidebar"]'); wait_idle(p)
    shot(p, "01_patient_home_chain_connected")

    # validation: no scope
    click(p, "Initial Consent")
    shot(p, "02_patient_validation_empty_scope")

    multiselect(p, "Data Access Scope", ["Observation", "Medication", "Condition", "Procedure"])
    click(p, "Initial Consent")
    txt = p.locator(".blockchain-badge").inner_text()
    cid = re.search(r"Consent ID:\s*([0-9a-f-]{36})", txt).group(1); state["cid"] = cid
    shot(p, "03_patient_consent_created")

    role(p, "Guardian")
    fill(p, "Enter Target Consent ID", cid)
    shot(p, "04_guardian_consent_found")
    click(p, "Sign Consent via VC")
    shot(p, "05_guardian_A_eip712_signed_1of2")
    p.locator('[data-testid="stSelectbox"]').filter(has_text="Guardian DID").click()
    p.get_by_role("option", name="did:parent:B").click(); wait_idle(p)
    click(p, "Sign Consent via VC")
    shot(p, "06_guardian_B_signed_2of2_sbt_mint_started")
    time.sleep(8)
    p.reload(); p.wait_for_selector('[data-testid="stSidebar"]'); wait_idle(p)
    role(p, "Guardian"); fill(p, "Enter Target Consent ID", cid)
    shot(p, "07_guardian_anchored_onchain_token")

    role(p, "Doctor")
    fill(p, "Enter Authorised Consent ID", cid)
    shot(p, "08_doctor_decision_matrix_all_pass")
    click(p, "Request Data Access")
    shot(p, "09_doctor_empty_request_scope_blocked")
    multiselect(p, "Select Request Scope", ["Observation", "Medication", "Condition", "Procedure"])
    click(p, "Request Data Access")
    p.wait_for_selector("text=Access Granted", timeout=120000)
    shot(p, "10_doctor_groth16_zk_access_granted_records")

    p.locator('[data-testid="stSelectbox"]').filter(has_text="Requester jurisdiction").click()
    p.get_by_role("option", name="US", exact=True).click(); wait_idle(p)
    click(p, "Request Data Access")
    shot(p, "11_doctor_jurisdiction_US_denied_VL_fail")

    role(p, "Patient")
    shot(p, "12_patient_my_consents_active")
    p.locator('[data-testid="stHorizontalBlock"]').filter(has_text=cid[:8]).get_by_role("button", name="Revoke").click(); wait_idle(p, 120)
    shot(p, "13_patient_revoked_onchain")

    role(p, "Doctor"); fill(p, "Enter Authorised Consent ID", cid)
    shot(p, "14_doctor_after_revoke_denied")

    role(p, "Auditor")
    shot(p, "15_auditor_lifecycle_and_ledger")
    b.close()
print(state)
