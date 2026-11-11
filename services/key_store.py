'''
Key Store for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11
'''
# The key store of the Enforcement Module (thesis Sections 6.2.4, 6.2.5 and 6.4.2).
#
# It holds one AES-256-GCM key for each pair of consent and record module, so the decryption step can open only
# the modules it is asked for. The keys are held apart from the encrypted copy: the copy is in the vault
# (services/data_vault.py), the keys are here, in a store of their own with a file of its own.
#
# A key never leaves this store. There is no operation that returns one. The vault and the release step ask the
# store to encrypt or to decrypt, and they receive ciphertext or plaintext and never a key. A requester receives
# decrypted modules and never a key either, and this is what makes the revocation claim true: after destroy()
# nobody holds a key that opens a copy of the ciphertext that remains in a backup or a replica.
#
# destroy(consent_id) is the key step of crypto-shredding (Algorithm 6.4). It deletes every key of the consent,
# leaves a record of the destruction that holds the key references and no key, and refuses to create a key for
# that consent again.
#
# What this prototype does not give:
# - The key store is a service of the Controller and runs in its process. While it encrypts or decrypts, the key
#   and the plaintext are in the memory of that process, and Python has no way to wipe them. An operator who can
#   read the store before the destruction can read the keys. A deployment would hold the keys in a hardware
#   security module or a key management service (thesis Section 9.4).
# - The file of the store is opened with secure_delete, so the bytes of a destroyed key are overwritten with
#   zeros in the file, and the rollback journal is kept in memory, so no old page is written beside it. The price
#   of the journal in memory is that a crash in the middle of a write can damage the file. The store cannot
#   control what the storage medium keeps below the file system, and a backup of the key store file made before
#   the destruction would defeat the destruction. The key store must not be backed up with the vault.
# - The keys are stored as they are, protected by the permissions of the file (owner only) and by nothing else.
#   They are not wrapped under a master key.
import json
import os
import sqlite3
import threading
import uuid
from datetime import datetime

from database import db

ALGORITHM = "AES-256-GCM"
KEY_BYTES = 32            # AES-256
NONCE_BYTES = 12          # the 96-bit nonce of GCM, fresh and random for every encryption
TAG_BYTES = 16            # the GCM tag, the last 16 bytes of the ciphertext


class KeyStoreError(Exception):
    """An operation of the key store failed."""


class KeyNotFoundError(KeyStoreError):
    """The store holds no key for this consent and module."""


class KeyDestroyedError(KeyStoreError):
    """The keys of this consent were destroyed (the consent was revoked by crypto-shredding)."""


class DecryptionError(KeyStoreError):
    """The ciphertext does not open under the key of this consent and module."""


# ---------------------------------------------------------------------------
# The cipher
# ---------------------------------------------------------------------------
# AES-256-GCM as two functions, seal(key, nonce, data, aad) and unseal(key, nonce, data, aad), both over ciphertext
# with the 16-byte tag at its end. The cryptography package is the library of the key store. Where it cannot be
# loaded (an installation whose binary bindings were built for another Python), the same standard algorithm is taken
# from pycryptodome, which is installed with web3. Both give the same ciphertext for the same key, nonce and data,
# so a copy sealed with one opens with the other. CIPHER_BACKEND names the library in use.
def _cryptography_cipher():
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    def seal(key, nonce, data, aad):
        return AESGCM(key).encrypt(nonce, data, aad)

    def unseal(key, nonce, data, aad):
        try:
            return AESGCM(key).decrypt(nonce, data, aad)
        except InvalidTag:
            raise DecryptionError("the authentication tag does not verify") from None

    return seal, unseal


def _pycryptodome_cipher():
    from Crypto.Cipher import AES

    def seal(key, nonce, data, aad):
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_BYTES)
        cipher.update(aad)
        body, tag = cipher.encrypt_and_digest(data)
        return body + tag

    def unseal(key, nonce, data, aad):
        if len(data) < TAG_BYTES:
            raise DecryptionError("the ciphertext is shorter than its tag")
        cipher = AES.new(key, AES.MODE_GCM, nonce=nonce, mac_len=TAG_BYTES)
        cipher.update(aad)
        try:
            return cipher.decrypt_and_verify(data[:-TAG_BYTES], data[-TAG_BYTES:])
        except ValueError:
            raise DecryptionError("the authentication tag does not verify") from None

    return seal, unseal


_LIBRARIES = (("cryptography", _cryptography_cipher), ("pycryptodome", _pycryptodome_cipher))   # in order of preference
_loaded = {}


