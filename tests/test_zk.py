"""Real Groth16 round-trip when zk/build exists (skipped otherwise) + honest placeholder."""
import pytest
from datetime import datetime, timedelta

def _consent(days=30):
    from models.consent import Consent
    return Consent("zk-1", "did:patient:x", "did:hospital:001", ["did:parent:A"], "Treatment", ["Observation"], 1, [],
                   datetime.now().isoformat(), (datetime.now() + timedelta(days=days)).isoformat())

def test_placeholder_mode_is_labelled_honestly(monkeypatch):
    from services import zk_service as zk
    monkeypatch.setattr(zk, "zk_available", lambda: False)
    p = zk.generate_proof(_consent()); assert p["mode"] == "placeholder" and "NOT zero-knowledge" in p["scheme"]

def test_real_groth16_roundtrip_and_tamper():
    from services import zk_service as zk
    if not zk.zk_available(): pytest.skip("run zk/build_zk.sh")
    p = zk.generate_proof(_consent()); assert p["mode"] == "groth16" and zk.verify_proof(p) is True
    bad = dict(p); bad["publicSignals"] = list(p["publicSignals"]); bad["publicSignals"][-1] = str(int(bad["publicSignals"][-1]) + 1)
    assert zk.verify_proof(bad) is False

def test_expired_consent_cannot_be_proven():
    from services import zk_service as zk
    if not zk.zk_available(): pytest.skip("run zk/build_zk.sh")
    with pytest.raises(RuntimeError): zk.generate_proof(_consent(days=-1))
