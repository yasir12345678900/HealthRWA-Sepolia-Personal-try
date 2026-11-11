'''
DID Resolution for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11
'''
# Lines 1 to 8 of Algorithm 5.1: resolve a decentralised identifier to its DID document and verify the document.
#
# resolve(did)                 -> the DID document, or DIDResolutionError with the code of the failure
# check_document(did, doc)     -> each condition of the document check, one by one, and VALID
# verify_document(did, doc)    -> True only when every condition holds
# ethereum_address(doc)        -> the Ethereum address of the key the document authenticates with, or None
# did_key(public_key, type)    -> the did:key identifier of a raw public key
#
# Two kinds of identifier are resolved, both offline:
#   did:key   the method of the W3C CCG did:key specification. The identifier is the public key itself (multibase
#             base58btc over a multicodec header and the raw key), so the document is computed from the identifier and
#             no registry is read. Ed25519 and secp256k1 keys are supported. A secp256k1 key is the kind a wallet
#             holds, so its Ethereum address follows from the identifier.
#   local     the demonstration identifiers of the prototype (did:parent, did:hospital, did:patient, did:halah).
#             Their documents name the derived demonstration key of services/identity_service.py. That key can be
#             rebuilt from the source, so a local document shows the resolution step, not the secrecy of the key.
#             The local resolver keeps no registry: it computes the document of any well-formed identifier of these
#             four methods, so an identifier that nobody was given still resolves and is refused later, at the
#             credential step of Algorithm 5.1.
# Any other method is refused with methodNotSupported. A resolver for a further method is passed to verify_identity
# as its `resolver` argument, and its documents go through the same document check. The key agreement key that did:key can derive for Ed25519 is
# not produced, because nothing in the prototype encrypts to an identifier.
from functools import lru_cache
from eth_utils import is_checksum_address, keccak, to_checksum_address
from services import identity_service as ids

DID_CONTEXT = "https://www.w3.org/ns/did/v1"
MULTIKEY_CONTEXT = "https://w3id.org/security/multikey/v1"
RECOVERY_CONTEXT = "https://w3id.org/security/suites/secp256k1recovery-2020/v2"
RECOVERY_METHOD = "EcdsaSecp256k1RecoveryMethod2020"

# Multicodec table of did:key: code -> (key type, length of the raw public key in bytes).
ED25519, SECP256K1 = 0xed, 0xe7
KEY_TYPES = {ED25519: ("Ed25519", 32), SECP256K1: ("secp256k1", 33)}

# Methods answered by the local resolver (the demonstration identifiers).
LOCAL_METHODS = {"parent", "hospital", "patient", "halah"}


class DIDResolutionError(Exception):
    """Resolution failed. `code` follows the error names of the DID Resolution and did:key specifications."""

    def __init__(self, code, detail=""):
        super().__init__(f"{code}: {detail}" if detail else code)
        self.code = code


# ---------------------------------------------------------------------------
# Multibase (base58btc) and multicodec (unsigned varint)
# ---------------------------------------------------------------------------
_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def _b58encode(data):
    n, out = int.from_bytes(data, "big"), ""
    while n:
        n, r = divmod(n, 58)
        out = _B58[r] + out
    return "1" * (len(data) - len(data.lstrip(b"\0"))) + out


