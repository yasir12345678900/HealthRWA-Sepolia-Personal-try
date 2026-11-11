'''
Consent-Bound Data Vault for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11
'''
# The consent-bound encrypted copy of the Enforcement Module (thesis Sections 6.2.4 and 6.4.2).
#
# When a consent is issued, the Controller takes a copy of the record modules in the consent scope and seals each
# module on its own, under the key of that consent and module in the key store (services/key_store.py). The vault
# keeps the ciphertext and nothing else: no key and no plaintext. The key store keeps the keys and no ciphertext.
#
# - seal() accepts only modules of the consent scope, so no copy and no key exist for a module outside it.
# - open() is the decryption step of Algorithm 6.5. It asks the key store to decrypt the modules it is given and
#   no other module. The release service calls it after ALLOW and a verified proof.
# - delete() removes the copy of a consent. Revocation (Algorithm 6.4) calls it and destroys the keys.
# - export_copy() gives the ciphertext as a backup or a replica would hold it, and import_copy() puts such a copy
#   back. After the keys are destroyed a copy that was kept or put back cannot be opened.
#
# The source record of the treating institution is not in this vault and is not touched by it.
# A ciphertext shows how long its plaintext is, so a copy that remains still shows the size of the module.
import json
import os
import sqlite3
import threading
from datetime import datetime

from database import db
from services import key_store

FORMAT_VERSION = 1


class VaultError(Exception):
    """An operation of the vault failed."""


class CopyNotFoundError(VaultError):
    """The vault holds no sealed copy of this module for this consent."""


class ScopeError(VaultError):
    """A module that is not in the consent scope was given to the vault."""


def _encode(records):
    """Serialise the records of one module to bytes. A table (a pandas DataFrame) keeps its columns and rows,
    bytes are kept as they are, and any other value must be JSON data."""
    if hasattr(records, "to_json") and hasattr(records, "columns"):
        table = json.loads(records.to_json(orient="split", date_format="iso"))
        body = {"kind": "table", "columns": table["columns"], "rows": table["data"]}
    elif isinstance(records, (bytes, bytearray)):
        body = {"kind": "bytes", "hex": bytes(records).hex()}
    else:
        body = {"kind": "json", "value": records}
    try:
        return json.dumps(body, sort_keys=True).encode("utf-8")
    except (TypeError, ValueError) as error:
        raise VaultError(f"the records cannot be serialised: {error}") from None


def _decode(data):
    body = json.loads(data.decode("utf-8"))
    if body["kind"] == "table":
        import pandas as pd                    # imported here: only a table needs it
        return pd.DataFrame(body["rows"], columns=body["columns"])
    if body["kind"] == "bytes":
        return bytes.fromhex(body["hex"])
    return body["value"]


def _is_revoked(consent):
    return bool(getattr(consent, "revoked", False)) or getattr(consent, "state", None) == "REVOKED"


