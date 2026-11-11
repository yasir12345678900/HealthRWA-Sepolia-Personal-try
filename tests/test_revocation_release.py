"""Revocation by crypto-shredding and consent-bound release (thesis Chapter 6, Algorithms 6.4 and 6.5).
The key store, the consent-bound encrypted copy, the release of the requested modules on ALLOW and a verified proof,
the revocation with its authority rule, the deletion, unintelligibility and notification tests of Section 6.5.3, and
the limits of the claim. Offline: no network and no keys from the environment. The chain is replaced by a callable,
and one test runs the ConsentSBTv3 bytecode on an in-memory EVM (eth-tester)."""
import copy, json, os, uuid
import pytest
from datetime import datetime, timedelta
from eth_account import Account
from web3 import Web3
from models.consent import Consent
from database import audit_db, consent_db, db
from services import (access_service, data_vault, identity_service, key_store, notification_service, release_service,
                      revocation_service)
from services.data_vault import DataVault, CopyNotFoundError, ScopeError
from services.identity_service import sign_consent
from services.key_store import KeyStore, DecryptionError, KeyDestroyedError, KeyNotFoundError
from services.release_service import release, GRANTED, DENIED
from services.revocation_service import (revoke, complete_revocation, sign_revocation, verify_revocation_signature,
                                         majority_reached, revocation_evidence, NO_CHAIN)
from services.state_service import lifecycle_state

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NOW = datetime(2026, 11, 11, 10, 0, 0)               # the time t of the requests, nine days before the patient is 18
MAJORITY = datetime(2026, 11, 20)                    # the eighteenth birthday of a patient born on 2008-11-20
PATIENT, DOCTOR, REGISTRAR = "did:patient:layan", "did:hospital:001", "did:hospital:002"
G = ["did:parent:A", "did:parent:B"]

# The source record of the treating institution. The consent-bound copy is taken from it and it is never changed.
RECORD = {"Observation": [{"date": "2026-10-02", "code": "8302-2", "description": "Body Height", "value": 167.7, "units": "cm"}],
          "Medication": [{"start": "2026-09-14", "description": "Amoxicillin 250 MG Oral Capsule"}],
          "Condition": [{"start": "2025-03-01", "description": "Childhood asthma"}],
          "Procedure": [{"date": "2026-08-30", "description": "Spirometry"}]}
PROOF = {"mode": "groth16", "proof": {"pi_a": ["1", "2"]}, "publicSignals": ["1794391200", "1", "1", "16725"]}


def source(patient_did, scope):
    return {m: copy.deepcopy(RECORD[m]) for m in scope if m in RECORD}


def accept(proof):
    return True


def make_consent(guardians=None, **kw):
    """An issued consent as the earlier steps leave it: approved by its guardians, token recorded, stored."""
    guardians = list(G if guardians is None else guardians)
    c = Consent(consent_id="rv-" + str(uuid.uuid4()), patient_did=PATIENT, requester_did=DOCTOR, guardian_dids=guardians,
                purpose="Treatment", scope=["Observation", "Medication"], threshold=len(guardians),
                start_date=(NOW - timedelta(days=1)).isoformat(), expiry_date=(NOW + timedelta(days=30)).isoformat(),
                state="ACTIVE", token_id="SBT-41", patient_birth_date="2008-11-20")
    for g in guardians:
        sig, addr = sign_consent(g, c.consent_id)
        c.signatures.append(g)
        c.signature_data[g] = {"signer": addr, "signature": sig}
    c.token_address, c.commitment = "0x" + "5a" * 20, "0x" + "c0" * 32
    c.commitment_opening = {"blinding": "271828182845904523536028747135266249775724709369995"}
    c.zk_secret = "314159265358979323846264338327950288419716939937510"
    for k, v in kw.items():
        setattr(c, k, v)
    consent_db.save(c)
    return c


@pytest.fixture()
def vault():
    return DataVault(KeyStore())


def sealed_consent(vault, **kw):
    c = make_consent(**kw)
    vault.seal_from_source(c, source)
    return c


def ask(c, vault, requester=DOCTOR, scope=("Observation",), purpose="Treatment", context="AU", now=NOW, **kw):
    kw.setdefault("proof", PROOF)
    kw.setdefault("verify_proof", accept)
    return release(c, requester, list(scope) if scope is not None else None, purpose, context, now=now, vault=vault, **kw)


def chain(calls=None, status=1):
    """Stands for the on-chain revoke: records the token it is asked to revoke and returns a receipt."""
    def onchain_revoke(consent):
        if calls is not None:
            calls.append(consent.token_id)
        return {"tx_hash": "0x" + "ab" * 32, "status": status, "block_number": 123, "gas_used": 32980,
                "revocation_root": "0x" + "1d" * 32}
    return onchain_revoke


def signed(did, c, **kw):
    return sign_revocation(did, c.consent_id, **kw)[0]


def rows(consent_id, action=None):
    return [e for e in audit_db.get() if e["consent_id"] == consent_id and (action is None or e["action"] == action)]


def stored_keys(keys, consent_id=None):
    """What an operator who reads the storage of the key store finds: (consent, module) -> key bytes."""
    found = {(c, m): bytes(k) for c, m, k in keys._db.execute("SELECT consent_id, module, key FROM keys")}
    return {k: v for k, v in found.items() if consent_id is None or k[0] == consent_id}


def leaves(value):
    if isinstance(value, dict):
        for v in value.values():
            yield from leaves(v)
    elif isinstance(value, (list, tuple, set)):
        for v in value:
            yield from leaves(v)
    else:
        yield value


def holds_a_key(value, keys):
    """True when a value that was given out contains one of the keys, as bytes or as text."""
    secrets = [k for k in keys] + [k.hex() for k in keys]
    return any((isinstance(leaf, (bytes, bytearray)) and any(isinstance(s, bytes) and s in bytes(leaf) for s in secrets))
               or (isinstance(leaf, str) and any(isinstance(s, str) and s in leaf.lower() for s in secrets))
               for leaf in leaves(value))


# ---------------------------------------------------------------------------
# Key store
# ---------------------------------------------------------------------------
def test_cipher_is_aes_256_gcm_by_the_published_vector():
    # McGrew and Viega, The Galois/Counter Mode of Operation, test case 16 (256-bit key, 96-bit nonce, with associated data)
    key = bytes.fromhex("feffe9928665731c6d6a8f9467308308feffe9928665731c6d6a8f9467308308")
    plain = bytes.fromhex("d9313225f88406e5a55909c5aff5269a86a7a9531534f7da2e4c303d8a318a72"
                          "1c3c0c95956809532fcf0e2449a6b525b16aedf5aa0de657ba637b39")
    aad = bytes.fromhex("feedfacedeadbeeffeedfacedeadbeefabaddad2")
    nonce = bytes.fromhex("cafebabefacedbaddecaf888")
    cipher = bytes.fromhex("522dc1f099567d07f47f37a32a84427d643a8cdcbfe5c0c97598a2bd2555d1aa"
                           "8cb08e48590dbb3da7b08b1056828838c5f61e6393ba7a0abcc9f662")
    tag = bytes.fromhex("76fc6ece0f4e1768cddf8853bb2d551b")
    assert key_store.ALGORITHM == "AES-256-GCM" and key_store.KEY_BYTES == 32
    assert [name for name, _ in key_store._LIBRARIES] == ["cryptography", "pycryptodome"]
    loaded = [name for name, _ in key_store._LIBRARIES if key_store._cipher(name) is not None]
    # the library in use is the first that loads: the cryptography package wherever it can be loaded
    assert loaded and key_store.CIPHER_BACKEND == loaded[0]
    assert (key_store._seal, key_store._unseal) == key_store._cipher(key_store.CIPHER_BACKEND)
    for name in loaded:                                                # every library that loads is the standard cipher
        seal, unseal = key_store._cipher(name)
        assert seal(key, nonce, plain, aad) == cipher + tag
        assert unseal(key, nonce, cipher + tag, aad) == plain
        for changed in (cipher[:-1] + bytes([cipher[-1] ^ 1]) + tag, cipher + tag[:-1] + bytes([tag[-1] ^ 1]), tag[:8]):
            with pytest.raises(DecryptionError):
                unseal(key, nonce, changed, aad)
        with pytest.raises(DecryptionError):
            unseal(key, nonce, cipher + tag, aad + b"\x00")


def test_key_store_holds_one_aes256_key_per_consent_and_module():
    keys = KeyStore()
    a, b, c = keys.create_key("c-1", "Observation"), keys.create_key("c-1", "Medication"), keys.create_key("c-2", "Observation")
    assert len({a, b, c}) == 3
    assert keys.create_key("c-1", "Observation") == a                  # the pair has one key, a second call makes no other
    raw = stored_keys(keys)
    assert set(raw) == {("c-1", "Observation"), ("c-1", "Medication"), ("c-2", "Observation")}
    assert all(len(k) == 32 for k in raw.values()) and len(set(raw.values())) == 3
    assert keys.key_ids("c-1") == {"Medication": b, "Observation": a}
    assert keys.has_key("c-1") and keys.has_key("c-1", "Medication") and not keys.has_key("c-1", "Procedure")