def _b58decode(text):
    n = 0
    for ch in text:
        i = _B58.find(ch)
        if i < 0:
            raise ValueError("character outside the base58btc alphabet")
        n = n * 58 + i
    return b"\0" * (len(text) - len(text.lstrip("1"))) + n.to_bytes((n.bit_length() + 7) // 8, "big")


def _varint(value):
    out = bytearray()
    while True:
        out.append((value & 0x7f) | (0x80 if value > 0x7f else 0))
        value >>= 7
        if not value:
            return bytes(out)


def _read_varint(data):
    value = 0
    for i, b in enumerate(data[:9]):
        value |= (b & 0x7f) << (7 * i)
        if not b & 0x80:
            if _varint(value) != data[:i + 1]:              # only the shortest encoding is accepted
                break
            return value, i + 1
    raise ValueError("malformed multicodec header")


# ---------------------------------------------------------------------------
# Public key checks
# ---------------------------------------------------------------------------
_P256K1 = 2 ** 256 - 2 ** 32 - 977
_P25519 = 2 ** 255 - 19
_D25519 = -121665 * pow(121666, -1, _P25519) % _P25519


def _secp256k1_point(raw):
    """Decompress a 33-byte secp256k1 public key to (x, y), or None when it is not a point of the curve."""
    if len(raw) != 33 or raw[0] not in (2, 3):
        return None
    x = int.from_bytes(raw[1:], "big")
    if not 0 < x < _P256K1:
        return None
    y2 = (pow(x, 3, _P256K1) + 7) % _P256K1
    y = pow(y2, (_P256K1 + 1) // 4, _P256K1)
    if y * y % _P256K1 != y2:
        return None
    return x, (y if y % 2 == raw[0] % 2 else _P256K1 - y)


def _is_ed25519_point(raw):
    """True when the 32 bytes encode a point of the Ed25519 curve (RFC 8032, section 5.1.3)."""
    if len(raw) != 32:
        return False
    y = int.from_bytes(raw, "little") & ((1 << 255) - 1)
    if y >= _P25519:
        return False
    x2 = (y * y - 1) * pow(_D25519 * y * y + 1, -1, _P25519) % _P25519
    if x2 == 0:
        return raw[31] >> 7 == 0
    x = pow(x2, (_P25519 + 3) // 8, _P25519)
    if (x * x - x2) % _P25519:
        x = x * pow(2, (_P25519 - 1) // 4, _P25519) % _P25519
    return (x * x - x2) % _P25519 == 0


def _decode_multikey(multibase):
    """Split a multibase public key into its multicodec code and raw key bytes, and check the key."""
    if not isinstance(multibase, str) or not multibase.startswith("z"):
        raise DIDResolutionError("invalidDid", "the key is not multibase base58btc")
    try:
        data = _b58decode(multibase[1:])
        code, used = _read_varint(data)
    except ValueError as e:
        raise DIDResolutionError("invalidDid", str(e))
    raw = data[used:]
    if code not in KEY_TYPES:
        raise DIDResolutionError("unsupportedPublicKeyType", f"multicodec 0x{code:x}")
    name, length = KEY_TYPES[code]
    if len(raw) != length:
        raise DIDResolutionError("invalidPublicKeyLength", f"{name} needs {length} bytes, found {len(raw)}")
    if not (_is_ed25519_point(raw) if code == ED25519 else _secp256k1_point(raw) is not None):
        raise DIDResolutionError("invalidPublicKey", f"not a point of the {name} curve")
    return code, raw


def did_key(public_key, key_type="secp256k1"):
    """The did:key identifier of a raw public key (32 bytes for Ed25519, 33 compressed bytes for secp256k1)."""
    code = {name: c for c, (name, _) in KEY_TYPES.items()}[key_type]
    did = "did:key:z" + _b58encode(_varint(code) + bytes(public_key))
    _decode_multikey(did.rsplit(":", 1)[1])
    return did


# ---------------------------------------------------------------------------
# Resolution (Algorithm 5.1, lines 1-4)
# ---------------------------------------------------------------------------
def _resolve_key(did):
    """Document creation algorithm of the did:key specification, with the Multikey verification method."""
    parts = did.split(":")
    if not (len(parts) == 3 or (len(parts) == 4 and parts[2] == "1")):
        raise DIDResolutionError("invalidDid", "did:key takes one multibase value, with version 1")
    multibase = parts[-1]
    _decode_multikey(multibase)
    method = {"id": f"{did}#{multibase}", "type": "Multikey", "controller": did, "publicKeyMultibase": multibase}
    return {"@context": [DID_CONTEXT, MULTIKEY_CONTEXT], "id": did, "verificationMethod": [method],
            "authentication": [method["id"]], "assertionMethod": [method["id"]],
            "capabilityInvocation": [method["id"]], "capabilityDelegation": [method["id"]]}


@lru_cache(maxsize=4096)
def _derived_address(did, key_tag):
    return ids.guardian_address(did)


def _local_address(did):
    """Address of the derived demonstration key of a local identifier (the issuer key for an issuer identifier)."""
    if did.startswith("did:halah:issuer:"):
        return ids.TRUSTED_ISSUERS.get(did) or ids._issuer_account(did).address
    return _derived_address(did, ids.DEMO_KEY_TAG)           # derived once for each identifier and key tag


def _resolve_local(did):
    method = {"id": f"{did}#key-1", "type": RECOVERY_METHOD, "controller": did,
              "blockchainAccountId": f"eip155:{ids.CHAIN_ID}:{_local_address(did)}"}
    return {"@context": [DID_CONTEXT, RECOVERY_CONTEXT], "id": did, "verificationMethod": [method],
            "authentication": [method["id"]], "assertionMethod": [method["id"]]}


def did_method(did):
    return did.split(":")[1] if ids.is_valid_did(did) else None


def resolve(did):
    """Resolve `did` to its DID document. Raises DIDResolutionError when the identifier is malformed, its method
    is not supported, or its key is not a valid public key."""
    method = did_method(did)
    if method is None:
        raise DIDResolutionError("invalidDid", "not a DID")
    if method == "key":
        return _resolve_key(did)
    if method in LOCAL_METHODS:
        return _resolve_local(did)
    raise DIDResolutionError("methodNotSupported", f"did:{method}")


# ---------------------------------------------------------------------------
# Document verification (Algorithm 5.1, lines 5-8)
# ---------------------------------------------------------------------------
def _account_address(method):
    """The address in a blockchainAccountId of the form eip155:<chain>:<address>, or None."""
    parts = str(method.get("blockchainAccountId", "")).split(":")
    if len(parts) == 3 and parts[0] == "eip155" and parts[1].isdigit() and is_checksum_address(parts[2]):
        return parts[2]
    return None


def _key_valid(did, method):
    """The key of a verification method is well formed and is the key the identifier commits to."""
    if method.get("type") == "Multikey":
        multibase = method.get("publicKeyMultibase")
        _decode_multikey(multibase)
        # A did:key identifier is its own key, so the document must carry exactly that key.
        return did_method(did) != "key" or (multibase == did.rsplit(":", 1)[1] and method.get("id") == f"{did}#{multibase}")
    if method.get("type") == RECOVERY_METHOD:
        address = _account_address(method)
        if address is None:
            return False
        if did_method(did) in LOCAL_METHODS:
            return (address == _local_address(did)
                    and method["blockchainAccountId"].split(":")[1] == str(ids.CHAIN_ID))
        return True
    return False


def check_document(did, document):
    """Each condition of the DID document check and VALID. Any malformed field fails the check."""
    r = {"Id_match": False, "Method_present": False, "Controller_match": False, "Key_valid": False,
         "Relationship_valid": False}
    try:
        methods = document.get("verificationMethod")
        r["Id_match"] = ids.is_valid_did(did) and document.get("id") == did
        r["Method_present"] = isinstance(methods, list) and len(methods) > 0 and all(isinstance(m, dict) for m in methods)
        if r["Method_present"]:
            known = [m.get("id") for m in methods]
            r["Controller_match"] = all(m.get("controller") == did and isinstance(m.get("id"), str)
                                        and m["id"].startswith(did + "#") for m in methods)
            r["Key_valid"] = all(_key_valid(did, m) for m in methods)
            # The document must say which key authenticates the subject and which key asserts for it.
            r["Relationship_valid"] = all(
                isinstance(document.get(rel), list) and len(document[rel]) > 0 and all(ref in known for ref in document[rel])
                for rel in ("authentication", "assertionMethod"))
    except Exception:
        r = {k: False for k in r}
    r["VALID"] = all(r.values())
    return r


def verify_document(did, document):
    return check_document(did, document)["VALID"]


def ethereum_address(document):
    """The Ethereum address of the secp256k1 key that the document authenticates with, or None when it has no such
    key (an Ed25519 key cannot sign an EIP-712 approval)."""
    try:
        methods = {m.get("id"): m for m in document.get("verificationMethod", [])}
        for ref in document.get("authentication", []):
            method = methods.get(ref, {})
            if method.get("type") == RECOVERY_METHOD:
                return _account_address(method)
            if method.get("type") == "Multikey":
                code, raw = _decode_multikey(method.get("publicKeyMultibase"))
                if code == SECP256K1:
                    x, y = _secp256k1_point(raw)
                    return to_checksum_address(keccak(x.to_bytes(32, "big") + y.to_bytes(32, "big"))[-20:])
    except Exception:
        return None
    return None