def _cipher(name):
    """The pair (seal, unseal) of one library, or None when the library cannot be loaded or fails a round trip.
    Each library is tried once."""
    if name not in _loaded:
        _loaded[name] = None
        try:
            seal, unseal = dict(_LIBRARIES)[name]()
            probe = bytes(KEY_BYTES), bytes(NONCE_BYTES)
            if unseal(*probe, seal(*probe, b"probe", b"aad"), b"aad") == b"probe":
                _loaded[name] = (seal, unseal)
        except BaseException as error:         # a broken binary binding does not raise an ordinary Exception
            if isinstance(error, (KeyboardInterrupt, SystemExit)):
                raise
    return _loaded[name]


def _load_cipher():
    """The first library of _LIBRARIES that loads: its name, seal and unseal."""
    for name, _ in _LIBRARIES:
        if _cipher(name) is not None:
            return (name,) + _cipher(name)
    raise ImportError("the key store needs AES-256-GCM from the cryptography package, which could not be loaded")


CIPHER_BACKEND, _seal, _unseal = _load_cipher()


def _name(value, what):
    if not isinstance(value, str) or not value or "\x00" in value:
        raise KeyStoreError(f"the {what} must be a non-empty string")
    return value


def _associated_data(consent_id, module, key_id):
    # The ciphertext is bound to its consent, its module and its key reference. A copy that is moved to another
    # consent or another module does not open, whatever key is tried.
    return b"\x00".join([b"HALAH-KEYSTORE-v1", consent_id.encode(), module.encode(), key_id.encode()])


