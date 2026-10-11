# HALAH refusal scenarios (2026-10-11)

This is a real run of the Streamlit app, driven by a browser (Playwright + Chromium), with full-page screenshots.
It shows three requests that the doctor sends on a consent that is not ACTIVE. Since the change in `app.py`
on this date, such a request is denied and recorded in the audit ledger, like every other denied request.

**Setup:** the app ran on a copy of `data/halah.db` taken after the 24 September run
(`HALAH_DB_PATH` pointed to the copy), so `data/halah.db` itself is unchanged. The copy is not kept in the
repository (`*.db` is ignored); every event it gained is in the CSV file below. No chain was configured ("Demo mode (local ledger)"), so no new Sepolia
transaction was sent. The revocation of consent f050c29a is the one already on Sepolia (block 11,771,307).
Times are Sydney time (AEDT).

| Case | Consent | What was done | State at the request | Failed check | Result |
|---|---|---|---|---|---|
| A | fc03dd6c | Only guardian A signed (1 of 2) | PENDING_SIGNATURE | VA | DENIED, recorded 13:17:43 |
| B | 4f8ee143 | Both guardians signed; validity of 5 minutes (expiry 13:16:57) | EXPIRED | VT | DENIED, recorded 13:17:52 |
| C | f050c29a | The consent revoked on 24 September | REVOKED | VA | DENIED, recorded 13:18:02 |

Each request produces two events: `STATE_CHECK` (the consent state and the decision matrix) and
`DATA_ACCESS` with result `DENIED`. All new events are in `audit_ledger_2026-10-11_new_events.csv`.

| Screenshot | What it shows |
|---|---|
| `A1_patient_consent_created.png` | Consent A created |
| `A2_guardian_A_signed_1of2.png` | Guardian A signs; 1 of 2 |
| `A3_doctor_before_request.png` | Doctor view: state PENDING_SIGNATURE, VA FAIL |
| `A3_doctor_request_denied_recorded.png` | Request denied and recorded |
| `B1_patient_consent_created_5min.png` | Consent B created with a 5-minute validity |
| `B2_guardians_signed_2of2.png` | Both guardians sign; 2 of 2, local token |
| `B3_doctor_before_request.png` | After expiry: state EXPIRED, VT FAIL |
| `B3_doctor_request_denied_recorded.png` | Request denied and recorded |
| `C1_doctor_before_request.png` | Revoked consent f050c29a: state REVOKED, VA FAIL |
| `C1_doctor_request_denied_recorded.png` | Request denied and recorded |
