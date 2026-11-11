'''
Consent commitment and request tag for HALAH
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-11

The commitment of a consent is the only consent data that goes on chain (Chapter 7, Section 7.2.3):

    c = Poseidon(patient, guardiansDigest, requester, role, purpose, context, scopeMask, notBefore, expiry, blinding)

The ten values are the opening of the commitment. The opening stays off chain with the consent record.
The blinding value is a fresh random number, so the commitment is hiding: without it a commitment over
fields of low entropy (a purpose, a context, a small scope) could be opened by trying every combination.

The request tag binds one access to its requester without naming the requester (Section 7.2.2):

    tag = Poseidon(requester, nonce)

with a fresh random nonce for every request, so two requests by the same clinician cannot be linked.
The nonce is recorded with the requester in the audit ledger, where an auditor can open the tag.

Field and hash: the BN254 scalar field and Poseidon with the circomlib parameters. The parameters are
generated here by the reference method (Grain LFSR), and they are the ones of circomlib 2.0.5 and
circomlibjs 0.1.7, so this module, the circuit zk/halah_decision.circom, zk/poseidon_cli.js and the
Poseidon contract compute the same values. The test file compares them.

to_field(text)                          -> a DID or other string as a field element
field_element(value)                    -> an integer or a decimal or 0x string as a checked field element
poseidon(inputs)                        -> Poseidon hash of 1 to 16 field elements
guardians_digest(guardian_dids, k)      -> digest of the guardian set and its threshold
compute_commitment(consent)             -> (commitment as 0x hex, opening as a dict of decimal strings)
commit_consent(consent)                 -> the same, stored in consent.commitment and consent.commitment_opening
open_commitment(opening)                -> the commitment that an opening hashes to
verify_opening(commitment, opening)     -> True only if the opening hashes to the commitment
request_tag(requester_did, nonce=None)  -> (tag, nonce)
open_tag(tag, requester_did, nonce)     -> True only if the tag opens to this requester
'''
import math
import secrets
from datetime import datetime

from eth_utils import keccak

# Order of the BN254 scalar field. Every commitment, tag and tree node is an element of this field.
FIELD = 21888242871839275222246405745257275088548364400416034343698204186575808495617

# The opening of the commitment, in the order the hash takes it.
OPENING_FIELDS = ("patient", "guardiansDigest", "requester", "role", "purpose", "context",
                  "scopeMask", "notBefore", "expiry", "blinding")

# Codes of the policy terms inside the commitment.
ROLE_CODES = {"doctor": 1}
PURPOSE_CODES = {"Treatment": 1, "Research": 2, "Emergency": 3}
# Record modules in the fixed order of the scope mask: Observation is bit 0, Procedure is bit 3.
SCOPE_MODULES = ("Observation", "Medication", "Condition", "Procedure")
# The role that a consent of this prototype permits (the requester of a consent is a doctor).
CONSENT_ROLE = "doctor"

RANDOM_BITS = 248            # size of a blinding value and of a nonce
TIME_BITS = 64               # the circuit compares the window and the time as 64-bit numbers


# ---- Poseidon ----------------------------------------------------------------------------------

_FULL_ROUNDS = 8
# Partial rounds for the state width t = 2 .. 17 (1 to 16 inputs), as circomlib fixes them.
_PARTIAL_ROUNDS = (56, 57, 56, 60, 60, 63, 64, 63, 60, 66, 60, 65, 70, 60, 64, 68)
_PARAMETERS = {}             # state width -> (round constants, MDS matrix), generated once


def _grain_bits(width, partial_rounds):
    '''Bit generator of the Poseidon reference parameter script: an 80-bit Grain LFSR seeded with
    the field type, the S-box, the field size, the state width and the round numbers.'''
    seed = (format(1, "02b") + format(0, "04b") + format(254, "012b") + format(width, "012b")
            + format(_FULL_ROUNDS, "010b") + format(partial_rounds, "010b") + "1" * 30)
    state = [int(bit) for bit in seed]

    def step():
        bit = state[62] ^ state[51] ^ state[38] ^ state[23] ^ state[13] ^ state[0]
        state.pop(0)
        state.append(bit)
        return bit

    for _ in range(160):                 # the first 160 bits are discarded
        step()

    def next_bit():
        # bits are taken in pairs: the second bit is kept only when the first one is 1
        while True:
            if step() == 1:
                return step()
            step()

    def random_number(bits=254):
        value = 0
        for _ in range(bits):
            value = (value << 1) | next_bit()
        return value

    return random_number


