"""Independent proof-of-concept check: re-reads the HALAH audit ledger and verifies every
recorded tx_hash against the chain (receipt, block, status), then reads the consent token's
on-chain state (owner, checkValid, checkValidAt) directly from the contract.

    RPC_URL=... CONTRACT_ADDRESS=... CONTRACT_VERSION=3 HALAH_DB_PATH=... python3 -m tools.verify_poc
"""
import os
import sys

from web3 import Web3

from blockchain.contract import ConsentContract, did_to_address
from database import db


def main():
    c = ConsentContract()
    w3 = c.w3
    print(f"RPC {c.rpc} | chainId {w3.eth.chain_id} | head block {w3.eth.block_number}")
    print(f"Contract {c.address} | code {len(w3.eth.get_code(c.address))} bytes | owner {c.contract.functions.owner().call()}")
    print()
    events = db.all_rows("audit", "ts")
    onchain = [e for e in events if e.get("tx_hash")]
    print(f"Audit ledger: {len(events)} events, {len(onchain)} with a tx_hash")
    ok = True
    for e in onchain:
        try:
            r = w3.eth.get_transaction_receipt(e["tx_hash"])
            match = int(r["blockNumber"]) == int(e["block_number"])
            status = "SUCCESS" if r["status"] == 1 else "REVERTED"
            print(f"  [{'OK' if match and r['status'] == 1 else 'XX'}] {e['action']:<15} {e['tx_hash']} "
                  f"block {r['blockNumber']} (ledger {e['block_number']}) {status} gas {r['gasUsed']} to {r['to']}")
            ok &= match and r["status"] == 1
        except Exception as ex:
            print(f"  [XX] {e['action']} {e['tx_hash']} NOT FOUND: {ex}")
            ok = False
    print()
    consents = db.all_rows("consents")
    for row in consents:
        tid = str(row.get("token_id") or "")
        if not (tid.startswith("SBT-") and tid[4:].isdigit()):
            print(f"Consent {row['consent_id']}: token {tid or '-'} (not anchored)")
            continue
        n = int(tid[4:])
        rec = c.contract.functions.consents(n).call()
        holder = c.contract.functions.ownerOf(n).call()
        print(f"Consent {row['consent_id']} -> token #{n}")
        print(f"  ownerOf            {holder}  == did_to_address(patient) {holder == did_to_address(row['patient_did'])}")
        print(f"  requester          {rec[1]}  == did_to_address(doctor)  {rec[1] == did_to_address(row['requester_did'])}")
        print(f"  purposeHash        0x{rec[2].hex()}  == keccak('{row['purpose']}') {rec[2] == Web3.keccak(text=row['purpose'])}")
        print(f"  notBefore/expiry   {rec[3]} / {rec[4]}")
        print(f"  jurisdiction       {rec[5]!r}  revoked(on-chain) {rec[6]}  burnAuth {rec[7]}")
        print(f"  checkValid         {c.check_valid(n)}")
        print(f"  checkValidAt(AU)   {c.check_valid_at(n, 'AU')}   checkValidAt(US) {c.check_valid_at(n, 'US')}")
        print(f"  local ledger state revoked={row.get('revoked')}  (matches chain: {bool(row.get('revoked')) == bool(rec[6])})")
        ok &= bool(row.get("revoked")) == bool(rec[6])
    print()
    print("RESULT:", "ALL CHECKS PASSED" if ok else "SOME CHECKS FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
