import json, os, re, sys, tempfile
import pytest
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
os.environ.setdefault("HALAH_DB_PATH", os.path.join(tempfile.mkdtemp(), "halah_test.db"))

try:
    import blockchain.contract          # reads a local .env once, here, so that the fixture below clears what it set
except Exception:                       # web3 not installed: the tests that need it are skipped
    pass

CHAIN_SETTINGS = ("PRIVATE_KEY", "RPC_URL", "CONTRACT_ADDRESS", "CONTRACT_V4_ADDRESS", "VERIFIER_ADDRESS",
                  "POSEIDON_ADDRESS", "GROTH16_VERIFIER_ADDRESS", "CONTRACT_V4_DEPLOY_BLOCK", "CHAIN_ID")


@pytest.fixture(autouse=True)
def no_chain_settings(monkeypatch):
    """No test reads the chain settings of the machine it runs on: a test that needs one sets it itself."""
    for name in CHAIN_SETTINGS:
        monkeypatch.delenv(name, raising=False)


@pytest.fixture()
def circuit_build(tmp_path, monkeypatch):
    """The verification key of the committed Groth16 verifier, read from its Solidity source and written as the file
    that a circuit build leaves in zk/build. The deployment command reads its key from this file, so a test of the
    command gives the same result whatever zk/build of the machine holds, or does not hold."""
    from blockchain import deploy_v4
    with open(os.path.join(ROOT, "contracts", "HalahDecisionVerifier.sol")) as f:
        k = dict(re.findall(r"uint256 constant (\w+)\s*=\s*(\d+);", f.read()))
    key = {"vk_alpha_1": [k["alphax"], k["alphay"], "1"],
           "IC": [[k[f"IC{i}x"], k[f"IC{i}y"], "1"] for i in range(8)]}
    for name in ("beta", "gamma", "delta"):
        key[f"vk_{name}_2"] = [[k[name + "x1"], k[name + "x2"]], [k[name + "y1"], k[name + "y2"]], ["1", "0"]]
    path = tmp_path / "zk_build" / "halah_decision_verification_key.json"
    path.parent.mkdir()
    path.write_text(json.dumps(key))
    monkeypatch.setattr(deploy_v4, "VERIFICATION_KEY", str(path))
    return path
