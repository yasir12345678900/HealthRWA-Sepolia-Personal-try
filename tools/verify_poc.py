"""Independent proof-of-concept check: re-reads the HALAH audit ledger and verifies every
recorded tx_hash against the chain (receipt, block, status), then compares every consent token
with the chain.

With CONTRACT_V4_ADDRESS set (ConsentSBTv4, the thesis design) it needs no key: it reads the database
file and the chain, as an auditor does.

    RPC_URL=... CONTRACT_V4_ADDRESS=... VERIFIER_ADDRESS=... HALAH_DB_PATH=... python3 -m tools.verify_poc

  1. every ledger row with a tx_hash: the receipt is found, its status is 1 and its block is the block of the row
  2. every mint: the ConsentIssued event gives the token and its commitment. The commitment is recomputed from the
     opening in the local record and compared with the chain, and the record must still hold the committed values
  3. the revocation state of every token (consents(token).revoked and checkValid) against the local record
  4. every revoke: the ConsentRevoked event names the token of the same consent
  5. every granted request with a proof reference: the receipt and the ConsentVerified event of the verification,
     the request tag opened with the requester and the nonce of the row, and the proof read back from the
     transaction, verified again by a call to the Groth16 verifier
  6. every decision: the STATE_CHECK and DATA_ACCESS rows name the block timestamp as the source of their time.
     A row that names the server clock fails the check. The refused request of a chain that could not be read
     names no time ("unavailable") and passes

A revocation deletes the opening of the commitment and the link to the token from the local record. The commitment
of a revoked consent can therefore not be recomputed: its token is taken from the mint receipt, and the revocation
state alone is compared. The output says so for each such consent.

Without CONTRACT_V4_ADDRESS, or with the argument v3, the older contract ConsentSBTv3 is checked as before:

    RPC_URL=... CONTRACT_ADDRESS=... CONTRACT_VERSION=3 HALAH_DB_PATH=... python3 -m tools.verify_poc v3
"""
import os
import sys
from types import SimpleNamespace

from web3 import Web3
from web3.logs import DISCARD

from blockchain.contract import ConsentContract, did_to_address
from database import db


def main_v3():
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
        mint = next((e for e in onchain if e["consent_id"] == row["consent_id"] and e["action"] == "ONCHAIN_MINT"), None)
        mint_to = w3.eth.get_transaction_receipt(mint["tx_hash"])["to"] if mint else None
        if mint_to and mint_to.lower() != c.address.lower():
            print(f"Consent {row['consent_id']} -> token #{n} lives on an older deployment {mint_to} - skipped")
            continue
        try:
            holder = c.contract.functions.ownerOf(n).call()
        except Exception:
            print(f"Consent {row['consent_id']} -> token #{n} does not exist on {c.address} - skipped")
            continue
        rec = c.contract.functions.consents(n).call()
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


# ---------------------------------------------------------------------------
# ConsentSBTv4 and the decision verifier
# ---------------------------------------------------------------------------
class _Report:
    """The lines of the check. One failed line fails the whole check."""

    def __init__(self, out):
        self.out, self.checks, self.failed = out, 0, 0

    def line(self, good, text):
        self.checks += 1
        self.failed += 0 if good else 1
        self.out(f"  [{'OK' if good else 'XX'}] {text}")
        return bool(good)


def _same(a, b):
    return isinstance(a, str) and isinstance(b, str) and a.lower() == b.lower()


def _chain_token(row):
    """The number of the ConsentSBTv4 token that a local record names, or None."""
    tid = str(row.get("token_id") or "")
    return int(tid[4:]) if tid.startswith("SBT-") and tid[4:].isdigit() and row.get("token_address") else None


BLOCK_TIME = "block-timestamp"


def time_sources(events):
    """Check 6, as data: (the STATE_CHECK and DATA_ACCESS rows that name the source of their time, those among them
    that name another source than the block timestamp). A DATA_ACCESS row with the source "unavailable" is the
    refusal of a request whose chain could not be read: no time was used for it, so it is not among the second."""
    named, other = [], []
    for e in events:
        m = e.get("metadata") if isinstance(e.get("metadata"), dict) else {}
        if e.get("action") == "DATA_ACCESS":
            source = m.get("time_source")
        elif e.get("action") == "STATE_CHECK":
            source = (m.get("time") or {}).get("source") if isinstance(m.get("time"), dict) else m.get("time_source")
        else:
            continue
        if source is None:
            continue
        named.append(e)
        if source != BLOCK_TIME and not (e["action"] == "DATA_ACCESS" and source == "unavailable"):
            other.append({"event_id": e.get("event_id"), "action": e["action"], "consent_id": e.get("consent_id"),
                          "timestamp": e.get("timestamp"), "time_source": source})
    return named, other


