"""Identity, authority and the approval signature of the thesis design (Chapter 5, Sections 5.2.2, 5.3.2, 5.3.3, 5.4.2).
DID resolution for did:key and for the demonstration identifiers, Algorithm 5.1 in full with one reason code for each
line that can refuse, the credential status list signed by the issuer, and the EIP-712 approval of Algorithm 5.2 over
the consent commitment with wallet-held addresses. Everything runs offline. The wallets are fixed test keys, and every
test reads and writes its own status list file."""
import base64, copy, gzip, json, pytest, tracemalloc
from datetime import datetime, timedelta
from functools import partial
from eth_account import Account
from eth_keys import keys
from eth_utils import keccak
from models.consent import Consent
from services import credential_status as status
from services import did_resolver
from services import identity_service as ids
from services.identity_service import IdentityReason as R, verify_identity

GUARDIANS = ["did:parent:A", "did:parent:B", "did:parent:C", "did:parent:D"]
DOCTORS = ["did:hospital:001", "did:hospital:002", "did:hospital:003"]
ED25519_DID = "did:key:z6MkiTBz1ymuepAQ4HEHYSF1H8quG5GLVVQR3djdX3mDooWp"        # Ed25519 example of the did:key specification
# secp256k1 test vectors of the did:key specification: private key -> identifier
SECP256K1_VECTORS = {
    "9085d2bef69286a6cbb51623c8fa258629945cd55ca705cc4e66700396894e0c": "did:key:zQ3shokFTS3brHcDQrn82RUDfCZESWL1ZdCEJwekUDPQiYBme",
    "f0f4df55a2b3ff13051ea814a8f24ad00f2e469af73c363ac7e9fb999a9072ed": "did:key:zQ3shtxV1FrJfhqE1dvxYRcCknWNjHc3c5X1y3ZSoPDi2aur2",
    "6b0b91287ae3348f8c2f2552d766f30e3604867e34adc37ccbb74a8e6b893e02": "did:key:zQ3shZc2QzApp2oymGvQbzP8eKheVshBHbU4ZYjeXqwSKEn6N"}
