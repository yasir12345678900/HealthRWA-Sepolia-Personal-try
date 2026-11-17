"""The screens of the running application as tools/final_run.py drives them in a browser (Playwright).

One function for each action a person makes: create a consent on the Patient screen, approve and revoke on the
Guardian screen, request and attest on the Clinician screen, revoke and take over under "My Consents", and select a
consent on the Auditor screen. Every action starts from a newly loaded page, so no selection of an earlier action is
left in a field. A function returns when the page has finished its run. What a click did is read by the caller from
the audit ledger, never from the text of the page."""
import re
import time


class Screens:
    def __init__(self, page, url, shots_dir, say=print):
        self.p, self.url, self.shots, self.say = page, url, shots_dir, say

    # ---- the page ----------------------------------------------------------------------------------
    def idle(self, seconds=240):
        """Wait until the application has finished the run that the last action started."""
        time.sleep(0.8)
        self.p.wait_for_function("() => !document.querySelector('[data-testid=\"stStatusWidget\"]')", timeout=seconds * 1000)
        time.sleep(0.6)

    def open(self, role="Patient"):
        """Load the page anew (a new session of the application) and choose the role."""
        self.p.goto(self.url)
        self.p.wait_for_selector('[data-testid="stSidebar"]', timeout=120000)
        self.idle()
        if role != "Patient":
            self.p.locator('[data-testid="stSidebar"] [data-testid="stSelectbox"]').first.click()
            self.p.get_by_role("option", name=role, exact=True).click()
            self.idle()

    def shot(self, name):
        """A screenshot of the whole page, saved as <name>.png in the folder of the screenshots."""
        if not name:
            return None
        self.idle()
        height = self.p.evaluate("""() => { const m = document.querySelector('[data-testid="stMain"]') || document.body;
            return Math.max(m.scrollHeight, document.querySelector('[data-testid="stSidebarContent"]')?.scrollHeight || 0) + 40 }""")
        self.p.set_viewport_size({"width": 1440, "height": max(900, min(height, 9000))})
        time.sleep(0.6)
        path = f"{self.shots}/{name[:-4] if name.endswith('.png') else name}.png"
        self.p.screenshot(path=path, full_page=True)
        self.p.set_viewport_size({"width": 1440, "height": 900})
        self.say(f"    screenshot {path.rsplit('/', 1)[-1]}")
        return path

    def text(self):
        return self.p.locator('[data-testid="stMain"]').inner_text()

    def wait_text(self, pattern, seconds=300):
        self.p.wait_for_selector(f"text=/{pattern}/", timeout=seconds * 1000)
        self.idle()

    # ---- the widgets ---------------------------------------------------------------------------------
    def fill(self, label, value):
        field = self.p.get_by_label(label, exact=True)
        field.fill(str(value))
        field.press("Enter" if field.evaluate("e => e.tagName") == "INPUT" else "Control+Enter")
        self.idle()

    def value(self, label):
        return self.p.get_by_label(label, exact=True).input_value()

    def pick(self, label, option):
        """Choose one option of a select box. The option is typed first, so a long list shows it."""
        box = self.p.locator('[data-testid="stSelectbox"]').filter(has_text=label).first
        box.scroll_into_view_if_needed()
        if box.locator(f'text="{option}"').count() and box.inner_text().strip().endswith(option):
            return                                           # it is the selected value already
        box.click()
        choice = self.p.get_by_role("option", name=option, exact=True)
        if choice.count() == 0 or not choice.first.is_visible():
            self.p.keyboard.type(option, delay=5)
            time.sleep(0.5)
        choice.first.click()
        self.idle()

    def options(self, label):
        """Open a select box and return the options it offers. The list stays open for a screenshot."""
        box = self.p.locator('[data-testid="stSelectbox"]').filter(has_text=label).first
        box.scroll_into_view_if_needed()
        box.click()
        time.sleep(0.8)
        return [o.inner_text().strip() for o in self.p.get_by_role("option").all()]

    def drives_multiselect(self):
        """Open the Patient screen and say whether its scope field is the multiselect that `chosen` and `choose`
        read: the one that Streamlit 1.67.0 draws, with its selected values as tags inside a combo box."""
        self.open("Patient")
        return self.p.locator('[data-testid="stMultiSelect"] .react-aria-ComboBox').count() > 0

    def chosen(self, label):
        box = self.p.locator('[data-testid="stMultiSelect"]').filter(has_text=label)
        return [t.get_attribute("aria-label") for t in box.locator('.react-aria-ComboBox [data-tag]').all()]

    def choose(self, label, options):
        """Set a multiselect to exactly these options, and check that it holds them."""
        options = list(options)
        box = self.p.locator('[data-testid="stMultiSelect"]').filter(has_text=label)
        box.scroll_into_view_if_needed()
        while self.chosen(label):                            # empty it first: Backspace removes the last value
            box.get_by_role("combobox").click()
            self.p.keyboard.press("Backspace")
            time.sleep(0.5)
        self.p.keyboard.press("Escape")
        self.idle()
        for name in options:
            option = self.p.get_by_role("option", name=name, exact=True)
            if option.count() == 0 or not option.first.is_visible():
                box.get_by_role("combobox").click()
                time.sleep(0.6)
            option.click()
            time.sleep(0.6)
        self.p.keyboard.press("Escape")
        self.idle()
        if self.chosen(label) != options:
            raise RuntimeError(f"the field '{label}' holds {self.chosen(label)} and not {options}")

    def click(self, name, exact=True):
        self.p.get_by_role("button", name=name, exact=exact).first.click()
        self.idle()

    def row_button(self, consent_id, name):
        """The button `name` in the row of a consent under "My Consents"."""
        row = self.p.locator('[data-testid="stHorizontalBlock"]').filter(has_text=consent_id[:8] + "...")
        return row.get_by_role("button", name=name, exact=True)

    # ---- Patient screen --------------------------------------------------------------------------------
    def create(self, spec, shot_form=None, shot_done=None):
        """Fill the form "Create Smart Consent Contract" and click "Initial Consent". `spec` holds patient,
        clinician, guardians, threshold, scope, context, start, expiry and, when the consent has them, birth_date
        and trigger. Returns the consent identifier read from the badge, or None when the form answered with an error."""
        self.open("Patient")
        self.pick("Patient DID (Identity Pointer)", spec["patient"])
        if self.value("Authorised Clinician DID") != spec["clinician"]:
            self.fill("Authorised Clinician DID", spec["clinician"])
        if spec.get("context", "AU") != "AU":
            self.pick("Consent Context (jurisdiction code)", spec["context"])
        self.choose("Data Access Scope (EMR Modules)", spec["scope"])
        if spec.get("birth_date"):
            self.fill("Patient Date of Birth (YYYY-MM-DD, optional)", spec["birth_date"])
        if spec.get("trigger"):
            self.fill("Conditional Trigger Event (optional)", spec["trigger"])
        guardians = ",".join(spec["guardians"])
        if self.value("Designated Guardian DIDs (Comma Separated)") != guardians:
            self.fill("Designated Guardian DIDs (Comma Separated)", guardians)
        if int(float(self.value("Approval Threshold N (guardians who must approve)"))) != int(spec["threshold"]):
            self.fill("Approval Threshold N (guardians who must approve)", int(spec["threshold"]))
        # the expiry first: the form refuses a start that is not earlier than the expiry it holds
        self.fill("Expiry Time (YYYY-MM-DD HH:MM:SS)", spec["expiry"])
        self.fill("Start Time (YYYY-MM-DD HH:MM:SS)", spec["start"])
        self.shot(shot_form)
        self.click("Initial Consent")
        found = None
        if self.p.locator(".blockchain-badge").count():
            match = re.search(r"Consent ID:\s*([0-9a-f-]{36})", self.p.locator(".blockchain-badge").first.inner_text())
            found = match.group(1) if match else None
        self.shot(shot_done)
        return found

    def my_consents(self, patient, shot=None):
        self.open("Patient")
        self.pick("Patient DID (Identity Pointer)", patient)
        self.p.get_by_text("My Consents", exact=True).scroll_into_view_if_needed()
        self.shot(shot)

    def patient_revoke(self, patient, consent_id, shot_before=None, shot_after=None):
        """Under "My Consents", click "Revoke" in the row of the consent."""
        self.my_consents(patient, shot_before)
        self.row_button(consent_id, "Revoke").click()
        self.wait_text("Revoked on-chain|Consent revoked \\(local ledger\\)|on-chain revoke failed|Revocation refused")
        self.shot(shot_after)

    def take_over(self, patient, shot_before=None, shot_after=None):
        """Under "My Consents", click "Take over this consent (age of majority)"."""
        self.my_consents(patient, shot_before)
        buttons = self.p.get_by_role("button", name="Take over this consent (age of majority)", exact=True)
        if buttons.count() != 1:
            raise RuntimeError(f"{buttons.count()} consents of {patient} offer the take-over, one was expected")
        buttons.first.click()
        self.wait_text("Consent re-issued to the patient|was not re-issued|is re-issued and the old consent|failed and nothing was changed")
        self.shot(shot_after)

    # ---- Guardian screen -------------------------------------------------------------------------------
    def guardian(self, consent_id, guardian=None):
        self.open("Guardian")
        self.fill("Enter Target Consent ID", consent_id)
        if guardian:
            self.pick("Select Your Guardian DID Identity", guardian)

    def approve(self, consent_id, guardian, shot=None):
        self.guardian(consent_id, guardian)
        self.click("Sign Consent via VC")
        self.shot(shot)

    def anchored(self, consent_id, shot=None):
        """The Guardian screen of a consent whose mint is confirmed: "Already anchored on <network> - token #<n>"."""
        self.guardian(consent_id)
        self.shot(shot)

    def anchor_again(self, consent_id):
        """After a failed mint the Guardian screen offers "Anchor on <network> now (background)": click it."""
        self.guardian(consent_id)
        self.p.get_by_role("button", name=re.compile("^Anchor on .* now")).first.click()
        self.idle()

    def guardian_options(self, consent_id, shot=None):
        """The guardians that the selector of the Guardian screen offers for a consent."""
        self.guardian(consent_id)
        offered = self.options("Select Your Guardian DID Identity")
        self.shot(shot)
        self.p.keyboard.press("Escape")
        return offered

    def guardian_revoke(self, consent_id, guardian, shot=None):
        self.guardian(consent_id, guardian)
        self.click("Revoke Consent (as guardian)")
        self.wait_text("Consent revoked by|Revocation refused|This consent is already revoked")
        self.shot(shot)

    # ---- Clinician screen ------------------------------------------------------------------------------
    def clinician(self, consent_id, requester, scope=(), purpose="Treatment", context="AU"):
        """Open the Clinician screen for a consent and declare the request, without submitting it."""
        self.open("Clinician")
        self.fill("Enter Authorised Consent ID", consent_id)
        self.fill("Your Clinician DID (requester)", requester)
        if context != "AU":
            self.pick("Request Context (jurisdiction code)", context)
        if purpose != "Treatment":
            self.pick("Purpose of this request", purpose)
        if scope:
            self.choose("Select Request Scope", scope)

    def request(self, consent_id, requester, scope=(), purpose="Treatment", context="AU", shot_before=None, shot_after=None):
        """Declare a request and click the button whose label starts with "Request Data Access"."""
        self.clinician(consent_id, requester, scope, purpose, context)
        self.shot(shot_before)
        self.p.get_by_role("button", name=re.compile("^Request Data Access")).first.click()
        self.wait_text("Access Granted|Access Denied")
        self.shot(shot_after)

    def attest(self, consent_id, clinician, shot=None):
        self.clinician(consent_id, clinician)
        self.click(f"Attest this event as {clinician}")
        self.wait_text("Attestation verified and recorded|Attestation refused")
        self.shot(shot)

    def notices(self, consent_id, clinician, shot=None):
        """Open the box "Withdrawal notices for this clinician" on the Clinician screen."""
        self.clinician(consent_id, clinician)
        box = self.p.locator('[data-testid="stExpander"]').filter(has_text="Withdrawal notices for this clinician")
        if box.count() == 0:
            raise RuntimeError("the Clinician screen shows no withdrawal notices for " + clinician)
        box.first.locator("summary").click()
        self.idle()
        self.shot(shot)

    # ---- Auditor screen --------------------------------------------------------------------------------
    def audit(self, consent_id, shot=None):
        self.open("Auditor")
        self.pick("Select Consent to Audit", consent_id)
        self.shot(shot)
