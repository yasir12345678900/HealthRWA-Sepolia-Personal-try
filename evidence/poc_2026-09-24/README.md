# HALAH proof of concept, A to Z (2026-09-24)

This is a real run of the Streamlit app, driven by a browser (Playwright + Chromium), with full-page screenshots.
Every blockchain action is a real signed transaction on a local EVM (Hardhat, chainId 31337) running the
`ConsentSBTv3` contract from this repo. The ZK proof is a real Groth16 proof (circom + snarkjs, dev trusted setup).

**Why a local chain and not Sepolia:** the sandbox that produced this run cannot reach any Sepolia RPC (the proxy
returns 403, see screenshot 19). The app code path is exactly the same; only `RPC_URL` and `CONTRACT_ADDRESS` differ.
The UI now shows the real network (`chain 31337`) instead of claiming "Sepolia". The earlier real Sepolia mints
are still listed in `../onchain_mints_2026-09-21.txt`.

| # | Screenshot | What it proves |
|---|---|---|
| 01 | `01_patient_home_chain_connected.png` | App connected to the chain: block, signer balance, contract address |
| 02 | `02_patient_validation_empty_scope.png` | A consent cannot be created with an empty data scope (new check) |
| 03 | `03_patient_consent_created.png` | Consent created off-chain, `PENDING_SIGNATURE`, 0/2 signatures |
| 04 | `04_guardian_consent_found.png` | Guardian loads the consent by ID |
| 05 | `05_guardian_A_eip712_signed_1of2.png` | Guardian A: EIP-712 signature verified by ecrecover, 1/2 |
| 06 | `06_guardian_B_signed_2of2_sbt_mint_started.png` | Guardian B: 2/2 threshold reached, SBT mint sent in the background |
| 07 | `07_guardian_anchored_onchain_token.png` | Mint confirmed: the consent now holds on-chain token #1 |
| 08 | `08_doctor_decision_matrix_all_pass.png` | VI, VA, VP, VT, VL all PASS, so ALLOW; state ACTIVE |
| 09 | `09_doctor_empty_request_scope_blocked.png` | An empty request is refused (it used to be granted) |
| 10 | `10_doctor_groth16_zk_access_granted_records.png` | Groth16 proof verified, access granted, EMR for all 4 modules |
| 11 | `11_doctor_jurisdiction_US_denied_VL_fail.png` | Requester in US vs consent in AU: VL fails and access is denied (it used to be granted) |
| 12 | `12_patient_my_consents_active.png` | The patient sees the ACTIVE consent with token SBT-1 |
| 13 | `13_patient_revoked_onchain.png` | The patient revokes it: `revoke()` transaction on-chain, state REVOKED |
| 14 | `14_doctor_after_revoke_denied.png` | After revoke: VA fails and the doctor is denied |
| 15 | `15_auditor_lifecycle_and_ledger.png` | Full lifecycle plus a ledger with tx_hash and block for the on-chain events |
| 16 | `16_cli_pytest_23_passed.png` | 23/23 tests pass, including real Groth16 and the new regression tests |
| 17 | `17_cli_groth16_zk_proof.png` | ZK proof: valid is accepted, tampered is rejected, an expired consent cannot be proven |
| 18 | `18_cli_onchain_independent_verification.png` | Every tx_hash in the ledger re-checked against chain receipts; on-chain state matches the ledger |
| 19 | `19_cli_sepolia_reachability_and_prior_evidence.png` | Sepolia is blocked from this sandbox; earlier Sepolia evidence, same patient address |

The raw terminal output is in `pytest.txt`, `zk.txt`, `chain.txt` and `sepolia.txt`.

## Reproduce
```bash
pip install -r requirements.txt playwright && bash zk/build_zk.sh
# local chain (or use Sepolia via .env)
npx hardhat node &   # prints funded dev keys
RPC_URL=http://127.0.0.1:8545 PRIVATE_KEY=<hardhat key #0> python3 -m blockchain.deploy ConsentSBTv3
export RPC_URL=http://127.0.0.1:8545 PRIVATE_KEY=<same> CONTRACT_ADDRESS=<printed> CONTRACT_VERSION=3
streamlit run app.py &
python3 tools/poc_screenshots.py      # screenshots 01-15
python3 -m tools.verify_poc           # independent ledger vs chain check
```