def test_ciphertext_opens_only_for_its_own_consent_and_module():
    keys = KeyStore()
    for pair in (("c-1", "Observation"), ("c-1", "Medication"), ("c-2", "Observation")):
        keys.create_key(*pair)
    sealed = keys.encrypt("c-1", "Observation", b"body height 167.7 cm")
    assert b"167.7" not in sealed["ciphertext"] and len(sealed["nonce"]) == 12
    assert keys.decrypt("c-1", "Observation", sealed["nonce"], sealed["ciphertext"]) == b"body height 167.7 cm"
    again = keys.encrypt("c-1", "Observation", b"body height 167.7 cm")
    assert again["nonce"] != sealed["nonce"] and again["ciphertext"] != sealed["ciphertext"]      # a fresh nonce every time
    for other in (("c-1", "Medication"), ("c-2", "Observation")):                                  # another module, another consent
        with pytest.raises(DecryptionError):
            keys.decrypt(*other, sealed["nonce"], sealed["ciphertext"])
    changed = bytes([sealed["ciphertext"][0] ^ 1]) + sealed["ciphertext"][1:]
    with pytest.raises(DecryptionError):
        keys.decrypt("c-1", "Observation", sealed["nonce"], changed)
    with pytest.raises(KeyNotFoundError):
        keys.decrypt("c-9", "Observation", sealed["nonce"], sealed["ciphertext"])
    with pytest.raises(KeyNotFoundError):
        keys.encrypt("c-1", "Procedure", b"no key was made for this module")


def test_no_operation_of_the_key_store_gives_out_a_key():
    keys = KeyStore()
    given_out = [keys.create_key("c-1", "Observation"), keys.create_key("c-1", "Medication")]
    raw = list(stored_keys(keys).values())
    given_out += [keys.key_ids("c-1"), keys.encrypt("c-1", "Observation", b"x"), keys.has_key("c-1"),
                  keys.destroy("c-1"), keys.destruction_record("c-1"), keys.is_destroyed("c-1")]
    assert len(raw) == 2 and not holds_a_key(given_out, raw)
    assert holds_a_key({"leak": raw[0]}, raw) and holds_a_key(["0x" + raw[1].hex()], raw)       # the check itself finds a key
    assert sorted(n for n in dir(keys) if not n.startswith("_")) == [
        "create_key", "decrypt", "destroy", "destruction_record", "encrypt", "has_key", "is_destroyed", "key_ids", "path"]


def test_destroy_removes_every_key_of_the_consent_and_no_other_key():
    keys = KeyStore()
    a, b = keys.create_key("c-1", "Observation"), keys.create_key("c-1", "Medication")
    keys.create_key("c-2", "Observation")
    mine, other = keys.encrypt("c-1", "Observation", b"mine"), keys.encrypt("c-2", "Observation", b"other")
    evidence = keys.destroy("c-1", now=NOW)
    assert evidence["keys_destroyed"] == 2 and evidence["keys_remaining"] == 0 and set(evidence["key_ids"]) == {a, b}
    assert evidence["destroyed_at"] == NOW.isoformat() and sorted(evidence["modules"]) == ["Medication", "Observation"]
    assert stored_keys(keys, "c-1") == {} and not keys.has_key("c-1") and keys.is_destroyed("c-1")
    with pytest.raises(KeyDestroyedError):
        keys.decrypt("c-1", "Observation", mine["nonce"], mine["ciphertext"])
    with pytest.raises(KeyDestroyedError):                             # no new key is made for a consent whose keys are destroyed
        keys.create_key("c-1", "Observation")
    assert keys.decrypt("c-2", "Observation", other["nonce"], other["ciphertext"]) == b"other" and not keys.is_destroyed("c-2")
    second = keys.destroy("c-1")                                       # destroying again finds nothing more to destroy
    assert second["keys_destroyed"] == 0 and second["destroyed_at"] == NOW.isoformat() and set(second["key_ids"]) == {a, b}
    assert key_store.KeyStore().destroy("c-3")["keys_destroyed"] == 0


def test_destroyed_key_bytes_are_overwritten_in_the_key_store_file(tmp_path):
    path = tmp_path / "keystore" / "keys.db"
    keys = KeyStore(str(path))
    keys.create_key("c-1", "Observation"), keys.create_key("c-2", "Observation")
    k1, k2 = stored_keys(keys)[("c-1", "Observation")], stored_keys(keys)[("c-2", "Observation")]
    assert k1 in path.read_bytes() and k2 in path.read_bytes()        # before: an operator can read both keys in the file
    if os.name == "posix":
        assert path.stat().st_mode & 0o777 == 0o600                   # and only the account of the Controller may open it
    keys.destroy("c-1")
    assert k1 not in path.read_bytes() and k2 in path.read_bytes()    # after: the bytes of the destroyed key are gone
    assert [p.name for p in path.parent.iterdir()] == ["keys.db"]     # and no journal file holds an old page
    reopened = KeyStore(str(path))                                    # the destruction survives a restart of the Controller
    assert reopened.is_destroyed("c-1") and reopened.has_key("c-2", "Observation")
    with pytest.raises(KeyDestroyedError):
        reopened.create_key("c-1", "Observation")


def test_key_store_and_vault_of_the_controller_are_kept_apart(monkeypatch, tmp_path):
    monkeypatch.delenv("HALAH_KEYSTORE_PATH", raising=False)
    monkeypatch.delenv("HALAH_VAULT_PATH", raising=False)
    keys_file, vault_file = key_store.default_path(), data_vault.default_path()
    assert keys_file != vault_file and os.path.dirname(keys_file) != os.path.dirname(vault_file)
    assert db.db_path() not in (keys_file, vault_file)
    monkeypatch.setenv("HALAH_KEYSTORE_PATH", str(tmp_path / "k.db"))
    monkeypatch.setenv("HALAH_VAULT_PATH", ":memory:")
    assert key_store.default_path() == str(tmp_path / "k.db") and data_vault.default_path() is None


# ---------------------------------------------------------------------------
# The consent-bound encrypted copy
# ---------------------------------------------------------------------------
def test_vault_seals_each_module_under_its_own_key_and_holds_no_plaintext_and_no_key(tmp_path):
    keys_path, vault_path = tmp_path / "keystore" / "keys.db", tmp_path / "vault" / "vault.db"
    keys = KeyStore(str(keys_path))
    vault = DataVault(keys, str(vault_path))
    c = make_consent()
    sealed = vault.seal_from_source(c, source)
    assert sealed["modules"] == ["Observation", "Medication"] == c.scope
    assert sealed["key_ids"] == keys.key_ids(c.consent_id) and len(set(sealed["key_ids"].values())) == 2
    vault_bytes, keys_bytes = vault_path.read_bytes(), keys_path.read_bytes()
    for marker in (b"Amoxicillin", b"Body Height", b"167.7"):          # the record is in neither file, as text or as hex
        for stored in (vault_bytes, keys_bytes):
            assert marker not in stored and marker.hex().encode() not in stored
    copy_held = vault.export_copy(c.consent_id)
    for key in stored_keys(keys).values():                             # the keys are held apart from the encrypted copy
        assert key not in vault_bytes and key.hex().encode() not in vault_bytes and not holds_a_key(copy_held, [key])
    for blob in copy_held.values():
        assert bytes.fromhex(blob["ciphertext"]) not in keys_bytes and blob["algorithm"] == "AES-256-GCM"
    assert vault.open(c.consent_id, ["Medication"]) == {"Medication": RECORD["Medication"]}       # only the module asked for
    assert vault.open(c.consent_id, ["Observation", "Medication"]) == {m: RECORD[m] for m in c.scope}
    assert vault.modules(c.consent_id) == ["Medication", "Observation"] and vault.has_copy(c.consent_id, "Observation")


def test_vault_takes_no_module_outside_the_consent_scope(vault):
    c = make_consent()
    with pytest.raises(ScopeError):
        vault.seal(c, {"Observation": RECORD["Observation"], "Procedure": RECORD["Procedure"]})
    assert not vault.has_copy(c.consent_id) and not vault.key_store.has_key(c.consent_id)         # nothing sealed, no key made
    vault.seal_from_source(c, source)
    with pytest.raises(CopyNotFoundError):
        vault.open(c.consent_id, ["Observation", "Procedure"])
    assert not vault.key_store.has_key(c.consent_id, "Procedure")
    with pytest.raises(data_vault.VaultError):                         # and no copy is sealed for a revoked consent
        vault.seal_from_source(make_consent(revoked=True, state="REVOKED"), source)
    other = make_consent()
    with pytest.raises(data_vault.VaultError):                         # records that cannot be serialised: nothing is sealed
        vault.seal(other, {"Observation": RECORD["Observation"], "Medication": object()})
    assert not vault.has_copy(other.consent_id) and not vault.key_store.has_key(other.consent_id)


def test_vault_returns_a_table_of_the_record_as_a_table(vault):
    import pandas as pd
    frame = pd.DataFrame([{"DATE": "2017-01-01", "PATIENT": "fe621c76", "DESCRIPTION": "Body Height", "VALUE": 167.7, "UNITS": "cm"},
                          {"DATE": "2018-01-01", "PATIENT": "fe621c76", "DESCRIPTION": "Body Weight", "VALUE": 60.2, "UNITS": "kg"}])
    c = make_consent()
    vault.seal(c, {"Observation": frame})
    out = vault.open(c.consent_id, ["Observation"])["Observation"]
    assert isinstance(out, pd.DataFrame) and list(out.columns) == list(frame.columns)
    assert out.to_dict("records") == frame.to_dict("records")


