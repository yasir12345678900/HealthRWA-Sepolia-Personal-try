"""The deployment from Remix (thesis Section 5.4.1): the Remix-ready sources under contracts/ and the order of the four
deployments with their constructor arguments.

ConsentSBTv4_remix.sol is ConsentSBTv4.sol with its two imports pinned. The Poseidon contract has no Solidity source, so
PoseidonT3Deployer_remix.sol creates it from its bytecode. The order is run here on an in-memory EVM (no network, no
Sepolia, no Remix) with the artefacts of blockchain/abi, and the result is checked with the check mode of the
deployment command, which is run after a deployment from Remix. The key of the deployer is derived from a
label in this file: it is a test key and holds nothing."""
import os
import re
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONTRACTS = os.path.join(ROOT, "contracts")
TEST_KEY_LABEL = "halah remix deployment test deployer"        # the deployer key is derived from this label (not a secret)


def _read(name):
    with open(os.path.join(CONTRACTS, name)) as f:
        return f.read()


def test_remix_copy_of_consentsbtv4_differs_only_in_the_pinned_imports():
    source, copy = _read("ConsentSBTv4.sol").split("\n"), _read("ConsentSBTv4_remix.sol").split("\n")
    note = [line for line in copy if line.startswith("// Remix copy of contracts/ConsentSBTv4.sol")]
    assert len(note) == 1
    copy.remove(note[0])
    assert len(copy) == len(source)
    changed = [(a, b) for a, b in zip(source, copy) if a != b]
    assert changed == [('import "@openzeppelin/contracts/token/ERC721/ERC721.sol";',
                        'import "@openzeppelin/contracts@4.9.6/token/ERC721/ERC721.sol";'),
                       ('import "@openzeppelin/contracts/access/Ownable.sol";',
                        'import "@openzeppelin/contracts@4.9.6/access/Ownable.sol";')]
    # the two verifier contracts have no import, so Remix compiles them as they are
    for name in ("ConsentDecisionVerifier.sol", "HalahDecisionVerifier.sol", "PoseidonT3Deployer_remix.sol"):
        assert not re.search(r"^\s*import\s", _read(name), re.M)


def test_poseidon_deployer_source_carries_the_bytecode_of_the_poseidon_artefact():
    from blockchain import contract_v4 as v4
    (literal,) = re.findall(r'hex"([0-9a-f]+)"', _read("PoseidonT3Deployer_remix.sol"))
    assert "0x" + literal == v4.load_artifact("PoseidonT3")["bytecode"]
    # the compiled deployer holds that creation code, so its constructor creates the same contract
    assert literal in v4.load_artifact("PoseidonT3Deployer")["bytecode"]


def test_remix_order_of_deployments_gives_the_contracts_the_application_expects(circuit_build, tmp_path, capsys, monkeypatch):
    pytest.importorskip("eth_tester", reason="eth-tester not installed")
    from web3 import Web3, EthereumTesterProvider
    from blockchain import contract_v4 as v4, deploy_v4
    w3 = Web3(EthereumTesterProvider())
    key = Web3.keccak(text=TEST_KEY_LABEL)
    deployer = w3.eth.account.from_key(key).address
    w3.eth.send_transaction({"from": w3.eth.accounts[0], "to": deployer, "value": 10 ** 19, "gas": 21000})
    # 1  PoseidonT3Deployer, no argument. Its poseidon() is the address of the Poseidon contract
    carrier, _ = v4.deploy_contract(w3, key, "PoseidonT3Deployer")
    poseidon = w3.eth.contract(address=carrier, abi=v4.load_artifact("PoseidonT3Deployer")["abi"]).functions.poseidon().call()
    direct, _ = v4.deploy_contract(w3, key, "PoseidonT3")
    assert len(w3.eth.get_code(poseidon)) > 9000 and w3.eth.get_code(poseidon) == w3.eth.get_code(direct)
    # 2  ConsentSBTv4(poseidon)   3  Groth16Verifier, no argument   4  ConsentDecisionVerifier(groth16, token)
    token, _ = v4.deploy_contract(w3, key, "ConsentSBTv4", poseidon)
    groth16, _ = v4.deploy_contract(w3, key, "HalahDecisionVerifier")
    verifier, _ = v4.deploy_contract(w3, key, "ConsentDecisionVerifier", groth16, token)
    addresses = {"poseidon": poseidon, "token": token, "groth16": groth16, "verifier": verifier}
    read = deploy_v4.check_deployment(w3, addresses, signer=deployer, key_constants=deploy_v4.verification_key_constants())
    assert (read["owner"], read["hasher"], read["proof_verifier"], read["consent_token"]) == (deployer, poseidon, groth16, token)
    # the Poseidon contract created by the deployer hashes as the tree of the token expects: a mint goes through
    client = v4.ConsentContractV4(w3=w3, address=token, private_key=key)
    minted = client.mint_consent(v4.derive_consent_address("did:patient:x", "remix-1")[0], 12345)
    assert minted["status"] == 1 and minted["token_id"] == 1 and client.consent_of(1) == {"commitment": 12345, "revoked": False}
    # the check mode of the deployment command accepts the four addresses and writes them where the application reads them
    env_file = tmp_path / "remix.env"
    monkeypatch.setenv("CHAIN_ID", str(w3.eth.chain_id))             # the command expects Sepolia unless told otherwise
    deploy_v4.main(["--check", "--poseidon", poseidon, "--token", token, "--groth16", groth16, "--verifier", verifier,
                    "--env-file", str(env_file)], w3=w3, private_key=Web3.to_hex(key))
    written = dict(line.split("=", 1) for line in env_file.read_text().splitlines() if "=" in line)
    assert (written["CONTRACT_V4_ADDRESS"], written["VERIFIER_ADDRESS"]) == (token, verifier)
    assert (written["POSEIDON_ADDRESS"], written["GROTH16_VERIFIER_ADDRESS"]) == (poseidon, groth16)
    assert Web3.to_hex(key)[2:] not in env_file.read_text() + capsys.readouterr().out          # the key is neither written nor printed
    # a deployer address given in the place of the Poseidon contract is refused
    with pytest.raises(deploy_v4.DeployError):
        deploy_v4.check_deployment(w3, dict(addresses, poseidon=carrier))
