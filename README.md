HALAH: A Blockchain-Based Patient Consent Management System
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date (YYYY-MM-DD): 2026-06-08, 2026-08-02

Push To https://github.com/Charles-Code4Fun/HealthRWA.git
   c4546f8..ecdf495  main -> main
branch 'main' set up to track 'origin/main'.


## v1.1 upgrade (2026-09-22) - C = (I, A, P, T, L, E) end to end
- **VI - real guardian signatures**: EIP-712 typed-data approvals verified by ecrecover (`services/identity_service.py`).
  Demo keys derive from the guardian DID; in production the guardian's own wallet signs the same typed data. One signature per guardian.
- **VA/E - revoke**: Patient -> *My Consents* -> **Revoke** updates local state and calls `revoke()` on the contract (`ONCHAIN_REVOKE` with a real tx hash).
- **VP/VT/VL - decision matrix**: `services/access_service.evaluate_allow()` returns VI, VA, VP, VT, VL, ALLOW; shown in the Doctor page.
- **Persistence**: SQLite write-through (`data/halah.db`, git-ignored) - consents and audit survive restarts, shared across sessions.
- **ConsentSBTv3** (`contracts/ConsentSBTv3.sol`, artifact `blockchain/abi/ConsentSBTv3.json`): VT (`notBefore`/`expiry`) and VL (`jurisdiction`)
  enforced on-chain (`checkValid`, `checkValidAt`), events, **ERC-5484** consensual burn (`burnAuth`, `burn`).
  Deploy without Remix: `python3 -m blockchain.deploy ConsentSBTv3` -> set `CONTRACT_ADDRESS` + `CONTRACT_VERSION=3`.
- **Limited-scope zero-knowledge proof** (`zk/`): Groth16/BN254 circuit proving "I know (secret, expiry) behind this Poseidon commitment
  and now <= expiry" without revealing either. Build once: `bash zk/build_zk.sh`; verifier: `contracts/ConsentValidityVerifier.sol`. Dev-only trusted setup.
- Tests: `python3 -m pytest -q tests/`.

## v1.2 fixes (2026-09-24) - found by an end-to-end run, proof in `evidence/poc_2026-09-24/`
- **v3 mint lost its token id**: `mint_consent_v3` used `DISCARD` without importing it, so every v3 mint stayed `SBT-LOCAL-*`
  (no on-chain revoke, and "Anchor now" minted duplicates). Fixed in `blockchain/contract.py`.
- **Sync from chain never matched on v3**: `find_onchain_tokens` read `notBefore` as the expiry (wrong struct index). Fixed.
- **`ConsentSBTv3.mintConsent` (v2-compatible) always reverted**: `this.mintConsentV3(...)` made the contract the caller, which fails `onlyOwner`.
  It now uses an internal `_mintV3`. The artifact was recompiled; **redeploy v3** to get this fix on Sepolia.
- **Doctor access**: an empty request scope was granted, and a VL (jurisdiction) mismatch was still granted. Access now requires
  a non-empty scope **and** the full VI..VL matrix. A denial names the failed checks.
- **EMR data**: `observations.csv`, `medications.csv` and `procedures.csv` are partially corrupted (binary garbage after 128 KiB), so the
  whole module used to load empty. The loader now keeps every valid row. **Re-export these files from Synthea to restore the missing rows.**
- UI: labels, expanders and download buttons were white-on-white; network labels now show the real chain instead of always "Sepolia";
  the Synthea repo is cached (it was re-read on every click); the Auditor table no longer hits Arrow errors on the JSON columns;
  STATE_CHECK is logged once per access request instead of on every page refresh; guardian DIDs are trimmed and validated.
- New: `tools/verify_poc.py` (checks the audit ledger against the chain), `tools/poc_screenshots.py` (browser A-to-Z walkthrough),
  `tests/test_regressions.py`.