# ---------------------------------------------------------------------------
# Algorithm 6.5: consent-bound data release
# ---------------------------------------------------------------------------
def test_release_on_allow_and_verified_proof_delivers_only_the_requested_modules(vault):
    c = sealed_consent(vault)
    r = ask(c, vault, scope=["Observation"], time_label="block-timestamp", proof_ref={"tx": "0x" + "ef" * 32})
    assert r["outcome"] == GRANTED and r["allow"] is True and r["deny_code"] is None and r["deny_codes"] == []
    assert r["data"] == {"Observation": RECORD["Observation"]}          # Medication is consented, but it was not requested
    assert r["modules"] == ["Observation"] and r["proof_verified"] is True and r["state"] == "ACTIVE"
    # the DATA_ACCESS record: outcome GRANTED, the scope, the requester, the time and a reference to the proof
    e = r["audit_event"]
    assert e is rows(c.consent_id, "DATA_ACCESS")[-1]
    assert (e["result"], e["actor_did"], e["scope"], e["purpose"]) == ("GRANTED", DOCTOR, ["Observation"], "Treatment")
    assert e["timestamp"] and e["metadata"]["decision_time"] == NOW.isoformat() and e["metadata"]["time_source"] == "block-timestamp"
    ref = e["metadata"]["proof_reference"]
    assert ref == release_service.proof_reference(PROOF, {"tx": "0x" + "ef" * 32})
    assert len(ref["digest"]) == 66 and ref["mode"] == "groth16" and ref["reference"] == {"tx": "0x" + "ef" * 32}
    assert release_service.proof_reference(dict(PROOF, publicSignals=["0"]))["digest"] != ref["digest"]
    assert e["metadata"]["zk_proof_verified"] is True and e["metadata"]["modules_released"] == ["Observation"]
    assert e["metadata"]["deny_code"] is None and e["metadata"]["decision_matrix"]["ALLOW"] is True
    assert e["metadata"]["key_references"] == {"Observation": vault.key_store.key_ids(c.consent_id)["Observation"]}
    assert e["tx_hash"] is None and e["block_number"] is None and e["onchain"] is False          # the record stays off chain
    # the STATE_CHECK record of the evaluation is written before it
    check = r["state_check_event"]
    assert rows(c.consent_id)[-2:] == [check, e] and check["action"] == "STATE_CHECK" and check["result"] == "ACTIVE"
    # the requester receives decrypted modules and never a key
    assert not holds_a_key(r, list(stored_keys(vault.key_store).values()))
    json.dumps(r, default=str)


@pytest.mark.parametrize("label, proof, verifier, reason", [
    ("the proof does not verify", PROOF, lambda p: False, "did not verify"),
    ("the verifier answers something other than True", PROOF, lambda p: "verified", "did not verify"),
    ("the verifier fails", PROOF, lambda p: 1 / 0, "verifier failed"),
    ("no verifier", PROOF, None, "no proof verifier"),
    ("no proof", None, accept, "no proof was presented")])
def test_release_needs_a_verified_proof(vault, label, proof, verifier, reason):
    c = sealed_consent(vault)
    r = ask(c, vault, scope=["Observation", "Medication"], proof=proof, verify_proof=verifier)
    assert r["outcome"] == DENIED and r["allow"] is True and r["proof_verified"] is False      # the rule allowed, the proof did not hold
    assert r["deny_code"] == "PROOF-INVALID" and reason in r["reason"] and r["data"] == {} and r["modules"] == []
    e = rows(c.consent_id, "DATA_ACCESS")[-1]
    assert e["result"] == "DENIED" and e["metadata"]["deny_code"] == "PROOF-INVALID" and e["metadata"]["modules_released"] == []
    assert e["metadata"]["zk_proof_verified"] is False and e["scope"] == ["Observation", "Medication"]


@pytest.mark.parametrize("label, request_kw, code, failed", [
    ("a module outside the consent scope", dict(scope=["Observation", "Procedure"]), "OUT-OF-SCOPE", "VP"),
    ("an empty scope", dict(scope=[]), "OUT-OF-SCOPE", "VP"),
    ("no scope", dict(scope=None), "OUT-OF-SCOPE", "VP"),
    ("another purpose than the consent purpose", dict(purpose="Research"), "PURPOSE-MISMATCH", "VP"),
    ("no declared purpose", dict(purpose=None), "PURPOSE-MISMATCH", "VP"),
    ("another context", dict(context="US"), "CONTEXT-MISMATCH", "VP"),
    ("before the start of the window", dict(now=NOW - timedelta(days=2)), "PRE-VALIDITY", "VT"),
    ("after the expiry, where the state code is reported", dict(now=NOW + timedelta(days=31)), "EXPIRED", "VT")])
def test_release_denied_with_the_deny_code_of_the_failed_check(vault, label, request_kw, code, failed):
    c = sealed_consent(vault)
    opened, verified = [], []
    real_open = vault.open
    vault.open = lambda consent_id, modules: opened.append(modules) or real_open(consent_id, modules)
    r = ask(c, vault, verify_proof=lambda p: verified.append(p) or True, **request_kw)
    assert r["outcome"] == DENIED and r["allow"] is False and r["deny_code"] == code and code in r["deny_codes"]
    assert r["decision"][failed] is False and r["decision"]["ALLOW"] is False
    assert r["data"] == {} and opened == [] and verified == []          # nothing is decrypted, and no proof is verified
    e = rows(c.consent_id, "DATA_ACCESS")[-1]
    assert e is r["audit_event"] and e["result"] == "DENIED" and e["metadata"]["deny_code"] == code
    assert e["metadata"]["deny_codes"] == r["deny_codes"] and e["metadata"]["modules_released"] == []
    assert e["scope"] == list(request_kw.get("scope", ["Observation"]) or []) and e["onchain"] is False
    assert rows(c.consent_id, "STATE_CHECK")[-1]["metadata"]["ALLOW"] is False
    vault.open = real_open
    assert ask(c, vault)["outcome"] == GRANTED                          # the same consent still serves a request that is in order


def test_release_refuses_a_requester_the_consent_does_not_name(vault):
    c = sealed_consent(vault)
    # the research registrar asks for Procedure records for a study (Event 2 of the case study)
    r = ask(c, vault, requester=REGISTRAR, scope=["Procedure"], purpose="Research")
    assert r["outcome"] == DENIED and r["decision"]["VI"] is False and r["decision"]["VP"] is False
    assert r["deny_code"] == "PURPOSE-MISMATCH"                         # the policy reason that is reported
    assert {"IDENTITY-INVALID", "PURPOSE-MISMATCH", "OUT-OF-SCOPE"} <= set(r["deny_codes"]) and r["data"] == {}
    e = rows(c.consent_id, "DATA_ACCESS")[-1]
    assert (e["result"], e["actor_did"], e["purpose"], e["scope"]) == ("DENIED", REGISTRAR, "Research", ["Procedure"])
    # a request in scope and with the consent purpose is refused as well, because VI fails
    for requester in (REGISTRAR, "did:hospital:999", "", None):
        r = ask(c, vault, requester=requester)
        assert r["outcome"] == DENIED and r["decision"]["VI"] is False and r["deny_code"] == "IDENTITY-INVALID" and r["data"] == {}
    # an approval that does not verify fails VI too: the release checks the approvals unless it is told not to
    c.signature_data[G[0]]["signature"] = "0x" + "11" * 65
    assert ask(c, vault)["deny_code"] == "IDENTITY-INVALID"
    assert ask(c, vault, verify_sig=False)["outcome"] == GRANTED