def _parameters(width):
    '''Round constants and MDS matrix for a state of `width` elements, as the reference script
    generates them for BN254 with the x^5 S-box. They equal the constants of circomlib.'''
    if width not in _PARAMETERS:
        partial_rounds = _PARTIAL_ROUNDS[width - 2]
        random_number = _grain_bits(width, partial_rounds)
        constants = []
        while len(constants) < (_FULL_ROUNDS + partial_rounds) * width:
            value = random_number()
            if value < FIELD:            # a value outside the field is drawn again
                constants.append(value)
        while True:                      # Cauchy matrix over 2 * width distinct field elements
            points = [random_number() % FIELD for _ in range(2 * width)]
            if len(set(points)) == 2 * width:
                break
        xs, ys = points[:width], points[width:]
        matrix = [[pow(x + y, FIELD - 2, FIELD) for y in ys] for x in xs]
        _PARAMETERS[width] = (constants, matrix)
    return _PARAMETERS[width]


def poseidon(inputs):
    '''Poseidon hash of 1 to 16 field elements (the permutation of circomlib, first state element out).'''
    values = [field_element(value) for value in inputs]
    if not 1 <= len(values) <= len(_PARTIAL_ROUNDS):
        raise ValueError("Poseidon takes 1 to 16 inputs")
    width = len(values) + 1
    partial_rounds = _PARTIAL_ROUNDS[width - 2]
    constants, matrix = _parameters(width)
    state = [0] + values
    half = _FULL_ROUNDS // 2
    for r in range(_FULL_ROUNDS + partial_rounds):
        state = [(s + constants[r * width + i]) % FIELD for i, s in enumerate(state)]
        if r < half or r >= half + partial_rounds:
            state = [pow(s, 5, FIELD) for s in state]            # full round: every element
        else:
            state[0] = pow(state[0], 5, FIELD)                   # partial round: the first element only
        state = [sum(m * s for m, s in zip(row, state)) % FIELD for row in matrix]
    return state[0]


def field_element(value):
    '''A field element as an integer. Accepts an integer or a decimal or 0x string, and refuses a
    value outside the field, so that every value has one representation only.'''
    if isinstance(value, (bool, float)) or value is None:
        raise ValueError("not a field element: %r" % (value,))
    if isinstance(value, str):
        text = value.strip()
        value = int(text, 16) if text.lower().startswith("0x") else int(text)
    value = int(value)
    if not 0 <= value < FIELD:
        raise ValueError("value is outside the field")
    return value


# ---- field encoding ------------------------------------------------------------------------------

def to_field(text):
    '''A DID or other string as a field element: keccak256 of its UTF-8 bytes with the top 8 bits
    cleared, which leaves a 248-bit value below the field order.'''
    if not isinstance(text, str) or not text:
        raise ValueError("a non-empty string is required")
    return int.from_bytes(keccak(text=text), "big") & ((1 << 248) - 1)


def role_code(role):
    '''Code of a requester role: 1 for doctor. An integer is taken as a code already.'''
    return _code(role, ROLE_CODES, "role")


def purpose_code(purpose):
    '''Code of a purpose: 1 Treatment, 2 Research, 3 Emergency. An integer is taken as a code already.'''
    return _code(purpose, PURPOSE_CODES, "purpose")


def _code(value, table, name):
    if isinstance(value, int) and not isinstance(value, bool):
        if not 0 <= value < FIELD:
            raise ValueError("%s code is outside the field" % name)
        return value
    if value not in table:
        raise ValueError("unknown %s: %r" % (name, value))
    return table[value]


def context_code(context):
    '''The request context as a number: the two ASCII bytes of its code ("AU" is 0x4155).
    A consent without a context (an empty string) has the code 0.'''
    if isinstance(context, int) and not isinstance(context, bool):
        if not 0 <= context < (1 << 16):
            raise ValueError("context code is outside two bytes")
        return context
    if context is None or context == "":
        return 0
    if not isinstance(context, str) or len(context) != 2 or not context.isascii():
        raise ValueError("a context code is two ASCII characters: %r" % (context,))
    return (ord(context[0]) << 8) | ord(context[1])


def scope_mask(scope):
    '''Bit mask of a list of record modules in the order of SCOPE_MODULES. An integer is taken as a
    mask already. A module that the mask has no bit for cannot be committed and is refused.'''
    if isinstance(scope, int) and not isinstance(scope, bool):
        if not 0 <= scope < (1 << len(SCOPE_MODULES)):
            raise ValueError("scope mask has a bit without a module")
        return scope
    mask = 0
    for module in (scope or []):
        if module not in SCOPE_MODULES:
            raise ValueError("unknown record module: %r" % (module,))
        mask |= 1 << SCOPE_MODULES.index(module)
    return mask


def scope_modules(mask):
    '''The record modules of a scope mask, in the order of SCOPE_MODULES.'''
    mask = scope_mask(int(mask))
    return [module for bit, module in enumerate(SCOPE_MODULES) if mask >> bit & 1]


def unix_seconds(value, round_up=False):
    '''A time as Unix seconds. Accepts seconds, a datetime or an ISO date-time string. A time
    without a zone is local time, as in the rest of the prototype. A fraction of a second is
    cut off, or rounded up with round_up, so that a window never grows by the conversion.'''
    if isinstance(value, bool) or value is None:
        raise ValueError("not a time: %r" % (value,))
    if isinstance(value, str):
        value = datetime.fromisoformat(value)
    if isinstance(value, datetime):
        value = value.timestamp()
    seconds = math.ceil(value) if round_up else math.floor(value)
    if not 0 <= seconds < (1 << TIME_BITS):
        raise ValueError("time is outside the 64-bit range")
    return seconds