def _receipts(w3, events, report):
    """Check 1: the receipt of every ledger row that names a transaction. Returns tx_hash -> receipt."""
    found = {}
    for e in events:
        try:
            r = w3.eth.get_transaction_receipt(e["tx_hash"])
        except Exception as ex:
            report.line(False, f"{e['action']:<15} {e['tx_hash']} NOT FOUND: {ex}")
            continue
        found[e["tx_hash"]] = r
        same_block = e.get("block_number") is not None and int(r["blockNumber"]) == int(e["block_number"])
        report.line(same_block and r["status"] == 1,
                    f"{e['action']:<15} {e['tx_hash']} block {r['blockNumber']} (ledger {e.get('block_number')}) "
                    f"{'SUCCESS' if r['status'] == 1 else 'REVERTED'} gas {r['gasUsed']} to {r['to']}")
    return found


def _check_token(token, n, row, report, event_commitment=None):
    """Checks 2 and 3 for one token: the commitment against the local record, and the revocation state."""
    from services import commitment_service
    out = report.out
    try:
        stored = token.consent_of(n)
        valid = token.check_valid(n)
    except Exception as ex:
        report.line(False, f"token #{n} could not be read from {token.address}: {ex}")
        return
    if event_commitment is not None:
        report.line(stored["commitment"] == event_commitment,
                    f"commitment on chain {commitment_service.commitment_hex(stored['commitment'])} == commitment of the ConsentIssued event")
    if row is None:
        report.line(False, "the local record of this consent is missing")
        return
    opening = row.get("commitment_opening")
    if opening:
        try:
            recomputed = commitment_service.open_commitment(opening)
        except Exception:
            recomputed = None
        report.line(recomputed is not None and recomputed == stored["commitment"],
                    "commitment recomputed from the opening of the local record == commitment on chain")
        report.line(commitment_service.opening_matches_consent(SimpleNamespace(**row), opening),
                    "the local record still holds the values that were committed")
        try:
            holder = token.contract.functions.ownerOf(n).call()
        except Exception:
            holder = None
        report.line(row.get("token_id") == f"SBT-{n}" and _same(holder, row.get("token_address")),
                    f"the local record names token #{n} and its per-consent address {holder}")
    elif row.get("revoked"):
        out("  [--] the opening and the link to the token were deleted with the revocation: the commitment cannot be "
            "recomputed, and the revocation state alone is compared")
    else:
        report.line(False, "the local record holds no opening although the consent is not revoked")
    local = bool(row.get("revoked"))
    report.line(stored["revoked"] == local and valid == (not local),
                f"revocation state: chain revoked={stored['revoked']} checkValid={valid} | local revoked={local}")


def _check_verification(verifier, e, report):
    """Check 5 for one granted request: the verification transaction that its proof reference names."""
    from services import commitment_service
    reference = e["metadata"]["proof_reference"]
    tx, label = reference["tx_hash"], f"DATA_ACCESS {e['event_id'][:8]} by {e['actor_did']}"
    if verifier is None:
        report.line(False, f"{label}: VERIFIER_ADDRESS is not set, so the verification {tx} cannot be checked")
        return
    try:
        r = verifier.w3.eth.get_transaction_receipt(tx)
    except Exception as ex:
        report.line(False, f"{label}: verification {tx} NOT FOUND: {ex}")
        return
    report.line(r["status"] == 1 and int(r["blockNumber"]) == int(reference.get("block_number") or -1) and _same(r["to"], verifier.address),
                f"{label}: verification {tx} block {r['blockNumber']} (ledger {reference.get('block_number')}) "
                f"{'SUCCESS' if r['status'] == 1 else 'REVERTED'} gas {r['gasUsed']} to {r['to']}")
    events = verifier.contract.events.ConsentVerified().process_receipt(r, errors=DISCARD)
    args = dict(events[0]["args"]) if len(events) == 1 else {}
    try:
        tag = int(reference.get("tag"))
    except (TypeError, ValueError):
        tag = None
    report.line(args.get("result") is True and tag is not None and int(args.get("tag", -1)) == tag,
                f"  ConsentVerified event: result {args.get('result')}, its tag is the tag of the ledger row")
    nonce = (reference.get("reference") or {}).get("nonce")
    report.line(tag is not None and nonce is not None and commitment_service.open_tag(tag, e["actor_did"], nonce),
                "  the request tag opens to the requester of the row with the recorded nonce")
    try:
        submitted = verifier.submitted_proof(tx)
        again = verifier.reverify(submitted["proof"], submitted["publicSignals"])
    except Exception:
        again = False
    report.line(again, "  the proof read back from the transaction verifies again (call to the Groth16 verifier)")