def test_release_gives_the_declared_purpose_and_scope_to_the_decision_function(vault, monkeypatch):
    c = sealed_consent(vault)
    # with the access service that is installed: a request without a purpose and without a scope is compared and refused
    m = release_service.decide_request(c, DOCTOR, None, None, now=NOW)
    assert m["ALLOW"] is False and m["VU"] is False and m["VS"] is False
    assert {"PURPOSE-MISMATCH", "OUT-OF-SCOPE"} <= set(m["DENY"])

    # The decision function of the thesis design takes the declared purpose and the requested scope and returns the
    # three conditions of VP and the deny codes. A stand-in with that interface takes its place here, so that this
    # test holds whichever version of the access service is installed.
    earlier, seen = access_service.evaluate_allow, []

    def evaluate_allow(consent, requester_jurisdiction="AU", now=None, verify_sig=None, verify_did=None, requester_did=None,
                       request_purpose=None, request_scope=None):
        seen.append({"requester": requester_did, "purpose": request_purpose, "scope": request_scope,
                     "context": requester_jurisdiction, "now": now, "verify_sig": verify_sig})
        six = earlier(consent, requester_jurisdiction, now=now, verify_sig=verify_sig, verify_did=verify_did,
                      requester_did=requester_did)
        m = {k: six[k] for k in ("VI", "VA", "VP", "VT", "VL", "ALLOW")}
        waiting = any(t["satisfied"] is not True for t in consent.triggers)
        vu = request_purpose is None or request_purpose == consent.purpose
        vs = request_scope is None or (len(request_scope) > 0 and set(request_scope) <= set(consent.scope))
        deny = (["AWAITING-TRIGGER"] if waiting else []) + ([] if vu else ["PURPOSE-MISMATCH"]) + ([] if vs else ["OUT-OF-SCOPE"])
        m.update(VU=vu, VS=vs, VX=True, VP=m["VP"] and vu and vs, VL=m["VL"] and not waiting, DENY=deny)
        m["ALLOW"] = m["ALLOW"] and not deny
        return m
    monkeypatch.setattr(access_service, "evaluate_allow", evaluate_allow)

    r = ask(c, vault, scope=["Medication"])
    assert r["outcome"] == GRANTED and r["data"] == {"Medication": RECORD["Medication"]} and r["decision"]["DENY"] == []
    assert seen[-1] == {"requester": DOCTOR, "purpose": "Treatment", "scope": ["Medication"], "context": "AU", "now": NOW,
                        "verify_sig": identity_service.verify_signature}
    # no purpose and no scope reach the function as an empty purpose and an empty scope, never as "not given"
    r = ask(c, vault, scope=None, purpose=None)
    assert (seen[-1]["purpose"], seen[-1]["scope"]) == ("", [])
    assert r["outcome"] == DENIED and r["deny_codes"] == ["PURPOSE-MISMATCH", "OUT-OF-SCOPE"] and r["deny_code"] == "PURPOSE-MISMATCH"
    assert release_service.decide_request(c, DOCTOR, None, None, now=NOW)["ALLOW"] is False
    assert (seen[-1]["purpose"], seen[-1]["scope"]) == ("", [])
    # the code of a consent that waits on a trigger comes from the decision function and is recorded as it is
    c.triggers = [{"id": "trg-1", "kind": "attestation", "event": "loss-of-capacity", "attester_role": "doctor",
                   "satisfied": False, "attestation_id": None}]
    r = ask(c, vault, scope=["Medication"])
    assert r["outcome"] == DENIED and r["deny_code"] == "AWAITING-TRIGGER" and r["decision"]["VL"] is False and r["data"] == {}
    assert rows(c.consent_id, "DATA_ACCESS")[-1]["metadata"]["deny_codes"] == ["AWAITING-TRIGGER"]
    c.triggers[0]["satisfied"] = True
    assert ask(c, vault, scope=["Medication"])["outcome"] == GRANTED


def test_release_cannot_open_a_module_outside_the_consent_scope_even_on_a_wrong_decision(vault):
    c = sealed_consent(vault)

    def wrong(consent, requester, scope, purpose, context, now):        # a decision function that allows everything
        return {"VI": True, "VA": True, "VP": True, "VT": True, "VL": True, "ALLOW": True, "DENY": []}
    r = ask(c, vault, scope=["Observation", "Procedure"], decide=wrong)
    assert r["outcome"] == DENIED and r["deny_code"] == "COPY-UNAVAILABLE"
    assert r["data"] == {}                                              # all or nothing: not even the module that has a copy
    assert rows(c.consent_id, "DATA_ACCESS")[-1]["metadata"]["deny_code"] == "COPY-UNAVAILABLE"
    # a decision that cannot be evaluated, or that allows and names a deny code, releases nothing
    assert ask(c, vault, decide=lambda *a: 1 / 0)["deny_code"] == "RECORD-INVALID"
    assert ask(c, vault, decide=lambda *a: dict(wrong(*a), DENY=["REVOKED"]))["outcome"] == DENIED


def test_release_seals_the_copy_from_the_source_record_when_the_vault_has_none(vault):
    c = make_consent()
    r = ask(c, vault, scope=["Medication"])                             # no copy and no source: nothing to release
    assert r["outcome"] == DENIED and r["deny_code"] == "COPY-UNAVAILABLE" and not vault.has_copy(c.consent_id)
    asked = []
    r = ask(c, vault, scope=["Medication"], source=lambda did, scope: asked.append((did, scope)) or source(did, scope))
    assert r["outcome"] == GRANTED and r["data"] == {"Medication": RECORD["Medication"]}
    assert asked == [(PATIENT, ["Observation", "Medication"])]          # the copy holds the consent scope, sealed per module
    assert vault.modules(c.consent_id) == ["Medication", "Observation"]
    ask(c, vault, scope=["Observation"], source=lambda did, scope: asked.append((did, scope)) or source(did, scope))
    assert len(asked) == 1                                              # the source is not read again once the copy exists


# ---------------------------------------------------------------------------
# Algorithm 6.4: who may revoke
# ---------------------------------------------------------------------------
def test_revocation_signature_binds_consent_revoker_action_and_chain():
    sig, address = sign_revocation("did:parent:A", "c-1")
    assert sig.startswith("0x") and len(sig) == 132 and address == identity_service.guardian_address("did:parent:A")
    assert verify_revocation_signature("did:parent:A", "c-1", sig) is True
    assert verify_revocation_signature("did:parent:A", "c-2", sig) is False      # another consent
    assert verify_revocation_signature("did:parent:B", "c-1", sig) is False      # another revoker
    assert verify_revocation_signature("did:parent:A", "c-1", sig, chain_id=1) is False      # another chain
    approval, _ = sign_consent("did:parent:A", "c-1")
    assert verify_revocation_signature("did:parent:A", "c-1", approval) is False  # an approval is not a revocation
    assert identity_service.verify_signature("did:parent:A", "c-1", sig) is False # and a revocation is not an approval
    for bad in (None, "", "0x1234", "0x" + "11" * 65):
        assert verify_revocation_signature("did:parent:A", "c-1", bad) is False
    # a wallet-held key: with a registered address only the wallet signs, and the derived key is refused
    wallet = Account.from_key(Web3.keccak(text="the wallet of guardian A in this test"))
    wallet_sig, wallet_address = sign_revocation("did:parent:A", "c-1", signer=wallet)
    assert verify_revocation_signature("did:parent:A", "c-1", wallet_sig, address=wallet_address) is True
    assert verify_revocation_signature("did:parent:A", "c-1", sig, address=wallet_address) is False
    assert verify_revocation_signature("did:parent:A", "c-1", wallet_sig) is False
    assert verify_revocation_signature("did:parent:A", "c-1", sig, allow_demo_key=False) is False
    data = revocation_service.revocation_typed_data("did:parent:A", "c-1")
    assert data["primaryType"] == "Revocation" and data["message"]["action"] == "REVOKE"
    assert data["domain"]["chainId"] == data["message"]["chainId"] == identity_service.CHAIN_ID


def test_one_guardian_alone_revokes_before_majority(vault):
    c = sealed_consent(vault)
    assert c.threshold == 2 and ask(c, vault, scope=c.scope)["outcome"] == GRANTED
    calls = []
    out = revoke(c, "did:parent:B", signed("did:parent:B", c), now=NOW, time_label="block-timestamp",
                 onchain_revoke=chain(calls), vault=vault)
    assert out["result"] == "REVOKED" and out["revoked"] is True and out["complete"] is True and out["pending"] == []
    assert (out["revoker_role"], out["basis"], out["after_majority"]) == ("Guardian", "one guardian before majority", False)
    # the on-chain revoke was submitted once, for the token of this consent, and its receipt is recorded
    assert calls == ["SBT-41"] and out["onchain"]["status"] == "SUCCESS" and out["onchain"]["gas_used"] == 32980
    chain_row = rows(c.consent_id, "ONCHAIN_REVOKE")[-1]
    assert chain_row["result"] == "SUCCESS" and chain_row["tx_hash"] == "0x" + "ab" * 32 and chain_row["onchain"] is True
    assert chain_row["metadata"]["revocation_root"] == out["onchain"]["revocation_root"] == "0x" + "1d" * 32
    # the consent is REVOKED in the store, with the revoking party and the time
    stored = consent_db.get(c.consent_id)
    assert stored.revoked is True and stored.state == "REVOKED" and lifecycle_state(stored, NOW) == "REVOKED"
    assert stored.revoked_at == NOW.isoformat() and stored.revoked_by == "did:parent:B"
    # the encrypted copy is deleted and its keys are destroyed
    assert not vault.has_copy(c.consent_id) and not vault.key_store.has_key(c.consent_id) and vault.key_store.is_destroyed(c.consent_id)
    assert out["shredded"]["modules_deleted"] == ["Medication", "Observation"] and out["shredded"]["keys_destroyed"] == 2
    assert out["shredded"]["copies_remaining"] == 0 and out["shredded"]["keys_remaining"] == 0 and out["shredded"]["shredded"] is True
    # the link between the token and the patient and the opening of the commitment are deleted, also in the stored record
    assert out["link"]["status"] == "DELETED"
    assert set(out["link"]["deleted"]) == {"commitment_opening", "zk_secret", "token_address", "token_id", "commitment"}
    persisted = [r for r in db.all_rows("consents") if r["consent_id"] == c.consent_id][0]
    for field in revocation_service.LINK_FIELDS:
        assert getattr(stored, field) is None and persisted[field] is None
    assert persisted["revoked"] is True and persisted["patient_did"] == PATIENT
    # the next request is refused with REVOKED
    r = ask(c, vault, scope=c.scope)
    assert r["outcome"] == DENIED and r["deny_code"] == "REVOKED" and r["data"] == {}
    # the revocation is recorded in E with the revoking party, the time and the notifications
    e = out["audit_event"]
    assert e in rows(c.consent_id, "REVOKE_CONSENT") and (e["result"], e["actor_did"], e["actor_role"]) == ("SUCCESS", "did:parent:B", "Guardian")
    meta = e["metadata"]
    assert meta["revocation"] == "REVOKED" and meta["revoked_at"] == NOW.isoformat() and meta["time_source"] == "block-timestamp"
    assert meta["recipients"] == [DOCTOR] and [n["status"] for n in meta["notifications"]] == ["SENT"]
    assert meta["shredded"]["keys_destroyed"] == 2 and meta["complete"] is True
    for record in (e, chain_row):                                      # the records hold no token identifier and no token address
        assert "0x" + "5a" * 20 not in json.dumps(record) and "SBT-41" not in json.dumps(record)