class KeyStore:
    """One AES-256-GCM key per consent and record module. path=None keeps the store in memory for the life of the
    object. A path keeps it in an SQLite file of its own."""

    def __init__(self, path=None):
        self.path = path
        self._lock = threading.Lock()
        if path:
            folder = os.path.dirname(path)
            if folder:
                os.makedirs(folder, exist_ok=True)
        self._db = sqlite3.connect(path or ":memory:", check_same_thread=False)
        self._db.execute("PRAGMA secure_delete=ON")       # deleted key bytes are overwritten with zeros
        self._db.execute("PRAGMA journal_mode=MEMORY")    # no old page with a key is written to a journal file
        with self._db:
            self._db.execute("CREATE TABLE IF NOT EXISTS keys (consent_id TEXT NOT NULL, module TEXT NOT NULL, "
                             "key_id TEXT NOT NULL, key BLOB NOT NULL, created_at TEXT NOT NULL, "
                             "PRIMARY KEY (consent_id, module))")
            self._db.execute("CREATE TABLE IF NOT EXISTS destroyed (consent_id TEXT PRIMARY KEY, "
                             "destroyed_at TEXT NOT NULL, body TEXT NOT NULL)")
        if path:
            try:
                os.chmod(path, 0o600)          # only the account of the Controller reads the file of the keys
            except OSError:
                pass                           # a file system without these permissions keeps its own

    # ---- reading what the store holds, never a key ------------------------------------------
    def _row(self, consent_id, module):
        row = self._db.execute("SELECT key_id, key FROM keys WHERE consent_id=? AND module=?",
                               (consent_id, module)).fetchone()
        if row is None:
            if self._destroyed(consent_id) is not None:
                raise KeyDestroyedError(f"the keys of consent {consent_id} were destroyed")
            raise KeyNotFoundError(f"no key for consent {consent_id} and module {module}")
        return row[0], bytes(row[1])

    def _destroyed(self, consent_id):
        row = self._db.execute("SELECT destroyed_at, body FROM destroyed WHERE consent_id=?", (consent_id,)).fetchone()
        if row is None:
            return None
        return dict(json.loads(row[1]), consent_id=consent_id, destroyed_at=row[0])

    def has_key(self, consent_id, module=None):
        """True when the store holds a key for the consent and module, or any key of the consent."""
        with self._lock:
            if module is None:
                query, args = "SELECT 1 FROM keys WHERE consent_id=? LIMIT 1", (consent_id,)
            else:
                query, args = "SELECT 1 FROM keys WHERE consent_id=? AND module=?", (consent_id, module)
            return self._db.execute(query, args).fetchone() is not None

    def key_ids(self, consent_id):
        """The key references of a consent, module -> key identifier. A reference names a key and is not a key."""
        with self._lock:
            return {m: k for m, k in self._db.execute("SELECT module, key_id FROM keys WHERE consent_id=? ORDER BY module",
                                                      (consent_id,))}

    def is_destroyed(self, consent_id):
        with self._lock:
            return self._destroyed(consent_id) is not None

    def destruction_record(self, consent_id):
        """The record that destroy() left for a consent: time, modules and key references. None before it."""
        with self._lock:
            return self._destroyed(consent_id)

    # ---- the three operations on keys ---------------------------------------------------------
    def create_key(self, consent_id, module, now=None):
        """Create the key of a consent and module and return its reference. The pair has one key: a second call
        returns the reference of the key that exists. No key is created for a consent whose keys were destroyed."""
        _name(consent_id, "consent identifier"), _name(module, "module")
        with self._lock:
            if self._destroyed(consent_id) is not None:
                raise KeyDestroyedError(f"the keys of consent {consent_id} were destroyed, no new key is created")
            row = self._db.execute("SELECT key_id FROM keys WHERE consent_id=? AND module=?", (consent_id, module)).fetchone()
            if row is not None:
                return row[0]
            key_id = str(uuid.uuid4())
            with self._db:
                self._db.execute("INSERT INTO keys (consent_id, module, key_id, key, created_at) VALUES (?,?,?,?,?)",
                                 (consent_id, module, key_id, os.urandom(KEY_BYTES), (now or datetime.now()).isoformat()))
            return key_id

    def encrypt(self, consent_id, module, plaintext):
        """Encrypt `plaintext` (bytes) under the key of the consent and module. Returns the key reference, the
        nonce and the ciphertext with its tag. The key stays in the store."""
        if not isinstance(plaintext, (bytes, bytearray)):
            raise KeyStoreError("the plaintext must be bytes")
        with self._lock:
            key_id, key = self._row(_name(consent_id, "consent identifier"), _name(module, "module"))
            nonce = os.urandom(NONCE_BYTES)
            ciphertext = _seal(key, nonce, bytes(plaintext), _associated_data(consent_id, module, key_id))
        return {"key_id": key_id, "nonce": nonce, "ciphertext": ciphertext}

    def decrypt(self, consent_id, module, nonce, ciphertext):
        """Decrypt a ciphertext of the consent and module and return the plaintext. Raises KeyDestroyedError after
        destroy(), KeyNotFoundError when there never was a key, and DecryptionError when the ciphertext was sealed
        for another consent, module or key, or was changed."""
        with self._lock:
            key_id, key = self._row(_name(consent_id, "consent identifier"), _name(module, "module"))
            return _unseal(key, bytes(nonce), bytes(ciphertext), _associated_data(consent_id, module, key_id))

    def destroy(self, consent_id, now=None):
        """Destroy every key of the consent (Algorithm 6.4). Returns the evidence: the time, the modules, the key
        references and the number of keys destroyed by this call. The call can be repeated: the second time there
        is nothing left to destroy and the first record is returned."""
        _name(consent_id, "consent identifier")
        with self._lock:
            earlier = self._destroyed(consent_id)
            rows = self._db.execute("SELECT module, key_id FROM keys WHERE consent_id=? ORDER BY module", (consent_id,)).fetchall()
            record = {"modules": list((earlier or {}).get("modules", [])), "key_ids": list((earlier or {}).get("key_ids", []))}
            for module, key_id in rows:
                record["modules"].append(module)
                record["key_ids"].append(key_id)
            destroyed_at = (earlier or {}).get("destroyed_at") or (now or datetime.now()).isoformat()
            with self._db:
                self._db.execute("DELETE FROM keys WHERE consent_id=?", (consent_id,))
                self._db.execute("INSERT OR REPLACE INTO destroyed (consent_id, destroyed_at, body) VALUES (?,?,?)",
                                 (consent_id, destroyed_at, json.dumps(record)))
            remaining = self._db.execute("SELECT COUNT(*) FROM keys WHERE consent_id=?", (consent_id,)).fetchone()[0]
        return {"consent_id": consent_id, "destroyed_at": destroyed_at, "modules": record["modules"],
                "key_ids": record["key_ids"], "keys_destroyed": len(rows), "keys_remaining": remaining,
                "algorithm": ALGORITHM}


# ---------------------------------------------------------------------------
# The key store of the running Controller
# ---------------------------------------------------------------------------
_default = None


def default_path():
    """Where the key store of the Controller is kept: HALAH_KEYSTORE_PATH when it is set (":memory:" keeps it in
    memory), otherwise a file of its own in a folder of its own beside the HALAH database."""
    path = os.environ.get("HALAH_KEYSTORE_PATH")
    if path:
        return None if path == ":memory:" else path
    return os.path.join(os.path.dirname(db.db_path()) or ".", "keystore", "halah_keys.db")


def default_store():
    global _default
    if _default is None:
        _default = KeyStore(default_path())
    return _default


def destroy(consent_id, now=None):
    """Destroy every key of the consent in the key store of the Controller."""
    return default_store().destroy(consent_id, now=now)
