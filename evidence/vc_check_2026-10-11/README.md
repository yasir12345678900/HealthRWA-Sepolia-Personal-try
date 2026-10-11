# Credential check, VL as the lifecycle check, requester identity (2026-10-11)

A browser run (Playwright + Chromium) of the updated app in demo mode ("Demo mode (local ledger)"): no chain was configured,
so no Sepolia transaction was sent. The app used a copy of `data/halah.db`, so the database in the repository is unchanged.
Times on the screens are the container clock.

## What changed in the code
- Credentials (original report, RO2 Steps 3-6): VC_valid = Sig_VC AND Issuer_valid AND Subject_match AND Time_valid, then the role claim.
- The patient form checks the authorised doctor and every guardian (a valid DID that holds a valid credential with the right role).
- A guardian's credential is checked before the EIP-712 signature is added.
- The doctor enters their own DID; VI checks it, its doctor credential and that it is the doctor named in the consent.
- VL is the lifecycle check (the consent state must be ACTIVE); the jurisdiction comparison is part of VP (policy context).
- The "2/2" texts show the real counts.

## Screenshots
| File | What it shows |
|---|---|
| `01_patient_bad_doctor_rejected.png` | Doctor field `did:hospital:001did:hospital:002` is rejected: no valid doctor credential |
| `02_patient_guardian_without_credential_rejected.png` | Guardian `did:parent:Z` has no credential, so the consent is not created |
| `03_patient_consent_created.png` | Consent 44e0ce10 created off-chain with guardians A and B, doctor `did:hospital:001` |
| `04_guardian_A_1of2.png` | Guardian A: credential verified, EIP-712 signature verified, 1/2 |
| `05_guardian_B_2of2.png` | Guardian B: 2/2, local token (demo mode, no on-chain anchoring) |
| `06_doctor_wrong_requester_matrix.png` | Requester `did:hospital:002` has a valid doctor credential but is not the doctor in this consent: VI FAIL |
| `07_doctor_wrong_requester_denied.png` | The request is denied ("Failed checks: VI") and recorded |
| `08_doctor_authorised_matrix.png` | Requester `did:hospital:001`: all five checks PASS |
| `09_doctor_granted.png` | Groth16 proof verified, access granted, records shown |
| `10_doctor_policy_context_mismatch.png` | Requester jurisdiction changed to US: VP FAIL, VL PASS |
| `11_doctor_after_revocation.png` | After the patient revokes: state REVOKED, VA FAIL and VL FAIL |
| `12_doctor_after_revocation_denied_recorded.png` | The request on the revoked consent is denied and recorded |
| `13_auditor.png` | Auditor view after the run |

## Other files
- `ledger_events_44e0ce10.csv`: the 11 ledger events of consent 44e0ce10 (creation, two approvals with credential IDs,
  STATE_CHECK rows with the requester's DID, GRANTED and DENIED rows, revocation).
- `A13_before_change.txt` / `A13_after_change.txt`: the same probe on the code before and after the change. Before, a doctor DID
  with no credential, two DIDs typed into one field, and a guardian DID used as the doctor were all accepted (VI PASS, ALLOW).
  After, all three are refused (VI FAIL).
- `test_suite.txt`: the full test run, 42 tests passed (14 in `tests/test_adversarial.py`: the baseline and attacks A1 to A13).