def test_patient_revokes_alone_before_and_after_majority(vault):
    for when, after in ((NOW, False), (MAJORITY + timedelta(days=1), True)):
        c = sealed_consent(vault)
        out = revoke(c, PATIENT, signed(PATIENT, c), now=when, onchain_revoke=NO_CHAIN, vault=vault)
        assert out["result"] == "REVOKED" and (out["revoker_role"], out["basis"], out["after_majority"]) == ("Patient", "patient", after)
        assert out["onchain"]["status"] == "NOT_APPLICABLE" and out["complete"] is True and c.revoked is True
        assert rows(c.consent_id, "ONCHAIN_REVOKE") == [] and not vault.has_copy(c.consent_id)


def test_guardian_cannot_revoke_after_majority(vault):
    c = sealed_consent(vault)
    sig = signed("did:parent:A", c)
    called = []
    out = revoke(c, "did:parent:A", sig, now=MAJORITY + timedelta(seconds=1), onchain_revoke=chain(called), vault=vault)
    assert out["result"] == "DENIED" and out["reason"] == "GUARDIAN-AFTER-MAJORITY" and out["after_majority"] is True
    assert c.revoked is False and consent_db.get(c.consent_id).revoked is False and called == []
    assert vault.open(c.consent_id, ["Observation"]) == {"Observation": RECORD["Observation"]}    # nothing was shredded
    e = rows(c.consent_id, "REVOKE_CONSENT")[-1]
    assert (e["result"], e["actor_did"], e["metadata"]["reason"]) == ("DENIED", "did:parent:A", "GUARDIAN-AFTER-MAJORITY")
    # the day before, the same guardian may revoke alone
    out = revoke(c, "did:parent:A", sig, now=MAJORITY - timedelta(seconds=1), onchain_revoke=chain(called), vault=vault)
    assert out["result"] == "REVOKED" and called == ["SBT-41"]
    # how majority is read from the consent
    assert majority_reached(make_consent(), MAJORITY - timedelta(seconds=1)) is False
    assert majority_reached(make_consent(), MAJORITY) is True
    leap = make_consent(patient_birth_date="2008-02-29")
    assert majority_reached(leap, datetime(2026, 2, 28, 23, 59)) is False and majority_reached(leap, datetime(2026, 3, 1)) is True
    assert majority_reached(make_consent(patient_birth_date="2004-01-01", majority_age=21), datetime(2024, 12, 31)) is False
    due = make_consent(patient_birth_date=None, transitions=[{"id": "t-1", "kind": "majority", "due": "2026-11-20T00:00:00", "done": False}])
    assert majority_reached(due, MAJORITY - timedelta(hours=1)) is False and majority_reached(due, MAJORITY) is True
    due.transitions[0]["done"] = True
    assert majority_reached(due, MAJORITY - timedelta(days=30)) is True
    # a consent that records no majority leaves the guardians their authority
    unknown = sealed_consent(vault, patient_birth_date=None)
    assert majority_reached(unknown, NOW) is None
    assert revoke(unknown, "did:parent:A", signed("did:parent:A", unknown), now=NOW, onchain_revoke=NO_CHAIN, vault=vault)["result"] == "REVOKED"


def test_former_guardian_cannot_revoke_the_reissued_consent(vault):
    # after the capacity transition the consent is re-issued with the patient as its sole guardian
    when = MAJORITY + timedelta(days=1)
    old = sealed_consent(vault)
    new = sealed_consent(vault, guardians=[PATIENT], predecessor_id=old.consent_id)
    old.successor_id, old.revoked, old.state = new.consent_id, True, "REVOKED"
    consent_db.update(old)
    assert new.guardian_dids == [PATIENT] and new.threshold == 1
    out = revoke(new, "did:parent:A", signed("did:parent:A", new), now=when, onchain_revoke=NO_CHAIN, vault=vault)
    assert out["result"] == "DENIED" and out["reason"] == "FORMER-GUARDIAN" and new.revoked is False
    out = revoke(new, "did:parent:C", signed("did:parent:C", new), now=when, onchain_revoke=NO_CHAIN, vault=vault)
    assert out["result"] == "DENIED" and out["reason"] == "NOT-A-PARTY"
    # a request against the consent that was replaced is refused too, whoever makes it
    assert revoke(old, "did:parent:A", signed("did:parent:A", old), now=when, vault=vault)["reason"] == "GUARDIAN-AFTER-MAJORITY"
    out = revoke(old, PATIENT, signed(PATIENT, old), now=when, vault=vault)
    assert out["reason"] == "CONSENT-SUPERSEDED" and out["successor_id"] == new.consent_id     # the consent to revoke is named
    assert vault.has_copy(new.consent_id) and ask(new, vault, now=when)["outcome"] == GRANTED
    out = revoke(new, PATIENT, signed(PATIENT, new), now=when, onchain_revoke=NO_CHAIN, vault=vault)
    assert out["result"] == "REVOKED" and out["revoker_role"] == "Patient" and out["after_majority"] is True


def test_revocation_request_must_be_signed_by_a_party_of_the_consent(vault):
    c = sealed_consent(vault)
    other = make_consent()
    wallet = Account.from_key(Web3.keccak(text="the wallet of guardian A in this test"))
    refused = [
        ("did:parent:A", None, "SIGNATURE-INVALID"),                                        # no signature
        ("did:parent:A", signed("did:parent:B", c), "SIGNATURE-INVALID"),                   # the signature of another guardian
        ("did:parent:A", sign_consent("did:parent:A", c.consent_id)[0], "SIGNATURE-INVALID"),   # an approval, replayed
        ("did:parent:A", signed("did:parent:A", other), "SIGNATURE-INVALID"),               # a revocation of another consent
        ("did:parent:A", signed("did:parent:A", c, signer=wallet), "SIGNATURE-INVALID"),    # a key that is not registered
        ("did:parent:C", signed("did:parent:C", c), "NOT-A-PARTY"),                         # a guardian of nobody here
        (DOCTOR, signed(DOCTOR, c), "NOT-A-PARTY"),                                         # the requester
        (None, None, "NOT-A-PARTY")]
    for revoker, signature, reason in refused:
        out = revoke(c, revoker, signature, now=NOW, onchain_revoke=chain(), vault=vault)
        assert out["result"] == "DENIED" and out["reason"] == reason and out["revoked"] is False
        e = rows(c.consent_id, "REVOKE_CONSENT")[-1]
        assert e["result"] == "DENIED" and e["metadata"]["reason"] == reason and e["actor_did"] == str(revoker)
    assert c.revoked is False and c.token_id == "SBT-41" and c.commitment_opening is not None
    assert vault.has_copy(c.consent_id) and rows(c.consent_id, "ONCHAIN_REVOKE") == [] and ask(c, vault)["outcome"] == GRANTED
    # with a wallet address registered for the guardian, the derived key is refused and the wallet revokes
    c.guardian_addresses = {"did:parent:A": wallet.address}
    assert revoke(c, "did:parent:A", signed("did:parent:A", c), now=NOW, vault=vault)["reason"] == "SIGNATURE-INVALID"
    assert revoke(c, "did:parent:B", signed("did:parent:B", c), now=NOW, vault=vault, allow_demo_key=False)["reason"] == "SIGNATURE-INVALID"
    out = revoke(c, "did:parent:A", signed("did:parent:A", c, signer=wallet), now=NOW, onchain_revoke=chain(), vault=vault,
                 allow_demo_key=False)
    assert out["result"] == "REVOKED"
    # another authentication can be given, and it must answer True
    d = sealed_consent(vault)
    seen = []
    assert revoke(d, PATIENT, "one-time-code", now=NOW, vault=vault, authenticate=lambda *a: "yes")["reason"] == "SIGNATURE-INVALID"
    out = revoke(d, PATIENT, "one-time-code", now=NOW, onchain_revoke=NO_CHAIN, vault=vault,
                 authenticate=lambda did, consent, signature: seen.append((did, consent.consent_id, signature)) or True)
    assert out["result"] == "REVOKED" and seen == [(PATIENT, d.consent_id, "one-time-code")]