def verify_v4(token, events, consents, verifier=None, out=print):
    """The check for ConsentSBTv4. `token` and `verifier` are read-only clients of blockchain/contract_v4
    (ConsentContractV4, DecisionVerifierContract), `events` the rows of the audit ledger in order and `consents` the
    consent records, both as the database file holds them. Prints through `out` and returns True when every check
    passed."""
    w3 = token.w3
    report = _Report(out)
    out(f"RPC {token.rpc} | chainId {w3.eth.chain_id} | head block {w3.eth.block_number}")
    out(f"ConsentSBTv4 {token.address} | code {len(w3.eth.get_code(token.address))} bytes | "
        f"owner {token.contract.functions.owner().call()} | consentCount {token.consent_count()}")
    if verifier is not None:
        status = verifier.status()
        out(f"ConsentDecisionVerifier {verifier.address} | code {len(w3.eth.get_code(verifier.address))} bytes | "
            f"Groth16 verifier {status['proof_verifier']}")
        report.line(_same(status["consent_token"], token.address), "the decision verifier reads its roots from this consent contract")
    out("")

    onchain = [e for e in events if e.get("tx_hash")]
    out(f"Audit ledger: {len(events)} events, {len(onchain)} with a tx_hash")
    receipts = _receipts(w3, onchain, report)
    out("")

    # Checks 2 and 3: every token, from its mint receipt, against the local record.
    records = {row["consent_id"]: row for row in consents}
    tokens = {}
    for e in onchain:
        if e.get("action") != "ONCHAIN_MINT" or e["tx_hash"] not in receipts:
            continue
        r, cid = receipts[e["tx_hash"]], e.get("consent_id")
        if not _same(r["to"], token.address):
            out(f"Consent {cid}: the mint {e['tx_hash']} went to another contract ({r['to']}) - skipped")
            tokens.setdefault(cid, None)
            continue
        issued = token.contract.events.ConsentIssued().process_receipt(r, errors=DISCARD)
        if len(issued) != 1:
            report.line(False, f"Consent {cid}: the mint {e['tx_hash']} carries no ConsentIssued event")
            continue
        n = tokens[cid] = int(issued[0]["args"]["tokenId"])
        out(f"Consent {cid} -> token #{n} (mint in block {r['blockNumber']})")
        _check_token(token, n, records.get(cid), report, event_commitment=int(issued[0]["args"]["commitment"]))
    for row in consents:
        cid = row["consent_id"]
        if cid in tokens:
            continue
        n = _chain_token(row)
        if n is not None:                       # recorded from the chain without its mint transaction (Sync)
            out(f"Consent {cid} -> token #{n} (no mint transaction in the ledger)")
            tokens[cid] = n
            _check_token(token, n, row, report)
        else:
            out(f"Consent {cid}: token {row.get('token_id') or '-'} (not anchored on this contract)")
    out("")

    # Check 4: every revoke names the token of its consent.
    for e in onchain:
        if e.get("action") != "ONCHAIN_REVOKE" or e["tx_hash"] not in receipts:
            continue
        r, cid = receipts[e["tx_hash"]], e.get("consent_id")
        if not _same(r["to"], token.address):
            out(f"  [--] ONCHAIN_REVOKE {e['tx_hash']} went to another contract ({r['to']}) - skipped")
            continue
        revoked = [int(x["args"]["tokenId"]) for x in token.contract.events.ConsentRevoked().process_receipt(r, errors=DISCARD)]
        report.line(len(revoked) == 1 and tokens.get(cid) is not None and revoked[0] == tokens[cid],
                    f"ONCHAIN_REVOKE {e['tx_hash']}: ConsentRevoked names token {revoked} == token #{tokens.get(cid)} of consent {cid}")

    # Check 5: every granted request whose proof was verified on chain.
    for e in events:
        reference = (e.get("metadata") or {}).get("proof_reference") if isinstance(e.get("metadata"), dict) else None
        if e.get("action") == "DATA_ACCESS" and e.get("result") == "GRANTED" and isinstance(reference, dict) and reference.get("tx_hash"):
            _check_verification(verifier, e, report)
    out("")

    # Check 6: with a chain configured every decision is taken at the block timestamp, never at the server clock.
    decided, other = time_sources(events)
    for row in other:
        report.line(False, f"time source: {row['action']} {str(row['event_id'])[:8]} of consent {row['consent_id']} "
                           f"({row['timestamp']}) names {row['time_source']}, not the block timestamp")
    if not other:
        report.line(True, f"time source: the {len(decided)} STATE_CHECK and DATA_ACCESS rows that name one name the block timestamp")
    out(f"{report.checks} checks, {report.failed} failed")
    out("RESULT: " + ("ALL CHECKS PASSED" if report.failed == 0 else "SOME CHECKS FAILED"))
    return report.failed == 0


def main(argv=None, token=None, verifier=None, events=None, consents=None):
    argv = sys.argv[1:] if argv is None else argv
    if "v3" in argv or not (token is not None or os.environ.get("CONTRACT_V4_ADDRESS")):
        return main_v3()
    from blockchain.contract_v4 import ConsentContractV4, DecisionVerifierContract
    token = token or ConsentContractV4(read_only=True)
    if verifier is None and os.environ.get("VERIFIER_ADDRESS"):
        verifier = DecisionVerifierContract(w3=token.w3, read_only=True)        # the same connection as the token client
    ok = verify_v4(token, db.all_rows("audit", "ts") if events is None else events,
                   db.all_rows("consents") if consents is None else consents, verifier)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
