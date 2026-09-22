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