# ---------------------------------------------------------------------------
# Algorithm 6.4: deletion, unintelligibility and notification (Section 6.5.3)
# ---------------------------------------------------------------------------
def test_backup_of_the_ciphertext_cannot_be_decrypted_after_the_keys_are_destroyed(tmp_path):
    keys_path, vault_path = tmp_path / "keystore" / "keys.db", tmp_path / "vault" / "vault.db"
    keys = KeyStore(str(keys_path))
    vault = DataVault(keys, str(vault_path))
    c, bystander = sealed_consent(vault), sealed_consent(vault)
    delivered = ask(c, vault, scope=c.scope)
    assert delivered["outcome"] == GRANTED
    backup = vault.export_copy(c.consent_id)                           # a copy of the ciphertext that stays outside the vault
    assert sorted(backup) == ["Medication", "Observation"]
    copied_keys = {m: k for (_, m), k in stored_keys(keys, c.consent_id).items()}      # kept only to show the third limit below
    ciphertexts = [bytes.fromhex(b["ciphertext"]) for b in backup.values()]
    assert all(b["ciphertext"].encode() in vault_path.read_bytes() for b in backup.values())

    out = revoke(c, "did:parent:A", signed("did:parent:A", c), now=NOW, onchain_revoke=chain(), vault=vault)
    assert out["result"] == "REVOKED" and out["shredded"]["shredded"] is True

    # deletion test: the consent-bound copy is gone from the store
    assert not vault.has_copy(c.consent_id) and vault.export_copy(c.consent_id) == {}
    assert not any(b["ciphertext"].encode() in vault_path.read_bytes() for b in backup.values())
    # no key survives: the operator of the key store finds none, in the store or in its file
    assert stored_keys(keys, c.consent_id) == {} and set(out["shredded"]["key_ids"]) == {b["key_id"] for b in backup.values()}
    assert not any(k in keys_path.read_bytes() for k in copied_keys.values())
    evidence = revocation_evidence(c, vault=vault, retained_copy=backup)
    assert evidence["deletion"] is True and evidence["unintelligibility"] is True and evidence["notification"] is True
    assert evidence["retained_blobs_tested"] == 2 and evidence["retained_blobs_opened"] == []

    # unintelligibility test: the copy that remains does not open, for any party
    for module, blob in backup.items():
        with pytest.raises(KeyDestroyedError):                         # the Controller, through its key store
            keys.decrypt(c.consent_id, module, bytes.fromhex(blob["nonce"]), bytes.fromhex(blob["ciphertext"]))
    assert vault.import_copy(backup) and vault.has_copy(c.consent_id)   # the backup is restored into the vault
    with pytest.raises(KeyDestroyedError):
        vault.open(c.consent_id, ["Observation", "Medication"])
    r = ask(c, vault, scope=c.scope, source=source)
    assert r["outcome"] == DENIED and r["deny_code"] == "REVOKED" and r["data"] == {}
    with pytest.raises(KeyDestroyedError):                             # no key can be made for the consent again
        keys.create_key(c.consent_id, "Observation")
    remaining = list(stored_keys(keys).values())                       # the operator tries every key that still exists
    assert len(remaining) == 2
    for module, blob in backup.items():
        aad = key_store._associated_data(c.consent_id, module, blob["key_id"])
        for candidate in remaining + [os.urandom(32), bytes(32)]:
            with pytest.raises(DecryptionError):
                key_store._unseal(candidate, bytes.fromhex(blob["nonce"]), bytes.fromhex(blob["ciphertext"]), aad)
    # a prior recipient holds what was delivered and no key
    assert not holds_a_key(delivered, list(copied_keys.values()))
    assert not any(RECORD["Medication"][0]["description"].encode() in ct for ct in ciphertexts)
    # the consent of another patient is untouched
    assert ask(bystander, vault, scope=bystander.scope)["outcome"] == GRANTED

    # limit 3 of the claim, seen from the other side: a key that was copied before the destruction still opens the backup
    for module, blob in backup.items():
        aad = key_store._associated_data(c.consent_id, module, blob["key_id"])
        plain = key_store._unseal(copied_keys[module], bytes.fromhex(blob["nonce"]), bytes.fromhex(blob["ciphertext"]), aad)
        assert json.loads(plain)["value"] == RECORD[module]


def test_every_recipient_recorded_in_the_ledger_is_notified_once(vault):
    c = sealed_consent(vault)
    assert ask(c, vault, scope=["Observation"])["outcome"] == GRANTED
    assert ask(c, vault, scope=["Medication"])["outcome"] == GRANTED
    assert ask(c, vault, requester=REGISTRAR)["outcome"] == DENIED      # a refused request makes no recipient
    # E is the source: a release that another part of the Controller recorded counts as well
    audit_db.log(actor_did="did:hospital:003", actor_role="Doctor", action="DATA_ACCESS", patient_did=PATIENT,
                 consent_id=c.consent_id, scope=["Observation"], purpose="Treatment", result="GRANTED")
    found = {r["recipient_did"]: r for r in notification_service.recipients_of(c.consent_id)}
    assert sorted(found) == [DOCTOR, "did:hospital:003"]
    assert found[DOCTOR]["releases"] == 2 and found[DOCTOR]["modules"] == ["Observation", "Medication"]
    assert notification_service.notification_check(c.consent_id) == {
        "consent_id": c.consent_id, "recipients": [DOCTOR, "did:hospital:003"], "notified": [],
        "missing": [DOCTOR, "did:hospital:003"], "complete": False}

    delivered = []
    out = revoke(c, PATIENT, signed(PATIENT, c), now=NOW, onchain_revoke=NO_CHAIN, vault=vault, send=delivered.append)
    assert out["recipients"] == [DOCTOR, "did:hospital:003"] and [n["status"] for n in out["notifications"]] == ["SENT", "SENT"]
    assert [n["recipient_did"] for n in delivered] == [DOCTOR, "did:hospital:003"]
    notice = delivered[0]
    assert (notice["type"], notice["consent_id"], notice["patient_did"]) == ("CONSENT_WITHDRAWN", c.consent_id, PATIENT)
    assert notice["withdrawn_at"] == NOW.isoformat() and notice["releases"] == 2 and notice["modules"] == ["Observation", "Medication"]
    assert "167.7" not in json.dumps(delivered) and "Amoxicillin" not in json.dumps(delivered)     # a notice carries no record data
    # every notice is a record of E, and the test of Section 6.5.3 passes: every recipient in E was notified
    notices = rows(c.consent_id, "WITHDRAWAL_NOTIFICATION")
    assert [(e["result"], e["metadata"]["recipient_did"]) for e in notices] == [("SENT", DOCTOR), ("SENT", "did:hospital:003")]
    assert notices[0]["metadata"]["access_event_ids"] == found[DOCTOR]["access_event_ids"]
    check = notification_service.notification_check(c.consent_id)
    assert check["complete"] is True and check["missing"] == [] and check["notified"] == [DOCTOR, "did:hospital:003"]
    assert REGISTRAR not in check["recipients"] and notification_service.inbox(REGISTRAR) == []
    assert notification_service.inbox(DOCTOR)[-1]["notification_id"] == notice["notification_id"]
    assert [n["notification_id"] for n in out["audit_event"]["metadata"]["notifications"]] == [n["notification_id"] for n in delivered]
    # repeating the steps sends no second notice
    again = complete_revocation(c, onchain_revoke=NO_CHAIN, vault=vault, send=delivered.append)
    assert again["result"] == "COMPLETED" and [n["new"] for n in again["notifications"]] == [False, False]
    assert len(delivered) == 2 and len(rows(c.consent_id, "WITHDRAWAL_NOTIFICATION")) == 2
    # the default transport places the notice in the outbox of the Controller
    d = sealed_consent(vault)
    ask(d, vault)
    before = len(notification_service.OUTBOX)
    revoke(d, PATIENT, signed(PATIENT, d), now=NOW, onchain_revoke=NO_CHAIN, vault=vault)
    assert [n["consent_id"] for n in notification_service.OUTBOX[before:]] == [d.consent_id]


def test_failed_delivery_of_a_notice_is_recorded_and_completed_later(vault):
    c = sealed_consent(vault)
    ask(c, vault)

    def offline(notice):
        raise ConnectionError("the recipient system is not reachable")
    out = revoke(c, PATIENT, signed(PATIENT, c), now=NOW, onchain_revoke=NO_CHAIN, vault=vault, send=offline)
    assert out["result"] == "REVOKED" and out["complete"] is False and out["pending"] == [f"notification:{DOCTOR}"]
    assert out["notifications"][0]["status"] == "FAILED" and "not reachable" in out["notifications"][0]["error"]
    assert rows(c.consent_id, "WITHDRAWAL_NOTIFICATION")[-1]["result"] == "FAILED"
    assert notification_service.notification_check(c.consent_id)["missing"] == [DOCTOR]
    assert out["shredded"]["shredded"] is True and c.revoked is True     # the withdrawal itself took effect
    delivered = []
    done = complete_revocation(c, onchain_revoke=NO_CHAIN, vault=vault, send=delivered.append, now=NOW + timedelta(hours=1))
    assert done["result"] == "COMPLETED" and done["pending"] == [] and len(delivered) == 1
    assert notification_service.notification_check(c.consent_id)["complete"] is True
    assert rows(c.consent_id, "REVOCATION_COMPLETION")[-1]["result"] == "SUCCESS"
    with pytest.raises(ValueError):                                     # completion revokes nothing by itself
        complete_revocation(make_consent(), vault=vault)