class DataVault:
    """The sealed copies, one per consent and module. path=None keeps the vault in memory for the life of the
    object. A path keeps it in an SQLite file of its own, apart from the file of the key store."""

    def __init__(self, keys=None, path=None):
        self.key_store = keys if keys is not None else key_store.default_store()
        self.path = path
        self._lock = threading.Lock()
        if path:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
        self._db = sqlite3.connect(path or ":memory:", check_same_thread=False)
        self._db.execute("PRAGMA secure_delete=ON")       # a deleted copy is overwritten with zeros in the file
        with self._db:
            self._db.execute("CREATE TABLE IF NOT EXISTS copies (consent_id TEXT NOT NULL, module TEXT NOT NULL, "
                             "body TEXT NOT NULL, PRIMARY KEY (consent_id, module))")

    # ---- sealing ------------------------------------------------------------------------------
    def seal(self, consent, records, now=None):
        """Seal the consent-bound copy: `records` maps a module of the consent scope to its records. Every module
        is encrypted on its own under the key of this consent and module, which is created when it does not
        exist. A module outside the consent scope is refused and nothing is sealed. No copy is sealed for a
        revoked consent. Returns the modules sealed and their key references."""
        if _is_revoked(consent):
            raise VaultError("no copy is sealed for a revoked consent")
        if not isinstance(records, dict):
            raise VaultError("the records must map a module to its records")
        outside = [m for m in records if m not in (consent.scope or [])]
        if outside:
            raise ScopeError(f"not in the consent scope: {', '.join(map(str, outside))}")
        sealed_at = (now or datetime.now()).isoformat()
        payloads = {module: _encode(content) for module, content in records.items()}   # before any key is made
        blobs = {}
        for module, payload in payloads.items():
            self.key_store.create_key(consent.consent_id, module)
            sealed = self.key_store.encrypt(consent.consent_id, module, payload)
            blobs[module] = {"version": FORMAT_VERSION, "algorithm": key_store.ALGORITHM, "consent_id": consent.consent_id,
                             "module": module, "key_id": sealed["key_id"], "nonce": sealed["nonce"].hex(),
                             "ciphertext": sealed["ciphertext"].hex(), "sealed_at": sealed_at}
        self._put(blobs.values())
        return {"consent_id": consent.consent_id, "modules": list(blobs), "sealed_at": sealed_at,
                "key_ids": {m: b["key_id"] for m, b in blobs.items()}}

    def seal_from_source(self, consent, source, now=None):
        """Seal the copy of the whole consent scope from the source record. `source` is a callable
        (patient_did, scope) -> {module: records}, for example SyntheaRepository.query_patient. A module that the
        source returns outside the consent scope is refused by seal()."""
        return self.seal(consent, source(consent.patient_did, list(consent.scope or [])), now=now)

    def _put(self, blobs):
        with self._lock, self._db:
            for blob in blobs:
                self._db.execute("INSERT OR REPLACE INTO copies (consent_id, module, body) VALUES (?,?,?)",
                                 (blob["consent_id"], blob["module"], json.dumps(blob, sort_keys=True)))

    # ---- reading ------------------------------------------------------------------------------
    def modules(self, consent_id):
        """The modules of which the vault holds a sealed copy for the consent."""
        with self._lock:
            return [r[0] for r in self._db.execute("SELECT module FROM copies WHERE consent_id=? ORDER BY module", (consent_id,))]

    def has_copy(self, consent_id, module=None):
        held = self.modules(consent_id)
        return bool(held) if module is None else module in held

    def export_copy(self, consent_id):
        """The sealed copy as it is stored, module -> blob: ciphertext, nonce and key reference, never a key.
        This is what a backup or a replica of the vault holds."""
        with self._lock:
            rows = self._db.execute("SELECT module, body FROM copies WHERE consent_id=? ORDER BY module", (consent_id,)).fetchall()
        return {module: json.loads(body) for module, body in rows}

    def import_copy(self, blobs):
        """Put sealed blobs back into the vault, as a restore from a backup does. Nothing is decrypted."""
        blobs = list(blobs.values()) if isinstance(blobs, dict) else list(blobs)
        for blob in blobs:
            if not all(isinstance(blob.get(k), str) and blob.get(k) for k in ("consent_id", "module", "key_id", "nonce", "ciphertext")):
                raise VaultError("not a sealed blob of this vault")
        self._put(blobs)
        return [(b["consent_id"], b["module"]) for b in blobs]

    def open(self, consent_id, modules):
        """Algorithm 6.5, the decryption step: decrypt the given modules of the consent and no other module, inside
        the Controller. The key store does the decryption and the keys stay in it. Raises CopyNotFoundError when a
        module has no sealed copy, and the errors of the key store when the keys were destroyed or the copy does
        not open. Either all the modules are returned or none."""
        modules = list(modules)
        with self._lock:
            rows = dict(self._db.execute("SELECT module, body FROM copies WHERE consent_id=?", (consent_id,)).fetchall())
        missing = [m for m in modules if m not in rows]
        if missing:
            if self.key_store.is_destroyed(consent_id):
                raise key_store.KeyDestroyedError(f"the keys of consent {consent_id} were destroyed")
            raise CopyNotFoundError(f"no sealed copy for consent {consent_id}: {', '.join(map(str, missing))}")
        opened = {}
        for module in modules:
            blob = json.loads(rows[module])
            plaintext = self.key_store.decrypt(consent_id, module, bytes.fromhex(blob["nonce"]), bytes.fromhex(blob["ciphertext"]))
            opened[module] = _decode(plaintext)
        return opened

    # ---- deleting -----------------------------------------------------------------------------
    def delete(self, consent_id, now=None):
        """Delete the sealed copy of a consent (Algorithm 6.4). Returns the evidence: the modules deleted by this
        call and the number of copies that remain, which is zero."""
        with self._lock:
            held = [r[0] for r in self._db.execute("SELECT module FROM copies WHERE consent_id=? ORDER BY module", (consent_id,))]
            with self._db:
                self._db.execute("DELETE FROM copies WHERE consent_id=?", (consent_id,))
            remaining = self._db.execute("SELECT COUNT(*) FROM copies WHERE consent_id=?", (consent_id,)).fetchone()[0]
        return {"consent_id": consent_id, "modules_deleted": held, "copies_remaining": remaining,
                "deleted_at": (now or datetime.now()).isoformat()}


# ---------------------------------------------------------------------------
# The vault of the running Controller
# ---------------------------------------------------------------------------
_default = None


def default_path():
    """Where the vault of the Controller is kept: HALAH_VAULT_PATH when it is set (":memory:" keeps it in memory),
    otherwise a file of its own in a folder of its own beside the HALAH database."""
    path = os.environ.get("HALAH_VAULT_PATH")
    if path:
        return None if path == ":memory:" else path
    return os.path.join(os.path.dirname(db.db_path()) or ".", "vault", "halah_vault.db")


def default_vault():
    global _default
    if _default is None:
        _default = DataVault(key_store.default_store(), default_path())
    return _default