def guardians_digest(guardian_dids, threshold):
    '''Digest of the guardian set G and its threshold k. The guardians' field elements are sorted,
    folded from the left (acc = g_1, then acc = Poseidon(acc, g_i)) and closed with the threshold:
    Poseidon(acc, k). The order in which the guardians were entered does not change the digest.'''
    elements = sorted(to_field(did) for did in (guardian_dids or []))
    if not elements:
        raise ValueError("a consent needs at least one guardian")
    if len(set(elements)) != len(elements):
        raise ValueError("a guardian is listed twice")
    threshold = int(threshold)
    if not 1 <= threshold <= len(elements):
        raise ValueError("the threshold must lie between 1 and the number of guardians")
    acc = elements[0]
    for element in elements[1:]:
        acc = poseidon([acc, element])
    return poseidon([acc, threshold])


def new_random():
    '''A fresh random 248-bit value, for a blinding value or a nonce.'''
    return secrets.randbits(RANDOM_BITS)


# ---- commitment ----------------------------------------------------------------------------------

def consent_opening(consent, blinding, role=CONSENT_ROLE):
    '''The ten committed values of a consent as integers, for the given blinding value.
    The window starts at the first whole second inside it and ends at the last one.'''
    opening = {
        "patient": to_field(consent.patient_did),
        "guardiansDigest": guardians_digest(consent.guardian_dids, consent.threshold),
        "requester": to_field(consent.requester_did),
        "role": role_code(role),
        "purpose": purpose_code(consent.purpose),
        "context": context_code(getattr(consent, "jurisdiction", "")),
        "scopeMask": scope_mask(consent.scope),
        "notBefore": unix_seconds(consent.start_date, round_up=True),
        "expiry": unix_seconds(consent.expiry_date),
        "blinding": _random_value(blinding, "blinding value"),
    }
    return opening


def _random_value(value, name):
    value = field_element(value)
    if value >= (1 << RANDOM_BITS):
        raise ValueError("the %s is longer than %d bits" % (name, RANDOM_BITS))
    return value


def open_commitment(opening):
    '''The commitment that an opening hashes to, as an integer.'''
    return poseidon([field_element(opening[name]) for name in OPENING_FIELDS])


def commitment_hex(value):
    '''A commitment as the 0x string of 32 bytes that the consent record and the contract client take.'''
    return "0x" + format(field_element(value), "064x")


def compute_commitment(consent, blinding=None, role=CONSENT_ROLE):
    '''Commit to a consent. Returns (commitment, opening): the commitment as a 0x string and the
    opening as a dict of decimal strings in the order of OPENING_FIELDS. A fresh blinding value is
    drawn unless one is given (the tests give one to stay deterministic). The consent is not changed.'''
    opening = consent_opening(consent, new_random() if blinding is None else blinding, role=role)
    commitment = commitment_hex(open_commitment(opening))
    return commitment, {name: str(opening[name]) for name in OPENING_FIELDS}


def commit_consent(consent, blinding=None, role=CONSENT_ROLE):
    '''Commit to a consent and keep the result with it: consent.commitment (the value that the
    guardians sign and the token carries) and consent.commitment_opening (off chain only).'''
    consent.commitment, consent.commitment_opening = compute_commitment(consent, blinding=blinding, role=role)
    return consent.commitment, consent.commitment_opening


def verify_opening(commitment, opening):
    '''True only if the opening is complete and hashes to the commitment.'''
    try:
        return open_commitment(opening) == field_element(commitment)
    except (KeyError, TypeError, ValueError):
        return False


def opening_matches_consent(consent, opening):
    '''True only if the consent record still holds the values that were committed, so that the
    decision on the record and the proof over the commitment speak about the same consent.
    The role is not a field of the record and is taken from the opening.'''
    try:
        current = consent_opening(consent, opening["blinding"], role=field_element(opening["role"]))
        return all(current[name] == field_element(opening[name]) for name in OPENING_FIELDS)
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


# ---- request tag ---------------------------------------------------------------------------------

def request_tag(requester_did, nonce=None):
    '''The tag of one request: Poseidon(requester, nonce). Returns (tag, nonce) as integers.
    A fresh nonce is drawn unless one is given. Record the nonce with the requester in the audit
    ledger and nowhere else: whoever holds it can open the tag.'''
    nonce = new_random() if nonce is None else _random_value(nonce, "nonce")
    return poseidon([to_field(requester_did), nonce]), nonce


def open_tag(tag, requester_did, nonce):
    '''True only if the tag opens to this requester with this nonce (the auditor's check).'''
    try:
        return request_tag(requester_did, nonce)[0] == field_element(tag)
    except (TypeError, ValueError):
        return False