def test_revoking_a_reissued_consent_covers_the_consent_it_replaced(vault):
    old = sealed_consent(vault)
    assert ask(old, vault, scope=old.scope)["outcome"] == GRANTED       # the data was received under the first consent
    new = sealed_consent(vault, guardians=[PATIENT], predecessor_id=old.consent_id)
    old.successor_id, old.revoked, old.state = new.consent_id, True, "REVOKED"
    consent_db.update(old)
    assert [p.consent_id for p in revocation_service.predecessors(new)] == [old.consent_id]
    assert vault.has_copy(old.consent_id)                               # the copy of the retired consent was left behind
    delivered = []
    out = revoke(new, PATIENT, signed(PATIENT, new), now=MAJORITY + timedelta(days=2), onchain_revoke=NO_CHAIN, vault=vault,
                 send=delivered.append)
    assert out["result"] == "REVOKED" and out["recipients"] == [DOCTOR] and out["complete"] is True
    assert delivered[0]["received_under"] == [old.consent_id] and delivered[0]["consent_id"] == new.consent_id
    assert out["shredded"]["consent_ids"] == [new.consent_id, old.consent_id] and out["shredded"]["keys_destroyed"] == 4
    for consent_id in (new.consent_id, old.consent_id):
        assert not vault.has_copy(consent_id) and vault.key_store.is_destroyed(consent_id)
    # the openings and the links to the tokens of both consents are deleted, in the records and in the store
    five = {"commitment_opening", "zk_secret", "token_address", "token_id", "commitment"}
    assert out["link"]["status"] == "DELETED" and set(out["link"]["deleted"]) == five
    assert set(out["link"]["deleted_in_replaced"][old.consent_id]) == five
    for consent in (new, old):
        assert all(getattr(consent_db.get(consent.consent_id), field) is None for field in revocation_service.LINK_FIELDS)
    assert old.successor_id == new.consent_id and new.predecessor_id == old.consent_id      # the two stay linked to each other
    evidence = revocation_evidence(new, vault=vault)
    assert evidence["consent_ids"] == [new.consent_id, old.consent_id]
    assert evidence["deletion"] and evidence["unintelligibility"] and evidence["notification"] and evidence["link_deleted"]
    # the capacity transition itself retires a copy with crypto_shred, which notifies nobody
    third = sealed_consent(vault)
    before = len(audit_db.get())
    evidence = revocation_service.crypto_shred(third.consent_id, vault, now=NOW)
    assert evidence["shredded"] is True and evidence["modules_deleted"] == ["Medication", "Observation"] and evidence["keys_destroyed"] == 2
    assert len(audit_db.get()) == before and not vault.has_copy(third.consent_id)


def test_link_to_a_token_is_kept_until_that_token_is_revoked_on_chain(vault):
    when = MAJORITY + timedelta(days=2)
    old = sealed_consent(vault)                                         # its token is SBT-41
    new = sealed_consent(vault, guardians=[PATIENT], predecessor_id=old.consent_id, token_id="SBT-42",
                         token_address="0x" + "6b" * 20)
    old.successor_id, old.revoked, old.state = new.consent_id, True, "REVOKED"
    consent_db.update(old)
    seen, calls = [], []

    def delete_link(consent):                                           # a link held outside the record, found by the token
        seen.append((consent.consent_id, consent.token_id, consent.token_address))
    out = revoke(new, PATIENT, signed(PATIENT, new), now=when, onchain_revoke=chain(calls), vault=vault, delete_link=delete_link)
    # The token of the new consent is revoked here. The revoke of the old token belongs to the capacity transition,
    # and E does not show it yet, so the link to the old token is kept and the step stays pending.
    assert out["result"] == "REVOKED" and calls == ["SBT-42"] and out["complete"] is False and out["pending"] == ["link_deletion"]
    assert out["link"]["status"] == "DEFERRED" and out["link"]["kept_for_onchain_revoke"] == [old.consent_id]
    assert seen == [(new.consent_id, "SBT-42", "0x" + "6b" * 20)]       # the callable saw the token before the record lost it
    assert new.token_id is None and new.token_address is None and old.token_id == "SBT-41"
    assert out["link"]["deleted_in_replaced"] == {old.consent_id: ["commitment_opening", "zk_secret"]}
    assert old.commitment_opening is None and consent_db.get(old.consent_id).zk_secret is None      # the openings go at once
    assert revocation_evidence(new, vault=vault)["link_deleted"] is False
    # the capacity transition records the revoke of the old token in E, and the completion deletes the last link
    audit_db.log(actor_did="Blockchain", actor_role="SmartContract", action="ONCHAIN_REVOKE", patient_did=PATIENT,
                 consent_id=old.consent_id, result="SUCCESS", tx_hash="0x" + "cd" * 32, block_number=120)
    done = complete_revocation(new, onchain_revoke=chain(calls), vault=vault, delete_link=delete_link)
    assert done["result"] == "COMPLETED" and calls == ["SBT-42"]        # no revoke is submitted twice
    assert seen[1:] == [(old.consent_id, "SBT-41", "0x" + "5a" * 20)]
    assert old.token_id is None and consent_db.get(old.consent_id).token_address is None
    assert revocation_evidence(new, vault=vault)["link_deleted"] is True
    again = complete_revocation(new, onchain_revoke=chain(calls), vault=vault, delete_link=delete_link)
    assert again["result"] == "COMPLETED" and len(seen) == 2            # a link that is deleted is not deleted twice

    # a callable that fails leaves the link to the token in place and the step pending
    third = sealed_consent(vault)

    def unreachable(consent):
        raise OSError("the wallet service is not reachable")
    out = revoke(third, PATIENT, signed(PATIENT, third), now=NOW, onchain_revoke=chain(), vault=vault, delete_link=unreachable)
    assert out["result"] == "REVOKED" and out["link"]["status"] == "FAILED" and out["pending"] == ["link_deletion"]
    assert "not reachable" in out["link"]["errors"][0] and out["link"]["deleted"] == ["commitment_opening", "zk_secret"]
    assert third.token_id == "SBT-41" and consent_db.get(third.consent_id).commitment_opening is None
    done = complete_revocation(third, onchain_revoke=chain(), vault=vault, delete_link=delete_link)
    assert done["result"] == "COMPLETED" and third.token_id is None and seen[-1] == (third.consent_id, "SBT-41", "0x" + "5a" * 20)


def test_audit_record_is_preserved_by_revocation(vault):
    c = sealed_consent(vault)
    audit_db.log(PATIENT, "Patient", "CREATE_CONSENT", PATIENT, c.consent_id, scope=c.scope, purpose=c.purpose)
    ask(c, vault, scope=c.scope)
    ask(c, vault, scope=["Procedure"])
    before = copy.deepcopy(rows(c.consent_id))
    persisted_before = {r["event_id"]: r for r in db.all_rows("audit") if r["consent_id"] == c.consent_id}
    assert len(before) == 5 and len(persisted_before) == 5
    revoke(c, "did:parent:A", signed("did:parent:A", c), now=NOW, onchain_revoke=chain(), vault=vault)
    after = rows(c.consent_id)
    assert after[:5] == before                                          # no record of E was changed or removed
    assert all(audit_db.event_digest(e) == e["event_digest"] for e in after)
    persisted_after = {r["event_id"]: r for r in db.all_rows("audit") if r["consent_id"] == c.consent_id}
    assert all(persisted_after[i] == r for i, r in persisted_before.items())
    assert [e["action"] for e in after[5:]] == ["ONCHAIN_REVOKE", "WITHDRAWAL_NOTIFICATION", "REVOKE_CONSENT"]
    granted = [e for e in after if e["action"] == "DATA_ACCESS" and e["result"] == "GRANTED"][0]
    assert granted["actor_did"] == DOCTOR and granted["scope"] == c.scope and granted["patient_did"] == PATIENT


