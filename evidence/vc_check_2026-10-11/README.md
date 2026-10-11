# Credential check, VL as the lifecycle check, requester identity (2026-10-11)

A browser run (Playwright + Chromium) of the updated app in demo mode ("Demo mode (local ledger)"): no chain was configured,
so no Sepolia transaction was sent. The app used a copy of `data/halah.db`, so the database in the repository is unchanged.
Times on the screens are the container clock. `ui_run_result.json` lists the checks the run made on each screen.

## What changed in the code
- Credentials (original report, RO2 Steps 3-6): VC_valid = Sig_VC AND Issuer_valid AND Subject_match AND Time_valid, then the role claim.
- The patient form checks the authorised doctor and every guardian (a valid DID that holds a valid credential with the right
  role) and refuses a guardian listed twice.
- A guardian's credential is checked before the EIP-712 signature is added; a refused approval is written to the ledger.
- The doctor enters their own DID; VI checks it, its doctor credential and that it is the doctor named in the consent.
  A requester who fails VI is refused before the consent's scope or any record is shown, and the refusal is recorded.
- VL is the lifecycle check (the consent state must be ACTIVE); the jurisdiction comparison is part of VP (policy context).
- Ledger rows of the doctor screen carry the requester's DID, the credential ID and issuer, and `matrix_version` 1.3.
- The "2/2" texts show the real counts.

## Limits of this stage (stated in the code as well)
- The requester DID is entered, not authenticated: VI shows that the entered DID holds a valid doctor credential and is the
  doctor named in the consent, not that the person typing controls that DID (holder binding is next-stage work).
- Full DID resolution is not implemented; the DID is checked for syntax only.
- The demo credentials are signed by one demo issuer whose key, like the guardian demo keys, can be reproduced from the
  source code. The credential check shows the verification steps; it does not rely on the issuer key being secret.
- VL checks the state only (ValidState). The transition check and the SUSPENDED state are next-stage work; in this
  prototype every non-ACTIVE state also fails VA or VT, so VL never refuses a request on its own.
- STATE_CHECK rows written before 11 October 2026 used VL for the jurisdiction comparison.

## Screenshots
| File | What it shows |
|---|---|
| `01_patient_bad_doctor_rejected.png` | Doctor field `did:hospital:001did:hospital:002` is refused: no valid doctor credential |
| `02_patient_guardian_without_credential_rejected.png` | Guardian `did:parent:Z` has no credential, so the consent is not created |
| `02b_patient_duplicate_guardian_rejected.png` | The same guardian listed twice is refused |
| `03_patient_consent_created.png` | Consent 18ab9b62 created off-chain with guardians A and B, doctor `did:hospital:001` |
| `04_guardian_A_1of2.png` | Guardian A: credential verified, EIP-712 signature verified, 1/2 |
| `05_guardian_B_2of2.png` | Guardian B: 2/2, local token (demo mode, no on-chain anchoring) |
| `06_doctor_wrong_requester_matrix.png` | Requester `did:hospital:002` holds a valid doctor credential but is not the doctor in this consent: VI FAIL |
| `07_doctor_wrong_requester_denied.png` | The request is refused at VI before any scope or record is shown, and recorded |
| `08_doctor_authorised_matrix.png` | Requester `did:hospital:001`: all five checks PASS |
| `09_doctor_granted.png` | Groth16 proof verified, access granted, records shown |
| `10_doctor_policy_context_mismatch.png` | Requester jurisdiction changed to US: VP FAIL, VL PASS |
| `11_doctor_after_revocation.png` | After the patient revokes: state REVOKED, VA FAIL and VL FAIL |
| `12_doctor_after_revocation_denied_recorded.png` | The request on the revoked consent is refused and recorded |
| `13_auditor.png` | Auditor view after the run |

## Other files
- `ledger_events_18ab9b62.csv`: the 11 ledger events of consent 18ab9b62 (creation, two approvals with credential IDs,
  STATE_CHECK rows with the requester and its credential, GRANTED and DENIED rows, revocation).
- `A13_before_change.txt` / `A13_after_change.txt`: the same probe (`tools/a13_probe.py`) on the code before and after the
  change. Before, a doctor DID with no credential, two DIDs typed into one field, and a guardian DID used as the doctor were
  all accepted (VI PASS, ALLOW). After, all three are refused (VI FAIL).
- `test_suite.txt`: the full test run (46 tests; 14 in `tests/test_adversarial.py`: the baseline and attacks A1 to A13).
