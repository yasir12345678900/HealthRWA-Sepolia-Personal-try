"""ConsentSBTv3 on an in-memory EVM (eth-tester): the mint input checks, the events and the ERC-5484 burn rule."""
import json, os
import pytest

ZERO = "0x" + "00" * 20
ISSUER_ONLY, OWNER_ONLY, BOTH, NEITHER = 0, 1, 2, 3     # IERC5484.BurnAuth


def chain():
    try:
        from web3 import Web3, EthereumTesterProvider
    except Exception:
        pytest.skip("eth-tester not installed")
    art = json.load(open(os.path.join(os.path.dirname(__file__), "..", "blockchain", "abi", "ConsentSBTv3.json")))
    w3 = Web3(EthereumTesterProvider()); owner, stranger, patient, doctor = w3.eth.accounts[:4]
    C = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
    addr = w3.eth.get_transaction_receipt(C.constructor().transact({"from": owner})).contractAddress
    c = w3.eth.contract(address=addr, abi=art["abi"])
    return w3, c, owner, stranger, patient, doctor, w3.eth.get_block("latest").timestamp


def refused(fn, reason, sender):
    with pytest.raises(Exception, match=reason):
        fn.transact({"from": sender})


def mint(c, owner, patient, doctor, now, auth):
    fn = c.functions.mintConsentV3(patient, doctor, "Treatment", now, now + 86400, b"AU", auth)
    tid = fn.call({"from": owner})
    return tid, fn.transact({"from": owner})


def burned(w3, c, tid, sender):
    rc = w3.eth.get_transaction_receipt(c.functions.burn(tid).transact({"from": sender}))
    b = c.events.ConsentBurned().process_receipt(rc)
    assert len(b) == 1 and dict(b[0]["args"]) == {"tokenId": tid, "by": sender}
    assert c.functions.checkValid(tid).call() is False
    with pytest.raises(Exception, match="no token"):                  # the token is gone
        c.functions.burnAuth(tid).call()
    rec = c.functions.consents(tid).call()
    assert rec[0] == ZERO and rec[1] == ZERO and rec[4] == 0          # and its record is cleared


def test_mint_refuses_bad_input_and_mints_nothing():
    w3, c, owner, _, patient, doctor, now = chain()
    v3 = c.functions.mintConsentV3
    refused(v3(ZERO, doctor, "Treatment", now, now + 86400, b"AU", BOTH), "zero address", owner)
    refused(v3(patient, ZERO, "Treatment", now, now + 86400, b"AU", BOTH), "zero address", owner)
    refused(v3(patient, doctor, "Treatment", now + 200, now + 100, b"AU", BOTH), "notBefore > expiry", owner)
    refused(v3(patient, doctor, "Treatment", now - 100, now - 1, b"AU", BOTH), "expiry in the past", owner)
    v2 = c.functions.mintConsent                                      # v2 signature: notBefore = now
    refused(v2(ZERO, doctor, "Treatment", now + 86400), "zero address", owner)
    refused(v2(patient, ZERO, "Treatment", now + 86400), "zero address", owner)
    refused(v2(patient, doctor, "Treatment", now - 1), "notBefore > expiry", owner)   # a past expiry is caught by the window check first
    assert c.functions.balanceOf(patient).call() == 0
    tid, _ = mint(c, owner, patient, doctor, now, BOTH)
    assert tid == 1                                                   # the refused calls used no token number
    assert c.functions.ownerOf(1).call() == patient and c.functions.checkValid(1).call() is True


def test_mint_and_revoke_emit_their_events():
    w3, c, owner, _, patient, doctor, now = chain()
    tid, tx = mint(c, owner, patient, doctor, now, OWNER_ONLY)
    rc = w3.eth.get_transaction_receipt(tx)
    m = c.events.ConsentMinted().process_receipt(rc)
    assert len(m) == 1
    assert dict(m[0]["args"]) == {"tokenId": tid, "patient": patient, "requester": doctor, "purposeHash": w3.keccak(text="Treatment"),
                                  "notBefore": now, "expiry": now + 86400, "jurisdiction": b"AU"}
    i = c.events.Issued().process_receipt(rc)
    assert len(i) == 1 and dict(i[0]["args"]) == {"from": owner, "to": patient, "tokenId": tid, "burnAuth": OWNER_ONLY}
    assert c.functions.burnAuth(tid).call() == OWNER_ONLY
    rc = w3.eth.get_transaction_receipt(c.functions.revoke(tid).transact({"from": owner}))
    r = c.events.ConsentRevoked().process_receipt(rc)
    assert len(r) == 1 and dict(r[0]["args"]) == {"tokenId": tid, "by": owner}
    assert c.functions.checkValid(tid).call() is False


def test_burn_follows_the_burn_authorisation_of_the_token():
    w3, c, owner, stranger, patient, doctor, now = chain()
    t, _ = mint(c, owner, patient, doctor, now, ISSUER_ONLY)
    refused(c.functions.burn(t), "burn not authorised", patient)      # the holder may not burn
    refused(c.functions.burn(t), "burn not authorised", stranger)
    burned(w3, c, t, owner)
    t, _ = mint(c, owner, patient, doctor, now, OWNER_ONLY)
    refused(c.functions.burn(t), "burn not authorised", owner)        # the issuer may not burn
    refused(c.functions.burn(t), "burn not authorised", stranger)
    burned(w3, c, t, patient)
    for by in (owner, patient):
        t, _ = mint(c, owner, patient, doctor, now, BOTH)
        refused(c.functions.burn(t), "burn not authorised", stranger)
        burned(w3, c, t, by)
    t, _ = mint(c, owner, patient, doctor, now, NEITHER)
    for by in (owner, patient, stranger):
        refused(c.functions.burn(t), "burn not authorised", by)       # nobody may burn
    assert c.functions.checkValid(t).call() is True
    assert c.functions.balanceOf(patient).call() == 1                 # only the Neither token is left