def test_failed_onchain_revoke_does_not_block_the_withdrawal(vault):
    c = sealed_consent(vault)
    ask(c, vault)

    def node_down(consent):
        raise RuntimeError("the node is not reachable")
    out = revoke(c, PATIENT, signed(PATIENT, c), now=NOW, onchain_revoke=node_down, vault=vault)
    assert out["result"] == "REVOKED" and out["revoked"] is True and out["complete"] is False
    assert out["onchain"]["status"] == "FAILED" and "not reachable" in out["onchain"]["error"]
    assert out["pending"] == ["onchain_revoke", "link_deletion"] and out["link"]["status"] == "DEFERRED"
    # the withdrawal took effect: the copy and the keys are gone, the opening is deleted, the recipient is notified
    assert out["shredded"]["shredded"] is True and not vault.has_copy(c.consent_id)
    assert c.commitment_opening is None and c.zk_secret is None and out["link"]["deleted"] == ["commitment_opening", "zk_secret"]
    assert [n["status"] for n in out["notifications"]] == ["SENT"]
    assert ask(c, vault)["deny_code"] == "REVOKED"
    # only the token is kept, because the on-chain revoke needs it
    assert c.token_id == "SBT-41" and c.token_address == "0x" + "5a" * 20
    failed = rows(c.consent_id, "ONCHAIN_REVOKE")[-1]
    assert failed["result"] == "FAILED" and failed["tx_hash"] is None and failed["onchain"] is False
    # a receipt that reports a failed transaction, and a call without the callable, leave the step pending too
    assert complete_revocation(c, onchain_revoke=chain(status=0), vault=vault)["onchain"]["status"] == "FAILED"
    waiting = complete_revocation(c, vault=vault)
    assert waiting["onchain"]["status"] == "NOT_SUBMITTED" and waiting["result"] == "PENDING" and c.token_id == "SBT-41"
    # the Controller completes the revocation when the chain answers
    calls = []
    done = complete_revocation(c, onchain_revoke=chain(calls), vault=vault, now=NOW + timedelta(hours=1))
    assert done["result"] == "COMPLETED" and done["onchain"]["status"] == "SUCCESS" and calls == ["SBT-41"]
    assert done["link"]["status"] == "DELETED" and c.token_id is None and c.token_address is None and c.commitment is None
    assert [n["new"] for n in done["notifications"]] == [False]         # no second notice
    assert c.revoked_at == NOW.isoformat() and c.revoked_by == PATIENT   # the revocation keeps its own time and party
    # once the chain has confirmed, nothing is submitted again
    again = revoke(c, PATIENT, signed(PATIENT, c), now=NOW + timedelta(hours=2), onchain_revoke=chain(calls), vault=vault)
    assert again["result"] == "ALREADY_REVOKED" and again["onchain"]["status"] == "ALREADY_CONFIRMED" and calls == ["SBT-41"]
    assert again["complete"] is True and c.revoked_at == NOW.isoformat()


def test_revoked_consent_releases_nothing_even_if_its_record_is_changed_back(vault):
    c = sealed_consent(vault)
    revoke(c, PATIENT, signed(PATIENT, c), now=NOW, onchain_revoke=NO_CHAIN, vault=vault)
    # the record is set back to a live consent, by an error or by an operator
    c.revoked, c.state, c.token_id, c.revoked_at, c.revoked_by = False, "ACTIVE", "SBT-41", None, None
    r = ask(c, vault, scope=c.scope, source=source)
    assert r["outcome"] == DENIED and r["deny_code"] == "REVOKED" and r["data"] == {}
    assert not vault.has_copy(c.consent_id) and not vault.key_store.has_key(c.consent_id)      # no new copy and no new key
    with pytest.raises(KeyDestroyedError):
        vault.seal_from_source(c, source)
    assert rows(c.consent_id, "DATA_ACCESS")[-1]["result"] == "DENIED"


def test_onchain_revoke_through_the_injected_callable_on_an_in_memory_chain(vault):
    # The ConsentSBTv3 bytecode of the repository on an in-memory EVM. No Sepolia transaction is sent.
    pytest.importorskip("eth_tester")
    from web3 import EthereumTesterProvider
    artefact = json.load(open(os.path.join(ROOT, "blockchain", "abi", "ConsentSBTv3.json")))
    w3 = Web3(EthereumTesterProvider())
    owner, holder, doctor = w3.eth.accounts[:3]
    deployed = w3.eth.get_transaction_receipt(w3.eth.contract(abi=artefact["abi"], bytecode=artefact["bytecode"]).constructor().transact({"from": owner}))
    token = w3.eth.contract(address=deployed.contractAddress, abi=artefact["abi"])
    start = w3.eth.get_block("latest").timestamp
    mint = token.functions.mintConsentV3(holder, doctor, "Treatment", start, start + 86400, b"AU", 2)
    token_id = mint.call({"from": owner})
    mint.transact({"from": owner})
    c = sealed_consent(vault, token_id=f"SBT-{token_id}")
    assert token.functions.checkValid(token_id).call() is True

    def onchain_revoke(consent):
        tx = token.functions.revoke(int(consent.token_id[4:])).transact({"from": owner})
        receipt = w3.eth.get_transaction_receipt(tx)
        events = token.events.ConsentRevoked().process_receipt(receipt)
        return {"tx_hash": w3.to_hex(tx), "status": receipt.status, "block_number": receipt.blockNumber,
                "gas_used": receipt.gasUsed, "revoked_token": events[0]["args"]["tokenId"]}
    out = revoke(c, "did:parent:A", signed("did:parent:A", c), now=NOW, onchain_revoke=onchain_revoke, vault=vault)
    assert out["result"] == "REVOKED" and out["complete"] is True and out["onchain"]["status"] == "SUCCESS"
    assert token.functions.checkValid(token_id).call() is False        # the chain reports the consent as revoked
    row = rows(c.consent_id, "ONCHAIN_REVOKE")[-1]
    assert row["tx_hash"] == out["onchain"]["tx_hash"] and row["block_number"] == out["onchain"]["block_number"]
    assert row["onchain"] is True and row["metadata"]["gas_used"] == out["onchain"]["gas_used"] > 21000
    assert c.token_id is None and not vault.has_copy(c.consent_id)


# ---------------------------------------------------------------------------
# The case study and the limits of the claim
# ---------------------------------------------------------------------------
def test_case_study_request_refusal_and_withdrawal(vault):
    record_before = copy.deepcopy(RECORD)
    c = sealed_consent(vault)
    # Event 1: the named clinician requests Observation and Medication for treatment
    event_1 = ask(c, vault, scope=["Observation", "Medication"])
    assert event_1["outcome"] == GRANTED and all(event_1["decision"][k] for k in ("VI", "VA", "VP", "VT", "VL"))
    assert event_1["data"] == {"Observation": RECORD["Observation"], "Medication": RECORD["Medication"]}
    # Event 2: the research registrar requests Procedure records for a study
    event_2 = ask(c, vault, requester=REGISTRAR, scope=["Procedure"], purpose="Research")
    assert event_2["outcome"] == DENIED and event_2["deny_code"] == "PURPOSE-MISMATCH" and event_2["data"] == {}
    assert rows(c.consent_id, "DATA_ACCESS")[-1]["result"] == "DENIED"
    # Event 4: the patient revokes, alone
    delivered = []
    out = revoke(c, PATIENT, signed(PATIENT, c), now=NOW + timedelta(hours=2), onchain_revoke=chain(), vault=vault,
                 send=delivered.append)
    assert out["result"] == "REVOKED" and out["complete"] is True
    assert [n["recipient_did"] for n in delivered] == [DOCTOR]          # the clinician who received data, not the registrar
    after = ask(c, vault, scope=["Observation", "Medication"], now=NOW + timedelta(hours=3))
    assert after["outcome"] == DENIED and after["deny_code"] == "REVOKED" and after["data"] == {}
    # limit 1: what the clinician read at Event 1 is not recalled
    assert event_1["data"]["Medication"] == record_before["Medication"]
    # limit 2: the source record of the treating institution is untouched
    assert RECORD == record_before and source(PATIENT, ["Observation"]) == {"Observation": record_before["Observation"]}


def test_limits_of_the_claim_are_stated_with_the_revocation_code():
    # the three limits in the words of Section 6.2.4 of the chapter instructions, each sentence whole
    text = " ".join(revocation_service.__doc__.split())
    limits = ("Revocation ends all future access, but it cannot recall data already delivered to an authorised recipient, "
              "which is why Article 19 of the GDPR asks the controller to notify recipients rather than to retrieve the data.",
              "It does not erase the source record held by the treating institution, which keeps it under its own legal "
              "basis (Article 17(3)).",
              "And a remaining copy stays unintelligible only while the encryption algorithm holds and the key was never "
              "compromised, as the final EDPB Guidelines 02/2025 (version 2, 7 July 2026) state at paragraph 51, where they "
              "also confirm that encrypted personal data is still personal data.")
    for number, sentence in enumerate(limits, 1):
        assert f"{number}. {sentence}" in text
    assert text.index(limits[0]) < text.index(limits[1]) < text.index(limits[2])
    assert "The audit record of the revocation is preserved." in text
    assert "consultation" not in text and "8 April 2025" not in text      # the final version of the guidelines is the one cited


def test_consent_bound_copy_of_a_synthea_patient_is_released_and_shredded(vault):
    from database.repository import SyntheaRepository
    repo = SyntheaRepository(os.path.join(ROOT, "data", "synthea"))
    patient = "did:patient:fe621c76-a591-b7be-5668-b77f00240d82"
    c = make_consent(patient_did=patient)
    sealed = vault.seal_from_source(c, repo.query_patient)
    assert sealed["modules"] == ["Observation", "Medication"]
    r = ask(c, vault, scope=["Observation", "Medication"])
    assert r["outcome"] == GRANTED
    truth = repo.query_patient(patient, ["Observation", "Medication"])
    for module in ("Observation", "Medication"):
        got = r["data"][module]
        assert len(got) == len(truth[module]) > 0 and list(got.columns) == list(truth[module].columns)
        assert json.loads(got.to_json(orient="split"))["data"] == json.loads(truth[module].to_json(orient="split"))["data"]
    backup = vault.export_copy(c.consent_id)
    out = revoke(c, patient, signed(patient, c), now=NOW, onchain_revoke=NO_CHAIN, vault=vault)
    evidence = revocation_evidence(c, vault=vault, retained_copy=backup)
    assert out["complete"] is True and evidence["deletion"] and evidence["unintelligibility"] and evidence["notification"]
    assert len(repo.query_patient(patient, ["Observation"])["Observation"]) == len(truth["Observation"])    # the source record stays
