"""The credential of the requester is judged at the time of the chain (Algorithm 5.1 inside the request path), with
Streamlit's test runner (no browser) and with the function the clinician screen calls.

With a chain configured the time of every check is the block timestamp. The chain of these tests stands after the end
of the validity of the demonstration credentials (31 December 2030), while the server clock stands before it. The
credential of the named clinician is then outside its validity time: the clinician screen says so, VI fails, the
request is refused without a deny code, no VALID identity verification is recorded and nothing is sent to the chain.
A check made at the server clock would accept the credential.

The chain is an in-memory EVM with the real bytecode of blockchain/abi (no network, no Sepolia). The fixtures and the
helpers are those of tests/test_refusals_on_screens.py."""
from datetime import datetime, timedelta

from test_refusals_on_screens import (app_test, base, chain, onchain,                       # fixtures
                                      CLINICIAN, RECORDED, _anchored, _click, _clinician_screen, _code_fields,
                                      _consent, _failed, _rows, _scope, _source)

AFTER_THE_CREDENTIALS = datetime(2031, 1, 15, 12, 0, 0)
END_OF_THE_CREDENTIALS = datetime(2030, 12, 31, 23, 59, 59)          # validUntil of every demonstration credential
OUTSIDE = "Time_valid: the credential is outside its validity time"


def _chain_in_2031(onchain):
    """A consent that is ACTIVE on 15 January 2031, anchored, and the chain moved to that day."""
    c = _consent(expiry=AFTER_THE_CREDENTIALS + timedelta(days=30))
    _anchored(c)
    onchain.tester.time_travel(int(AFTER_THE_CREDENTIALS.timestamp()))
    block = onchain.w3.eth.get_block("latest")
    assert datetime.fromtimestamp(block.timestamp) >= END_OF_THE_CREDENTIALS > datetime.now()
    return c, block


def test_clinician_screen_judges_the_credential_of_the_requester_at_the_block_time(app_test, onchain):
    from services import identity_service as ids
    c, block = _chain_in_2031(onchain)
    assert ids.verify_identity(CLINICIAN, role="doctor").valid         # at the server clock the credential is valid
    at = _clinician_screen(app_test, c.consent_id)
    assert any(w.value == f"No valid clinician credential for this DID ({OUTSIDE})." for w in at.warning)
    assert not any(x.value.startswith("Clinician credential verified") for x in at.caption)
    assert _failed(_scope(at, ["Observation"])) == ["VI"]              # the window and the state hold at that time
    assert any(e.value == "Identity and authority check (VI) failed: this requester cannot access this consent." for e in at.error)
    blocks = onchain.w3.eth.block_number
    at = _click(at, "Request Data Access")
    assert any(e.value == "Access Denied. Failed checks: VI." + RECORDED for e in at.error) and not at.dataframe
    check, access = _rows(c.consent_id, "STATE_CHECK")[-1], _rows(c.consent_id, "DATA_ACCESS")[-1]
    who = check["metadata"]["requester_identity"]
    assert (who["result"], who["reason"]) == ("INVALID", "CREDENTIAL_TIME_INVALID")
    assert check["metadata"]["time"]["source"] == "block-timestamp" and check["metadata"]["time"]["unix"] >= block.timestamp
    m = access["metadata"]
    assert (access["result"], m["deny_code"], m["deny_codes"], m["failed_checks"]) == ("DENIED", None, [], ["VI"])
    assert m["time_source"] == "block-timestamp" and m["modules_released"] == [] and m["proof_reference"] is None
    assert _code_fields(check) == [] and _code_fields(access) == []
    assert not [e for e in _rows(c.consent_id, "IDENTITY_VERIFICATION") if e["actor_did"] == CLINICIAN and e["result"] == "VALID"]
    assert onchain.w3.eth.block_number == blocks                      # no proof was presented and nothing was sent


def test_request_path_judges_the_credential_of_the_requester_at_the_block_time(onchain):
    from services import request_service
    c, block = _chain_in_2031(onchain)
    blocks = onchain.w3.eth.block_number
    out = request_service.submit_request(c, CLINICIAN, ["Observation"], "Treatment", "AU", source=_source)
    assert (out["outcome"], out["failed_checks"], out["deny_code"], out["data"]) == ("DENIED", ["VI"], None, {})
    assert out["time"]["source"] == "block-timestamp" and out["time"]["time"] > END_OF_THE_CREDENTIALS
    assert out["identity"].valid is False and out["identity"].reason == "CREDENTIAL_TIME_INVALID"
    assert out["decision"]["VT"] is True and out["decision"]["VL"] is True and out["decision"]["VA"] is True
    assert out["state_check_event"]["metadata"]["requester_identity"]["reason"] == "CREDENTIAL_TIME_INVALID"
    assert not _rows(c.consent_id, "IDENTITY_VERIFICATION")           # only a valid verification is recorded as evidence
    assert out["proof_reference"] is None and onchain.w3.eth.block_number == blocks
