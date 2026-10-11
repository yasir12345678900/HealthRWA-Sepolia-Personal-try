# HALAH run in the Codespace, connected to Sepolia (2026-10-11)

Screenshots taken by hand while using the app in the Codespace, after the change that records a refused
request on a consent that is not ACTIVE. The app was connected to Sepolia (contract
0x0EC3617581DEC63A7f2bb162DC14d088916ADc73). Times inside the app are UTC (the Codespace clock).

## Sepolia transactions in this run
| Consent | Guardians | Transaction | Block | Time (UTC) | Status |
|---|---|---|---|---|---|
| 49c7bfaa | 2 of 2 | `0x7a9efb621e8497259c53e9b1c69e60d350bf4f47f2e378049e734d813dd08949` (mintConsentV3) | 11,888,788 | 02:42:12 | success, token #3 |
| e9ef47d2 | 3 of 3 | `0x432b25ab81b14b381a8810436af14f796b815f1d099fb9dc75ce1d67093fe428` (mintConsentV3) | 11,888,870 | 02:58:36 | success, token #4 |

Only one mint was sent for each consent, even though a guardian button was pressed more than once.

## Screenshots
| File | What it shows |
|---|---|
| `00_codespace_terminal.png` | Codespace terminal before starting the app |
| `01_49c7bfaa_guardian_B_second_signature_rejected_anchoring.webp` | 2/2 reached; a second signature by guardian B is rejected ("one signature per guardian"); anchoring in progress |
| `02_49c7bfaa_doctor_active_all_pass.webp` | Doctor view: consent ACTIVE, all checks PASS |
| `03_be77a6f9_doctor_pending_0of2.webp` | Doctor view: no guardian has signed (0/2), state PENDING_SIGNATURE, VI and VA FAIL |
| `04_be77a6f9_doctor_pending_0of2_denied_recorded.webp` | Request denied and recorded in the audit ledger |
| `05_49c7bfaa_guardian_already_anchored_token3.webp` | Anchoring confirmed: token #3; a repeated signature by guardian A is rejected |
| `06_20a98ca8_patient_create_form.webp` | Patient form (start time shown in UTC) |
| `07_20a98ca8_patient_created_offchain.webp` | Consent created and logged off-chain; nothing on the chain before guardian approval |
| `08_patient_my_consents.webp` | Patient list of consents with state, signatures and token |
| `09_3G_e9ef47d2_patient_created_offchain.webp` | Consent with three guardians (A, B, C) created off-chain |
| `10_3G_e9ef47d2_guardian_A_1of3.webp` | Guardian A signs: 1/3 |
| `11_3G_e9ef47d2_guardian_B_2of3.webp` | Guardian B signs: 2/3 |
| `12_3G_e9ef47d2_doctor_at_2of3_denied_recorded.webp` | Doctor requests at 2/3: VA FAIL, PENDING_SIGNATURE, denied and recorded |
| `13_3G_e9ef47d2_guardian_C_3of3_token_anchoring.webp` | Guardian C signs: 3/3, local token, anchoring on Sepolia (the status line says "2/2" because that text is fixed in the app) |
| `14_3G_e9ef47d2_doctor_active_all_pass.webp` | Doctor view after 3/3: ACTIVE, all checks PASS |
| `15_3G_e9ef47d2_doctor_request_observation.webp` | Doctor selects the agreed module (Observation) |
| `16_3G_e9ef47d2_doctor_access_granted_records.webp` | Groth16 verification successful, access granted, records shown |
| `17_3G_e9ef47d2_observation_export.csv` | The Observation records the doctor downloaded (synthetic Synthea patient) |
| `18_auditor_dashboard_82_events.webp` | Auditor dashboard: 82 events, 12 consent events, 13 access requests, 7 on-chain anchors |
| `19_3G_e9ef47d2_auditor_lifecycle_create_and_signatures.webp` | Auditor lifecycle of e9ef47d2: creation, signatures of A and B |
| `20_3G_e9ef47d2_auditor_lifecycle_denied_then_C_signs.webp` | STATE_CHECK PENDING_SIGNATURE and DATA_ACCESS DENIED at 2/3, then guardian C signs |
| `21_3G_e9ef47d2_auditor_lifecycle_mint_and_active.webp` | Local token, on-chain mint, STATE_CHECK ACTIVE |
| `22_3G_e9ef47d2_auditor_detailed_records.webp` | Detailed audit records of e9ef47d2, with the on-chain mint in block 11,888,870 |
| `23_audit_ledger_all_82_events.csv` | Full audit ledger exported by the auditor (82 events) |
| `24_audit_ledger_e9ef47d2.csv` | Audit records of consent e9ef47d2 only |