CID = "consent-123"
C = 0x1A2B3C4D5E6F708192A3B4C5D6E7F8091A2B3C4D5E6F708192A3B4C5D6E7F809         # a consent commitment (a field element)
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141         # order of secp256k1
EMPTY = bytes(status.LIST_SIZE // 8)


@pytest.fixture(autouse=True)
def status_store(tmp_path, monkeypatch):
    path = tmp_path / "credential_status.json"
    monkeypatch.setenv("HALAH_STATUS_LIST_PATH", str(path))
    return path


def wallet(name):
    """A key held by a wallet, outside the server: nothing derives it from an identifier."""
    return Account.from_key(keccak(text=f"test wallet of {name}"))


def wallet_did(acct):
    return did_resolver.did_key(keys.PrivateKey(acct.key).public_key.to_compressed_bytes())


def b58(data):
    alphabet, n, out = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz", int.from_bytes(data, "big"), ""
    while n:
        n, r = divmod(n, 58); out = alphabet[r] + out
    return out


def _active():
    c = Consent("id-v2", "did:patient:x", "did:hospital:001", ["did:parent:A", "did:parent:B"], "Treatment", ["Observation"], 2,
                start_date=(datetime.now() - timedelta(days=1)).isoformat(), expiry_date=(datetime.now() + timedelta(days=30)).isoformat(),
                token_id="SBT-1")
    for g in c.guardian_dids:
        sig, addr = ids.sign_consent(g, c.consent_id); c.signatures.append(g); c.signature_data[g] = {"signer": addr, "signature": sig}
    return c


def _active_v2(wallets=True):
    """An active consent whose guardians approved its commitment: with wallet-held keys whose addresses the consent
    registers, or (wallets=False) with the derived keys of the test harness and no registered address."""
    c = Consent("id-v2c", "did:patient:x", "did:hospital:001", ["did:parent:A", "did:parent:B"], "Treatment", ["Observation"], 2,
                start_date=(datetime.now() - timedelta(days=1)).isoformat(), expiry_date=(datetime.now() + timedelta(days=30)).isoformat(),
                token_id="SBT-1", commitment=hex(C))
    for g in c.guardian_dids:
        held = wallet(g) if wallets else None
        if held is not None:
            c.guardian_addresses[g] = held.address
        sig, addr = ids.sign_consent_v2(g, c.consent_id, c.commitment, signer=held)
        c.signatures.append(g); c.signature_data[g] = {"scheme": "EIP-712", "signer": addr, "signature": sig}
    return c


# ---------------------------------------------------------------------------
# DID resolution and document verification (Algorithm 5.1, lines 1-8)
# ---------------------------------------------------------------------------
def test_did_key_secp256k1_matches_the_specification_vectors():
    for private_key, did in SECP256K1_VECTORS.items():
        public_key = keys.PrivateKey(bytes.fromhex(private_key)).public_key
        assert did_resolver.did_key(public_key.to_compressed_bytes()) == did
        doc = did_resolver.resolve(did)
        assert doc["id"] == did and did_resolver.verify_document(did, doc) is True
        assert did_resolver.ethereum_address(doc) == public_key.to_checksum_address()     # the wallet address follows from the identifier


def test_did_key_document_follows_the_method_specification():
    doc = did_resolver.resolve(ED25519_DID); key = ED25519_DID.split(":")[2]
    method = {"id": f"{ED25519_DID}#{key}", "type": "Multikey", "controller": ED25519_DID, "publicKeyMultibase": key}
    assert doc == {"@context": ["https://www.w3.org/ns/did/v1", "https://w3id.org/security/multikey/v1"], "id": ED25519_DID,
                   "verificationMethod": [method], "authentication": [method["id"]], "assertionMethod": [method["id"]],
                   "capabilityInvocation": [method["id"]], "capabilityDelegation": [method["id"]]}
    assert did_resolver.verify_document(ED25519_DID, doc) is True
    assert did_resolver.ethereum_address(doc) is None                                    # an Ed25519 key has no Ethereum address
    rfc8032 = bytes.fromhex("d75a980182b10ab7d54bfed3c964073a0ee172f3daa62325af021a68f707511a")   # public key of RFC 8032, test 1
    did = did_resolver.did_key(rfc8032, "Ed25519")
    assert did == "did:key:z" + b58(b"\xed\x01" + rfc8032) and did.startswith("did:key:z6Mk") and did_resolver.resolve(did)["id"] == did
    versioned = "did:key:1:" + key                                                       # version 1 written out
    assert did_resolver.verify_document(versioned, did_resolver.resolve(versioned)) is True


def test_did_resolution_fails_closed():
    secp = lambda raw: "did:key:z" + b58(b"\xe7\x01" + raw)
    ed = lambda raw: "did:key:z" + b58(b"\xed\x01" + raw)
    good = keys.PrivateKey(keccak(text="k")).public_key.to_compressed_bytes()
    assert did_resolver.resolve(secp(good))["id"] == secp(good)                          # positive control for the helpers
    cases = {
        "nope": "invalidDid", "did:key:": "invalidDid", "": "invalidDid", None: "invalidDid",
        "did:web:example.com": "methodNotSupported", "did:example:123": "methodNotSupported",
        "did:ethr:0xb9c5714089478a327f09197987f16f9e5d936e8a": "methodNotSupported",
        "did:key:z6LSbysY2xFMRpGMhb7tFTLMpeuPRaqaWM1yECx2AtzE3KCc": "unsupportedPublicKeyType",   # an X25519 key agreement key
        "did:key:f" + good.hex(): "invalidDid",                                         # not base58btc multibase
        "did:key:z0OIl": "invalidDid",                                                  # characters outside the alphabet
        "did:key:2:" + secp(good).split(":")[2]: "invalidDid",                          # only version 1 exists
        secp(good[:32]): "invalidPublicKeyLength", ed(bytes(31)): "invalidPublicKeyLength",
        secp(b"\x02" + (5).to_bytes(32, "big")): "invalidPublicKey",                    # x = 5 is not on secp256k1
        secp(b"\x04" + good[1:]): "invalidPublicKey",                                   # not a compressed key
        ed((2).to_bytes(32, "little")): "invalidPublicKey",                             # y = 2 is not on Ed25519
        "did:key:z" + b58(b"\xe7\x81\x00" + good): "invalidDid",                        # multicodec header not in its shortest form
    }
    for did, code in cases.items():
        with pytest.raises(did_resolver.DIDResolutionError) as e:
            did_resolver.resolve(did)
        assert e.value.code == code, did


def test_demonstration_identifiers_resolve_through_the_local_resolver():
    for did in GUARDIANS + DOCTORS + ["did:patient:5f01f823-c8e8-9e40-c911-54b7b1ad843a"]:
        doc = did_resolver.resolve(did)
        assert doc["id"] == did and did_resolver.verify_document(did, doc) is True
        assert doc["verificationMethod"][0]["blockchainAccountId"] == f"eip155:{ids.CHAIN_ID}:{ids.guardian_address(did)}"
        assert did_resolver.ethereum_address(doc) == ids.guardian_address(did)           # the derived demonstration key
    issuer = did_resolver.resolve(ids.ISSUER_DID)
    assert did_resolver.ethereum_address(issuer) == ids.TRUSTED_ISSUERS[ids.ISSUER_DID]
    assert ids.get_credential("did:parent:A")["proof"]["verificationMethod"] == issuer["assertionMethod"][0]


def test_document_check_fails_on_each_condition():
    did = "did:parent:A"; good = did_resolver.resolve(did)
    assert did_resolver.check_document(did, good) == {"Id_match": True, "Method_present": True, "Controller_match": True,
                                                       "Key_valid": True, "Relationship_valid": True, "VALID": True}

    def failed(change, target=did):
        doc = copy.deepcopy(did_resolver.resolve(target)); change(doc)
        r = did_resolver.check_document(target, doc); assert r["VALID"] is False
        return [k for k, v in r.items() if not v and k != "VALID"]

    attacker = wallet("attacker").address
    assert failed(lambda d: d.update(id="did:parent:B")) == ["Id_match"]
    assert failed(lambda d: d.update(verificationMethod=[])) == ["Method_present", "Controller_match", "Key_valid", "Relationship_valid"]
    assert failed(lambda d: d["verificationMethod"][0].update(controller="did:parent:B")) == ["Controller_match"]
    assert failed(lambda d: d["verificationMethod"][0].update(blockchainAccountId=f"eip155:{ids.CHAIN_ID}:{attacker}")) == ["Key_valid"]
    assert failed(lambda d: d["verificationMethod"][0].update(blockchainAccountId=f"eip155:1:{ids.guardian_address(did)}")) == ["Key_valid"]
    assert failed(lambda d: d["verificationMethod"][0].update(type="JsonWebKey2020")) == ["Key_valid"]
    assert failed(lambda d: d.pop("authentication")) == ["Relationship_valid"]
    assert failed(lambda d: d.update(assertionMethod=[did + "#key-9"])) == ["Relationship_valid"]
    # did:key is self-certifying: a document that carries any other key is not the document of the identifier
    other = list(SECP256K1_VECTORS.values())[1].split(":")[2]
    assert failed(lambda d: d["verificationMethod"][0].update(publicKeyMultibase=other), target=list(SECP256K1_VECTORS.values())[0]) == ["Key_valid"]
    for broken in (None, "a document", [], {}):
        assert did_resolver.verify_document(did, broken) is False


# ---------------------------------------------------------------------------
# Algorithm 5.1: identity and authority verification
# ---------------------------------------------------------------------------
def test_algorithm_5_1_returns_valid_for_every_demonstration_participant():
    for did, role in [(g, "guardian") for g in GUARDIANS] + [(d, "doctor") for d in DOCTORS]:
        r = verify_identity(did, role=role)
        assert r.valid is True and bool(r) is True and r.result == "VALID" and r.reason == R.OK
        assert all(r.checks.values()) and list(r.checks) == ["DID_resolved", "DID_document_valid", "VC_found", "Issuer_valid", "Sig_VC",
                                                              "Subject_match", "Time_valid", "Status_valid", "Role_match"]
        assert r.claims["role"] == role and r.evidence["credential_id"] == f"urn:halah:vc:{role}:{did}"
        assert r.evidence["did_method"] == did.split(":")[1] and r.evidence["issuer"] == ids.ISSUER_DID
    assert verify_identity("did:parent:A").valid is True                                # no role required: identity and credential only
    assert json.loads(json.dumps(verify_identity("did:parent:A", role="guardian").as_dict()))["result"] == "VALID"


def test_algorithm_5_1_stops_at_the_first_failed_line_with_its_reason():
    doctor = "did:hospital:001"; forger = wallet("forger")
    passed = lambda r: [k for k, v in r.checks.items() if v]

    def refused(reason, did=doctor, role="doctor", **kw):
        r = verify_identity(did, role=role, **kw)
        assert r.valid is False and bool(r) is False and r.result == "INVALID" and r.reason == reason and r.evidence["reason"] == reason
        return passed(r)

    # lines 1-4: the identifier does not resolve
    for did in ("did:web:example.com", "hospital:001", "did:key:z0OIl", None):
        assert refused(R.DID_RESOLUTION_FAILED, did=did) == []
    def offline(did): raise TimeoutError("resolver unreachable")
    assert refused(R.DID_RESOLUTION_FAILED, resolver=offline) == []
    # lines 5-8: the document is not the document of the identifier (its key was replaced)
    def swapped(did):
        doc = did_resolver.resolve(did); doc["verificationMethod"][0]["blockchainAccountId"] = f"eip155:{ids.CHAIN_ID}:{forger.address}"
        return doc
    assert refused(R.DID_DOCUMENT_INVALID, resolver=swapped) == ["DID_resolved"]
    assert refused(R.DID_DOCUMENT_INVALID, resolver=lambda did: {"id": did}) == ["DID_resolved"]
    # lines 9-12: no credential for a well-formed identifier that resolves
    assert refused(R.CREDENTIAL_NOT_FOUND, did="did:hospital:999") == ["DID_resolved", "DID_document_valid"]
    # lines 13-16: each of the four conditions, in turn
    found = ["DID_resolved", "DID_document_valid", "VC_found"]
    untrusted = ids.issue_credential(doctor, "doctor", issuer_did="did:example:unknown-issuer", signer=forger)
    assert refused(R.CREDENTIAL_ISSUER_UNTRUSTED, credential=untrusted) == found
    assert refused(R.CREDENTIAL_ISSUER_UNTRUSTED, credential="not a credential") == found
    forged = ids.issue_credential(doctor, "doctor", signer=forger)                       # the trusted issuer's name, another key
    assert refused(R.CREDENTIAL_SIGNATURE_INVALID, credential=forged) == found + ["Issuer_valid"]
    changed = copy.deepcopy(ids.get_credential(doctor)); changed["validUntil"] = "2099-12-31T23:59:59"
    assert refused(R.CREDENTIAL_SIGNATURE_INVALID, credential=changed) == found + ["Issuer_valid"]
    assert refused(R.CREDENTIAL_SUBJECT_MISMATCH, credential=ids.get_credential("did:hospital:002")) == found + ["Issuer_valid", "Sig_VC"]
    for when in (datetime(2031, 1, 1), datetime(2025, 12, 31)):                          # after validUntil, before validFrom
        assert refused(R.CREDENTIAL_TIME_INVALID, now=when) == found + ["Issuer_valid", "Sig_VC", "Subject_match"]
    # lines 17-20: a valid credential whose role claim is not the authority the step requires
    verified = found + ["Issuer_valid", "Sig_VC", "Subject_match", "Time_valid", "Status_valid"]
    assert refused(R.AUTHORITY_MISMATCH, role="guardian") == verified
    assert refused(R.AUTHORITY_MISMATCH, did="did:parent:A", role="doctor") == verified
    # line 13, the status check: revoked by the issuer
    status.revoke_credential(ids.get_credential(doctor))
    assert refused(R.CREDENTIAL_REVOKED) == found + ["Issuer_valid", "Sig_VC", "Subject_match", "Time_valid"]


def test_verify_identity_is_the_identity_check_of_the_decision():
    from services.access_service import evaluate_allow
    decide = lambda c, **kw: evaluate_allow(c, "AU", verify_sig=ids.verify_signature, verify_did=verify_identity, **kw)
    assert decide(_active(), requester_did="did:hospital:001")["ALLOW"] is True
    m = decide(_active(), requester_did="did:hospital:002")                             # a valid doctor, not the doctor of this consent
    assert m["VI"] is False and m["ALLOW"] is False
    c = _active(); c.expiry_date = "2099-12-31T23:59:59"
    m = decide(c, now=datetime(2031, 6, 1))                                             # the credential is checked at the evaluation time
    assert m["VI"] is False and m["ALLOW"] is False
    status.revoke_credential(ids.get_credential("did:hospital:001"))                    # the issuer withdraws the doctor's credential
    m = decide(_active(), requester_did="did:hospital:001")
    assert m["VI"] is False and m["ALLOW"] is False


def test_A12_forged_or_invalid_credential_is_refused_by_algorithm_5_1():
    from services.access_service import evaluate_allow
    doctor = "did:hospital:001"; forger = wallet("forger")
    assert verify_identity(doctor, role="doctor", credential=ids.get_credential(doctor)).valid is True     # positive control
    tampered = copy.deepcopy(ids.get_credential("did:parent:A")); tampered["credentialSubject"]["role"] = "doctor"
    bad = [ids.issue_credential(doctor, "doctor", signer=forger),
           ids.issue_credential(doctor, "doctor", issuer_did="did:example:unknown-issuer", signer=forger),
           tampered, ids.get_credential("did:hospital:002"),
           ids.issue_credential(doctor, "doctor", valid_until=(datetime.now() - timedelta(days=1)).isoformat(timespec="seconds")),
           ids.get_credential("did:parent:A")]
    for cred in bad:
        r = verify_identity(doctor, role="doctor", credential=cred)
        assert r.valid is False and r.reason != R.OK
        m = evaluate_allow(_active(), "AU", verify_sig=ids.verify_signature,
                           verify_did=lambda d, role=None, now=None, b=cred: verify_identity(d, role=role, now=now, credential=b))
        assert m["VI"] is False and m["ALLOW"] is False
    assert verify_identity("did:parent:A", role="guardian", credential=bad[0]).valid is False     # a forged guardian credential


def test_evidence_is_recorded_before_valid_is_returned():
    from database import audit_db
    seen = []
    r = verify_identity("did:parent:A", role="guardian", record=seen.append, now=datetime(2026, 11, 11, 9, 0, 0))
    assert r.valid is True and len(seen) == 1
    e = seen[0]
    assert e["result"] == "VALID" and e["reason"] == R.OK and e["did"] == "did:parent:A" and e["required_role"] == "guardian"
    assert e["checked_at"] == "2026-11-11T09:00:00" and e["verification_method"] == "did:parent:A#key-1"
    assert e["key_address"] == ids.guardian_address("did:parent:A") and e["claims"] == {"role": "guardian", "organisation": ""}
    assert e["status_list"] == status.default_list_id(ids.ISSUER_DID) and e["status_sequence"] == 0
    assert json.loads(json.dumps(e)) == e                                                # the evidence can be stored as it is
    seen.clear()
    assert verify_identity("did:parent:A", role="doctor", record=seen.append).valid is False and seen == []
    def ledger_down(evidence): raise OSError("ledger not writable")
    r = verify_identity("did:parent:A", role="guardian", record=ledger_down)             # no VALID without its evidence
    assert r.valid is False and r.reason == R.EVIDENCE_NOT_RECORDED
    before = len(audit_db.get())
    r = verify_identity("did:hospital:001", role="doctor",
                        record=partial(ids.record_identity_evidence, consent_id="id-v2", patient_did="did:patient:x"))
    row = audit_db.get()[-1]
    assert r.valid is True and len(audit_db.get()) == before + 1
    assert (row["action"], row["actor_did"], row["actor_role"], row["result"]) == ("IDENTITY_VERIFICATION", "did:hospital:001", "Doctor", "VALID")
    assert row["consent_id"] == "id-v2" and row["metadata"]["credential_id"] == "urn:halah:vc:doctor:did:hospital:001"
    assert row["event_digest"] == audit_db.event_digest(row) and row["onchain"] is False


def test_verify_identity_reads_a_time_with_a_zone_as_the_same_instant():
    from datetime import timezone
    did = "did:hospital:001"; inside = datetime(2027, 6, 1, 12, 0, 0); after = datetime(2031, 6, 1, 12, 0, 0)
    for zone in (timezone.utc, timezone(timedelta(hours=11)), timezone(timedelta(hours=-8))):
        r = verify_identity(did, role="doctor", now=inside.replace(tzinfo=zone))         # a block timestamp arrives with a zone
        assert r.valid is True and r.evidence["checked_at"] == inside.replace(tzinfo=zone).astimezone().replace(tzinfo=None).isoformat()
        assert verify_identity(did, role="doctor", now=after.replace(tzinfo=zone)).reason == R.CREDENTIAL_TIME_INVALID
    assert verify_identity(did, role="doctor", now="2027-06-01").reason == R.CREDENTIAL_TIME_INVALID       # not a time: refused, no error


def test_did_key_participant_passes_algorithm_5_1_with_an_issued_credential():
    holder = wallet("guardian one"); did = wallet_did(holder)
    cred = ids.issue_credential(did, "guardian", status_index=7)
    r = verify_identity(did, role="guardian", credential=cred)
    assert r.valid is True and r.evidence["did_method"] == "key" and r.evidence["key_address"] == holder.address
    assert r.evidence["status_index"] == 7 and r.evidence["verification_method"] == f"{did}#{did.split(':')[2]}"
    assert verify_identity(did, role="guardian").reason == R.CREDENTIAL_NOT_FOUND        # the store holds no credential for it
    assert verify_identity(wallet_did(wallet("someone else")), role="guardian", credential=cred).reason == R.CREDENTIAL_SUBJECT_MISMATCH
    assert verify_identity(ED25519_DID, role="guardian", credential=ids.issue_credential(ED25519_DID, "guardian")).valid is True


# ---------------------------------------------------------------------------
# Credential status list
# ---------------------------------------------------------------------------
def test_status_list_encoding_follows_the_bitstring_recommendation(status_store):
    assert status.LIST_SIZE == 131072
    bits = bytearray(EMPTY); bits[0] = 0x80; bits[1] = 0x01                              # positions 0 and 15 are set
    encoded = status.encode_list(bits)
    assert encoded.startswith("u") and "=" not in encoded
    assert gzip.decompress(base64.urlsafe_b64decode(encoded[1:] + "=" * (-len(encoded[1:]) % 4))) == bytes(bits)
    assert status.decode_list(encoded) == bytes(bits)
    status.publish_status_list(status.sign_status_list(ids.ISSUER_DID, bits, 1))
    at = lambda i: status.is_revoked(ids.issue_credential("did:parent:A", "guardian", status_index=i))
    assert [i for i in (0, 1, 7, 8, 14, 15, 16, status.LIST_SIZE - 1) if at(i)] == [0, 15]       # position 0 is the left-most bit
    pack = lambda data: "u" + base64.urlsafe_b64encode(gzip.compress(data)).decode().rstrip("=")
    for bad in ("", "zabc", "u", "u!!!!", encoded[:-8], pack(bytes(len(EMPTY) + 1)), pack(bytes(len(EMPTY) - 1)), None, 5):
        with pytest.raises(status.StatusListError):
            status.decode_list(bad)
    with pytest.raises(status.StatusListError):
        status.encode_list(bytes(10))
    # a small encoded list that expands to 50 megabytes is refused without being expanded
    huge = pack(bytes(50_000_000)); assert len(huge) < 100_000
    tracing = tracemalloc.is_tracing()
    if not tracing:
        tracemalloc.start()
    tracemalloc.reset_peak(); before = tracemalloc.get_traced_memory()[0]
    with pytest.raises(status.StatusListError):
        status.decode_list(huge)
    grown = tracemalloc.get_traced_memory()[1] - before
    if not tracing:
        tracemalloc.stop()
    assert grown < 2_000_000


def test_nothing_is_revoked_until_the_issuer_publishes_a_list(status_store):
    creds = list(ids.load_credentials().values())
    assert len(creds) == 7 and len({status.status_entry(c) for c in creds}) == 7        # no two demonstration credentials share a position
    assert all(status.is_revoked(c) is False for c in creds) and not status_store.exists()
    first = status.current_status_list(ids.ISSUER_DID)
    assert first["sequence"] == 0 and first["issuer"] == ids.ISSUER_DID and status.verify_status_list(first) == EMPTY
    assert first["type"] == ["VerifiableCredential", "BitstringStatusListCredential"]
    assert first["credentialSubject"]["type"] == "BitstringStatusList" and first["credentialSubject"]["statusPurpose"] == "revocation"


def test_revocation_by_the_issuer_refuses_the_credential_at_line_13(status_store):
    cred = ids.get_credential("did:parent:A")
    assert verify_identity("did:parent:A", role="guardian").valid is True
    published = status.revoke_credential(cred, now=datetime(2026, 11, 11, 9, 0, 0))
    assert published["sequence"] == 1 and published["validFrom"] == "2026-11-11T09:00:00"
    assert json.loads(status_store.read_text())["statusLists"][ids.ISSUER_DID][published["id"]] == published
    assert sum(bin(b).count("1") for b in status.verify_status_list(published)) == 1     # one credential, one bit
    assert status.is_revoked(cred) is True
    assert status.check_status(cred) == {"revoked": True, "status_list": published["id"], "index": status.status_entry(cred)[1], "sequence": 1}
    r = verify_identity("did:parent:A", role="guardian")
    assert r.valid is False and r.reason == R.CREDENTIAL_REVOKED and r.checks["Sig_VC"] is True and r.checks["Status_valid"] is False
    for did, role in [(g, "guardian") for g in GUARDIANS[1:]] + [(d, "doctor") for d in DOCTORS]:
        assert verify_identity(did, role=role).valid is True                             # nobody else is affected
    status._verified.clear(); status._initial.clear()                                    # a verifier that starts afresh reads the same list
    assert status.is_revoked(cred) is True
    assert status.revoke_credential(cred) == published                                   # revoking twice changes nothing
    second = status.revoke_credential(ids.get_credential("did:hospital:002"))
    assert second["sequence"] == 2 and status.is_revoked(cred) and status.is_revoked(ids.get_credential("did:hospital:002"))
    assert status.is_revoked(ids.get_credential("did:parent:B")) is False


def test_only_the_issuer_can_revoke_and_a_forged_list_is_not_trusted(status_store):
    doctor = "did:hospital:001"; cred = ids.get_credential(doctor); forger = wallet("forger")
    with pytest.raises(status.StatusListError):
        status.revoke_credential(cred, signer=forger)
    assert not status_store.exists() and verify_identity(doctor, role="doctor").valid is True
    status.revoke_credential(cred)
    # the attacker replaces the published list with an empty one signed by the attacker's own key
    empty = status.sign_status_list(ids.ISSUER_DID, EMPTY, 2, signer=forger)
    with pytest.raises(status.StatusListError):
        status.publish_status_list(empty)
    status_store.write_text(json.dumps({"statusLists": {ids.ISSUER_DID: {empty["id"]: empty}}}))
    with pytest.raises(status.StatusListError):
        status.is_revoked(cred)
    r = verify_identity(doctor, role="doctor")                                           # an unknown status is not a good status
    assert r.valid is False and r.reason == R.CREDENTIAL_STATUS_UNAVAILABLE
    # a list signed by an issuer that is not in the registry is not trusted either
    stranger = status.sign_status_list("did:example:unknown-issuer", EMPTY, 1, signer=forger)
    with pytest.raises(status.StatusListError):
        status.verify_status_list(stranger)
    status_store.write_text("{ not json")                                                # a store that cannot be read
    assert verify_identity(doctor, role="doctor").reason == R.CREDENTIAL_STATUS_UNAVAILABLE


def test_a_changed_status_list_fails_its_signature(status_store):
    cred = ids.get_credential("did:parent:B")
    published = status.revoke_credential(cred)
    assert status.is_revoked(cred, status_list=published) is True
    def changed(**kw):
        sl = copy.deepcopy(published)
        for k, v in kw.items():
            (sl["credentialSubject"] if k in ("encodedList", "statusPurpose") else sl).__setitem__(k, v)
        return sl
    for bad in (changed(encodedList=status.encode_list(EMPTY)),                           # the revoked bit cleared after signing
                changed(sequence=9), changed(validFrom="2020-01-01T00:00:00"), changed(statusPurpose="suspension"),
                changed(id="urn:halah:status:another-list"), changed(issuer="did:example:unknown-issuer"),
                changed(proof={}), changed(sequence="1"), changed(sequence=True), "a list", {}):
        with pytest.raises(status.StatusListError):
            status.is_revoked(cred, status_list=bad)
    # genuine lists of the same issuer that are not the revocation list this credential names
    another = status.sign_status_list(ids.ISSUER_DID, EMPTY, 3, list_id="urn:halah:status:another-list")
    assert status.verify_status_list(another) == EMPTY
    with pytest.raises(status.StatusListError, match="not the status list the credential names"):
        status.is_revoked(cred, status_list=another)
    suspension = status.sign_status_list(ids.ISSUER_DID, EMPTY, 3); suspension["credentialSubject"]["statusPurpose"] = "suspension"
    suspension["proof"]["proofValue"] = "0x" + ids._issuer_account(ids.ISSUER_DID).sign_message(status._signable(suspension)).signature.hex().removeprefix("0x")
    with pytest.raises(status.StatusListError, match="does not record revocation"):
        status.is_revoked(cred, status_list=suspension)
    assert status.is_revoked(cred) is True                                               # none of this changed the published answer


def test_revocation_is_not_reversible_and_an_older_list_is_refused(status_store):
    cred = ids.get_credential("did:parent:C")
    before = status.current_status_list(ids.ISSUER_DID)                                 # the genuine list before the revocation
    assert status.is_revoked(cred, status_list=before) is False
    published = status.revoke_credential(cred)
    with pytest.raises(status.StatusListError, match="not reversible"):                  # even the issuer cannot clear the bit
        status.publish_status_list(status.sign_status_list(ids.ISSUER_DID, EMPTY, 5))
    with pytest.raises(status.StatusListError, match="must increase"):
        status.publish_status_list(status.sign_status_list(ids.ISSUER_DID, status.verify_status_list(published), 1))
    with pytest.raises(status.StatusListError, match="older"):                           # the earlier list replayed to the verifier
        status.is_revoked(cred, status_list=before)
    status_store.unlink()                                                                # the published file rolled back
    with pytest.raises(status.StatusListError, match="older"):
        status.is_revoked(cred)
    assert verify_identity("did:parent:C", role="guardian").reason == R.CREDENTIAL_STATUS_UNAVAILABLE


def test_status_entry_is_signed_with_the_credential(status_store):
    did = "did:parent:D"; list_id = status.default_list_id(ids.ISSUER_DID)
    cred = ids.issue_credential(did, "guardian", status_index=5)
    assert cred["credentialStatus"] == {"id": f"{list_id}#5", "type": "BitstringStatusListEntry", "statusPurpose": "revocation",
                                        "statusListIndex": "5", "statusListCredential": list_id}
    assert ids.check_credential(did, role="guardian", credential=cred)["VALID"] is True and status.status_entry(cred) == (list_id, 5)
    moved = copy.deepcopy(cred); moved["credentialStatus"]["statusListIndex"] = "6"      # the holder points at another position
    stripped = {k: v for k, v in cred.items() if k != "credentialStatus"}                # or removes the entry
    added = dict(ids.get_credential(did), credentialStatus=cred["credentialStatus"])     # or adds one to an older credential
    for bad in (moved, stripped, added):
        assert ids.check_credential(did, role="guardian", credential=bad)["Sig_VC"] is False
        assert verify_identity(did, role="guardian", credential=bad).reason == R.CREDENTIAL_SIGNATURE_INVALID
    for entry in ({}, [], {"type": "BitstringStatusListEntry", "statusPurpose": "suspension", "statusListIndex": "5", "statusListCredential": list_id},
                  dict(cred["credentialStatus"], statusListIndex=5), dict(cred["credentialStatus"], statusListIndex=str(status.LIST_SIZE)),
                  dict(cred["credentialStatus"], statusListIndex="-1")):
        with pytest.raises(status.StatusListError):
            status.status_entry(dict(cred, credentialStatus=entry))
    status.revoke_credential(cred)
    assert status.is_revoked(cred) is True and verify_identity(did, role="guardian", credential=cred).reason == R.CREDENTIAL_REVOKED
    fresh = ids.issue_credential(did, "guardian", status_index=6)                        # re-issued at a new position
    assert fresh["id"] != cred["id"] and verify_identity(did, role="guardian", credential=fresh).valid is True
    assert verify_identity(did, role="guardian").valid is True                           # the stored credential has its own position
    with pytest.raises(ValueError):
        ids.issue_credential(did, "guardian", status_index=status.LIST_SIZE)
    plain = ids.issue_credential("did:parent:A", "guardian")                             # without a position nothing changes
    assert plain == ids.get_credential("did:parent:A") and "credentialStatus" not in plain


def test_status_functions_take_the_identifier_of_a_stored_credential(status_store):
    did = "did:parent:D"
    assert status.is_revoked(did) is False and status.check_status(did) == status.check_status(ids.get_credential(did))
    published = status.revoke_credential(did)
    assert published["sequence"] == 1 and status.is_revoked(did) is True and status.is_revoked(ids.get_credential(did)) is True
    assert status.is_revoked("did:hospital:003") is False and verify_identity(did, role="guardian").reason == R.CREDENTIAL_REVOKED
    for unknown in ("did:hospital:999", "", "not a did"):                                # no stored credential: no answer, not "not revoked"
        with pytest.raises(status.StatusListError):
            status.is_revoked(unknown)
        with pytest.raises(status.StatusListError):
            status.revoke_credential(unknown)
    for broken in (None, 7, [], {}, {"id": "urn:x"}):                                    # nothing that names an issuer
        with pytest.raises(status.StatusListError):
            status.is_revoked(broken)


def test_an_issuer_with_its_own_key_publishes_and_revokes_with_that_key(status_store, monkeypatch):
    """The production model: the verifier knows only the registered address of the issuer. The issuer's key is held
    by the issuer, here a wallet whose did:key is the issuer identifier, and nothing derives it."""
    authority = wallet("health authority"); issuer = wallet_did(authority)
    holder = wallet("guardian one"); did = wallet_did(holder)
    cred = ids.issue_credential(did, "guardian", issuer_did=issuer, signer=authority, status_index=11)
    assert verify_identity(did, role="guardian", credential=cred).reason == R.CREDENTIAL_ISSUER_UNTRUSTED   # not yet in the registry
    monkeypatch.setitem(ids.TRUSTED_ISSUERS, issuer, authority.address)
    assert ids.check_credential(did, role="guardian", credential=cred)["VALID"] is True
    # until this issuer publishes its list there is no status: the stand-in list of the demonstration key is not its list
    assert verify_identity(did, role="guardian", credential=cred).reason == R.CREDENTIAL_STATUS_UNAVAILABLE
    with pytest.raises(status.StatusListError):
        status.publish_status_list(status.sign_status_list(issuer, EMPTY, 1))            # signed with the derived key: refused
    first = status.publish_status_list(status.sign_status_list(issuer, EMPTY, 1, signer=authority, valid_from="2026-11-11T09:00:00"))
    key = did_resolver.resolve(issuer)["assertionMethod"][0]                             # the proofs name the key of the issuer's document
    assert first["id"] == status.default_list_id(issuer) and first["proof"]["verificationMethod"] == key == cred["proof"]["verificationMethod"]
    r = verify_identity(did, role="guardian", credential=cred)
    assert r.valid is True and r.evidence["issuer"] == issuer and r.evidence["status_sequence"] == 1 and r.evidence["status_index"] == 11
    with pytest.raises(status.StatusListError, match="only the issuer"):
        status.revoke_credential(cred)                                                   # the demonstration key is not this issuer
    with pytest.raises(status.StatusListError, match="only the issuer"):
        status.revoke_credential(cred, signer=holder)                                    # nor is the holder
    assert verify_identity(did, role="guardian", credential=cred).valid is True
    assert status.revoke_credential(cred, signer=authority)["sequence"] == 2
    assert verify_identity(did, role="guardian", credential=cred).reason == R.CREDENTIAL_REVOKED
    assert verify_identity("did:parent:A", role="guardian").valid is True                # the other issuer's list is a separate list
    # a trusted issuer cannot answer for another issuer's credentials, nor take the place of that issuer's list
    theirs = status.default_list_id(ids.ISSUER_DID); other = ids.get_credential("did:parent:A")
    squat = status.sign_status_list(issuer, EMPTY, 9, list_id=theirs, signer=authority)
    with pytest.raises(status.StatusListError, match="another issuer"):
        status.is_revoked(other, status_list=squat)
    status.publish_status_list(squat)                                                    # it lands on this issuer's own shelf
    assert status.revoke_credential(other)["sequence"] == 1 and status.is_revoked(other) is True
    stored = json.loads(status_store.read_text())["statusLists"]
    assert set(stored) == {issuer, ids.ISSUER_DID} and set(stored[issuer]) == {status.default_list_id(issuer), theirs}


# ---------------------------------------------------------------------------
# EIP-712 approval over the consent commitment (Algorithm 5.2)
# ---------------------------------------------------------------------------
def test_v2_approval_roundtrip_with_the_harness_key():
    sig, addr = ids.sign_consent_v2("did:parent:A", CID, C)
    assert sig.startswith("0x") and len(sig) == 132 and addr == ids.guardian_address("did:parent:A")
    assert ids.verify_signature_v2("did:parent:A", CID, C, sig) is True
    assert ids.recover_signer_v2("did:parent:A", CID, C, sig) == addr                    # the recovery step, on its own
    assert ids.verify_signature_v2("did:parent:A", CID, C, bytes.fromhex(sig[2:])) is True
    assert ids.verify_signature_v2("did:parent:A") is False and ids.verify_signature_v2("did:parent:A", CID, C) is False


def test_v2_approval_binds_consent_guardian_commitment_and_chain():
    did = "did:parent:A"; sig, addr = ids.sign_consent_v2(did, CID, C)
    assert ids.verify_signature_v2(did, "consent-999", C, sig) is False                  # A2: replayed for another consent
    assert ids.verify_signature_v2("did:parent:B", CID, C, sig) is False                 # another guardian
    assert ids.verify_signature_v2(did, CID, C + 1, sig) is False                        # the consent changed after approval
    assert ids.verify_signature_v2(did, CID, C, sig, chain_id=ids.CHAIN_ID + 1) is False  # another chain
    elsewhere, _ = ids.sign_consent_v2(did, CID, C, chain_id=1)                          # signed for Ethereum mainnet
    assert ids.verify_signature_v2(did, CID, C, elsewhere) is False and ids.verify_signature_v2(did, CID, C, elsewhere, chain_id=1) is True
    assert ids.verify_signature_v2(did, CID, C, sig, action="REVOKE") is False           # an approval is not another statement
    for other in (("consent-999", C, None), (CID, C + 1, None), (CID, C, 1)):
        assert ids.recover_signer_v2(did, other[0], other[1], sig, chain_id=other[2]) != addr
    # the earlier approval, which does not cover the commitment, and this one are not interchangeable
    v1, _ = ids.sign_consent(did, CID)
    assert ids.verify_signature(did, CID, v1) is True and ids.verify_signature_v2(did, CID, C, v1) is False
    assert ids.verify_signature(did, CID, sig) is False


def test_v2_approval_with_a_wallet_held_key():
    did = "did:parent:B"; held = wallet("guardian B")
    consent = Consent("id-w", "did:patient:x", "did:hospital:001", ["did:parent:A", did], "Treatment", ["Observation"], 2,
                      commitment=hex(C), guardian_addresses={did: held.address})
    sig, addr = ids.sign_consent_v2(did, consent.consent_id, consent.commitment, signer=held)
    assert addr == held.address != ids.guardian_address(did)
    check = lambda s, **kw: ids.verify_signature_v2(did, consent.consent_id, consent.commitment, s, **kw)
    assert check(sig, address=consent.guardian_addresses.get(did)) is True
    assert check(sig, address=held.address.lower()) is True                              # an address written without checksum case
    # whoever derives the demonstration key cannot approve for a guardian whose wallet address is registered
    derived, _ = ids.sign_consent_v2(did, consent.consent_id, consent.commitment)
    assert check(derived, address=held.address) is False
    assert check(ids.sign_consent_v2(did, consent.consent_id, consent.commitment, signer=wallet("uncle"))[0], address=held.address) is False
    assert check(sig) is False                                                           # with no address registered the derived key is expected
    assert check(derived, address=consent.guardian_addresses.get("did:parent:A")) is True   # A has none registered (None): the harness path
    for bad in ("", "0x1234", held.address[:-1], 5, b"\x00" * 20):                       # a malformed address refuses, it never falls back
        assert check(derived, address=bad) is False and check(sig, address=bad) is False


def test_v2_approval_of_a_did_key_guardian_is_checked_against_its_identifier():
    held = wallet("guardian one"); did = wallet_did(held)
    sig, addr = ids.sign_consent_v2(did, CID, C, signer=held)
    check = lambda d, s, **kw: ids.verify_signature_v2(d, CID, C, s, **kw)
    assert addr == held.address and check(did, sig) is True                              # the identifier is the wallet's public key
    with pytest.raises(ValueError):
        ids.sign_consent_v2(did, CID, C)                                                 # there is no derived key for it
    by_derived_key = ids.sign_consent_v2(did, CID, C, signer=ids.guardian_account(did))[0]
    by_another_wallet = ids.sign_consent_v2(did, CID, C, signer=wallet("uncle"))[0]
    assert check(did, by_derived_key) is False and check(did, by_another_wallet) is False
    # the identifier is the key: an address registered beside it cannot put another key in its place
    uncle = wallet("uncle")
    assert check(did, sig, address=held.address) is True and check(did, sig, address=held.address.lower()) is True
    assert check(did, by_another_wallet, address=uncle.address) is False
    assert check(did, sig, address=uncle.address) is False and check(did, sig, address="") is False
    # an Ed25519 identifier has no key that can sign typed data: only a registered wallet can approve for it
    by_wallet = ids.sign_consent_v2(ED25519_DID, CID, C, signer=held)[0]
    by_derived_key = ids.sign_consent_v2(ED25519_DID, CID, C, signer=ids.guardian_account(ED25519_DID))[0]
    assert check(ED25519_DID, by_wallet) is False and check(ED25519_DID, by_derived_key) is False   # no Ethereum key, and no derived key either
    assert check(ED25519_DID, by_wallet, address=held.address) is True and check(ED25519_DID, by_wallet, address=uncle.address) is False
    malformed = ids.sign_consent_v2("did:key:z0OIl", CID, C, signer=held)[0]             # an identifier that does not resolve approves nothing
    assert check("did:key:z0OIl", malformed) is False and check("did:key:z0OIl", malformed, address=held.address) is False


def test_v2_commitment_forms_and_malformed_commitments():
    did = "did:parent:A"; sig, _ = ids.sign_consent_v2(did, CID, C)
    for form in (C, hex(C), f"{C:064x}", f"{C:064X}", str(C), C.to_bytes(32, "big")):     # one commitment, however it is written
        assert ids.commitment_value(form) == C and ids.verify_signature_v2(did, CID, form, sig) is True
    assert ids.commitment_value("0x10") == 16 and ids.commitment_value("10") == 10 and ids.commitment_value("1" * 64) == int("1" * 64, 16)
    for bad in (None, "", "xyz", "0x", "12ab", "0x" + "f" * 65, "0x12_34", " 12", "-5", 0, -1, 2 ** 256, True, 1.5, b"", [C]):
        assert ids.verify_signature_v2(did, CID, bad, sig) is False
        with pytest.raises(ValueError):
            ids.sign_consent_v2(did, CID, bad)


def test_v2_malformed_signatures_are_rejected_without_an_error():
    from eth_account.messages import encode_typed_data
    did = "did:parent:A"; sig, addr = ids.sign_consent_v2(did, CID, C)
    raw = bytes.fromhex(sig[2:]); r, s, v = raw[:32], int.from_bytes(raw[32:64], "big"), raw[64]
    twin = r + (N - s).to_bytes(32, "big") + bytes([55 - v])                             # the second signature ECDSA allows for the same message
    signable = encode_typed_data(full_message=ids.approval_typed_data(did, CID, C))
    assert Account.recover_message(signable, signature=twin) == addr                     # plain recovery accepts it
    assert ids.verify_signature_v2(did, CID, C, "0x" + twin.hex()) is False              # the approval check does not
    for bad in ("0x", "0x" + "11" * 65, "0x" + "00" * 65, sig[:-2], sig + "00", "not hex", "0x" + "zz" * 65, b"\x01" * 64, 12345, object()):
        assert ids.verify_signature_v2(did, CID, C, bad) is False and ids.recover_signer_v2(did, CID, C, bad) is None


def test_v2_typed_data_is_what_a_wallet_signs():
    did = "did:parent:A"; chain = ids.CHAIN_ID
    data = ids.approval_typed_data(did, CID, C)
    assert json.loads(json.dumps(data)) == data                                          # the JSON a wallet takes in eth_signTypedData_v4
    assert data["primaryType"] == "Approval" and data["domain"] == {"name": "HALAH Consent", "version": "2", "chainId": chain}
    assert [(f["name"], f["type"]) for f in data["types"]["Approval"]] == [
        ("consentId", "string"), ("guardian", "string"), ("commitment", "uint256"), ("chainId", "uint256"), ("action", "string")]
    assert data["message"] == {"consentId": CID, "guardian": did, "commitment": str(C), "chainId": chain, "action": "APPROVE"}
    # the EIP-712 digest, computed here by hand from the standard, signed by a wallet key through another library
    word = lambda n: n.to_bytes(32, "big")
    domain = keccak(keccak(b"EIP712Domain(string name,string version,uint256 chainId)") + keccak(b"HALAH Consent") + keccak(b"2") + word(chain))
    struct = keccak(keccak(b"Approval(string consentId,string guardian,uint256 commitment,uint256 chainId,string action)")
                    + keccak(CID.encode()) + keccak(did.encode()) + word(C) + word(chain) + keccak(b"APPROVE"))
    digest = keccak(b"\x19\x01" + domain + struct)
    held = wallet("guardian A")
    sig = keys.PrivateKey(held.key).sign_msg_hash(digest).to_bytes()
    assert ids.recover_signer_v2(did, CID, C, sig) == held.address
    assert ids.verify_signature_v2(did, CID, C, sig, address=held.address) is True
    assert ids.verify_signature_v2(did, CID, C, sig) is False                            # it is not the derived key


def test_v2_derived_key_can_be_switched_off_outside_the_harness():
    did = "did:parent:A"; held = wallet("guardian A"); strict = partial(ids.verify_signature_v2, allow_demo_key=False)
    derived, _ = ids.sign_consent_v2(did, CID, C)
    assert ids.verify_signature_v2(did, CID, C, derived) is True                         # the harness path, as before
    assert strict(did, CID, C, derived) is False                                         # no registered address: nothing to check against
    assert strict(did, CID, C, derived, address=ids.guardian_address(did)) is True       # an address that was registered is still an address
    by_wallet, _ = ids.sign_consent_v2(did, CID, C, signer=held)
    assert strict(did, CID, C, by_wallet, address=held.address) is True and strict(did, CID, C, by_wallet) is False
    key_did = wallet_did(held)                                                           # a did:key carries its own key, which is not a derived key
    assert strict(key_did, CID, C, ids.sign_consent_v2(key_did, CID, C, signer=held)[0]) is True
    assert strict(key_did, CID, C, ids.sign_consent_v2(key_did, CID, C, signer=wallet("uncle"))[0]) is False


def _decide_v2(c, **kw):
    """The decision with Algorithm 5.1 as its identity check and the approval over the commitment as its signature check."""
    from services.access_service import evaluate_allow
    return evaluate_allow(c, "AU", verify_sig=ids.approval_verifier(c, **kw), verify_did=verify_identity)


def _refused(matrix, by):
    return matrix[by] is False and matrix["ALLOW"] is False


def test_approval_verifier_is_the_signature_check_of_the_decision():
    a, b = "did:parent:A", "did:parent:B"
    assert _decide_v2(_active_v2())["ALLOW"] is True                                     # both guardians signed c with their wallets
    assert _decide_v2(_active_v2(wallets=False))["ALLOW"] is True                        # the harness path, derived keys
    assert _refused(_decide_v2(_active_v2(wallets=False), allow_demo_key=False), "VI")   # outside the harness a derived key approves nothing
    # the consent changed after approval: the commitment over its current fields is no longer the one that was signed
    assert _refused(_decide_v2(_active_v2(), commitment=C + 1), "VI")
    c = _active_v2(); c.commitment = hex(C + 1); assert _refused(_decide_v2(c), "VI")
    c = _active_v2(); c.commitment = None; assert _refused(_decide_v2(c), "VI")          # no commitment, no approval
    # the derived key, which anyone can rebuild, signs for a guardian whose wallet address is registered
    c = _active_v2(); c.signature_data[b]["signature"] = ids.sign_consent_v2(b, c.consent_id, C)[0]
    assert _refused(_decide_v2(c), "VI")
    c = _active_v2(); c.signature_data[b]["signature"] = c.signature_data[a]["signature"]   # one guardian's signature under the other's name
    assert _refused(_decide_v2(c), "VI")
    c = _active(); c.commitment = hex(C); assert _refused(_decide_v2(c), "VI")           # approvals of the earlier scheme do not cover c
    # the check on its own: it belongs to one consent
    c = _active_v2(); check = ids.approval_verifier(c); sig = c.signature_data[a]["signature"]
    assert check(a, c.consent_id, sig) is True and check(a, "another-consent", sig) is False and check(a) is False
    assert check(b, c.consent_id, sig) is False and check(a, c.consent_id, None) is False
    elsewhere = ids.sign_consent_v2(a, "another-consent", C, signer=wallet(a))[0]        # her genuine approval of another consent
    assert check(a, "another-consent", elsewhere) is False                               # is not an approval this consent can count
    c.guardian_addresses = None; assert check(a, c.consent_id, sig) is False             # no address, and the derived key did not sign


# A1 - a signer outside the guardian set G submits an approval of the commitment that verifies
def test_A1_v2_signer_outside_G_is_not_counted():
    a, b, uncle = "did:parent:A", "did:parent:B", "did:parent:Z"
    c = _active_v2(); c.signatures = [a]; del c.signature_data[b]
    c.guardian_addresses[uncle] = wallet(uncle).address
    sig = ids.sign_consent_v2(uncle, c.consent_id, c.commitment, signer=wallet(uncle))[0]
    c.signatures.append(uncle); c.signature_data[uncle] = {"scheme": "EIP-712", "signer": wallet(uncle).address, "signature": sig}
    assert ids.approval_verifier(c)(uncle, c.consent_id, sig) is True                    # cryptographically valid, but Z is not in G
    assert _refused(_decide_v2(c), "VA")
    # the uncle signs under a guardian's name: the signer that is recovered is not the guardian's wallet
    c = _active_v2(); c.signature_data[b]["signature"] = ids.sign_consent_v2(b, c.consent_id, c.commitment, signer=wallet(uncle))[0]
    assert _refused(_decide_v2(c), "VI")


# A2 - replay of a guardian's signature from another consent
def test_A2_v2_replayed_signature_is_rejected():
    a = "did:parent:A"
    for earlier in (C, C + 1):                                                           # the earlier consent, with the same or another commitment
        replayed = ids.sign_consent_v2(a, "an-earlier-consent", earlier, signer=wallet(a))[0]
        assert ids.verify_signature_v2(a, "an-earlier-consent", earlier, replayed, address=wallet(a).address) is True
        c = _active_v2(); c.signature_data[a]["signature"] = replayed
        assert ids.verify_signature_v2(a, c.consent_id, c.commitment, replayed, address=wallet(a).address) is False
        assert _refused(_decide_v2(c), "VI")
    c = _active_v2(); other_chain = ids.sign_consent_v2(a, c.consent_id, c.commitment, signer=wallet(a), chain_id=1)[0]
    c.signature_data[a]["signature"] = other_chain                                       # the same approval, signed for another chain
    assert _refused(_decide_v2(c), "VI")


# A3 - the same guardian approves twice to reach the threshold
def test_A3_v2_duplicate_approval_does_not_reach_threshold():
    a, b = "did:parent:A", "did:parent:B"
    c = _active_v2(); c.signatures = [a, a]; del c.signature_data[b]
    assert ids.approval_verifier(c)(a, c.consent_id, c.signature_data[a]["signature"]) is True
    assert _refused(_decide_v2(c), "VA")


def test_case_study_two_guardians_approve_with_wallets_and_two_attempts_are_refused():
    """Section 5.7: both guardians pass Algorithm 5.1 and sign the commitment with their wallets. An approval by a
    person outside G (A1) and a signature replayed from an earlier consent (A2) are refused."""
    father, mother, uncle = "did:parent:A", "did:parent:B", "did:parent:Z"
    wallets = {father: wallet("father"), mother: wallet("mother"), uncle: wallet("uncle")}
    consent = Consent("layan-2", "did:patient:x", "did:hospital:001", [father, mother], "Treatment", ["Observation"], 2,
                      commitment=hex(C), guardian_addresses={father: wallets[father].address, mother: wallets[mother].address})

    def approve(did, signature):
        """Algorithm 5.2 for one approval: identity and authority, membership of G, recovery of the signer, no duplicate."""
        if not verify_identity(did, role="guardian") or did not in consent.guardian_dids or did in consent.signatures:
            return False
        if not ids.verify_signature_v2(did, consent.consent_id, consent.commitment, signature, address=consent.guardian_addresses.get(did)):
            return False
        consent.signatures.append(did); consent.signature_data[did] = {"scheme": "EIP-712", "signature": signature}
        return True

    sign = lambda did, cid=consent.consent_id, c=consent.commitment: ids.sign_consent_v2(did, cid, c, signer=wallets[did])[0]
    assert approve(uncle, sign(uncle)) is False                                          # A1: not a guardian of this consent
    assert approve(mother, sign(mother, cid="layan-1", c=C + 1)) is False                # A2: her signature for an earlier consent
    assert approve(mother, sign(mother, cid="layan-1")) is False                         # even over the same commitment
    assert approve(father, sign(father)) is True and len(consent.signatures) == 1 < consent.threshold      # pending at 1 of 2
    assert approve(father, sign(father)) is False                                        # A3: the same guardian again
    assert approve(mother, sign(father)) is False                                        # his signature under her name
    assert approve(mother, sign(mother)) is True and len(set(consent.signatures)) == consent.threshold     # the threshold is met
