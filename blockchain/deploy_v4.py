'''
Deployment of the thesis-design contracts for HALAH (ConsentSBTv4, Poseidon, the Groth16 verifier, the decision verifier)
History Access Link for Authorised Healthcare Version 1
Authors: Charles, Yasir, Daniel, Kejia, Yasmin, Farookh
Date: 2026-11-17

One command deploys the four contracts from the wallet whose key is configured, reads them back, and
writes their addresses where the application reads them (the .env file beside the repository):

    python3 -m blockchain.deploy_v4 --dry-run     look first: the deployer, the chain, the balance, the gas
                                                  price and the estimated cost. Nothing is sent
    python3 -m blockchain.deploy_v4               deploy, read back, write the addresses, print READY

The command stops before anything is sent when zk/build holds no circuit build: the proving key there must be the one
that the Groth16 verifier was exported from, or no proof could be made for the contracts that are deployed. The
option --without-circuit-build lets it go on (for a machine that only deploys).

What a deployment printed (the deployer, the four addresses, their transactions, blocks and gas) is also written
into a file beside the env file, deployment_<network>_block<first block>.txt, for the record of the thesis.

Order of the deployments and their constructor arguments:

    1  HalahDecisionVerifier     the Groth16 verifier of the decision circuit, no argument
    2  PoseidonT3                the Poseidon contract for two inputs (bytecode only), no argument
    3  ConsentSBTv4              (address of 2). The deployer becomes the owner
    4  ConsentDecisionVerifier   (address of 1, address of 3)

After a deployment made elsewhere (Remix with MetaMask) the same command checks the four contracts and
writes the same lines, without sending anything:

    python3 -m blockchain.deploy_v4 --check --poseidon 0x.. --token 0x.. --groth16 0x.. --verifier 0x..

Configuration, from the environment or the env file (the environment wins):

    RPC_URL       JSON-RPC endpoint (default: public Sepolia node)
    PRIVATE_KEY   key of the deploying wallet. It is used to sign and is never printed or written
    CHAIN_ID      the chain that is expected (default 11155111, Sepolia). Another chain stops the command

Lines written: CONTRACT_V4_ADDRESS, VERIFIER_ADDRESS, POSEIDON_ADDRESS, GROTH16_VERIFIER_ADDRESS,
CONTRACT_V4_DEPLOY_BLOCK and CHAIN_ID. No other line of the file is changed.
'''
import argparse
import json
import os
import sys
from datetime import datetime, timezone

from dotenv import dotenv_values, set_key
from eth_utils import to_checksum_address
from web3 import Web3

from blockchain import contract_v4 as v4
from blockchain.contract import DEFAULT_RPC, SEPOLIA_CHAIN_ID, explorer_address, explorer_tx

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENV_FILE = os.path.join(ROOT, ".env")
VERIFICATION_KEY = os.path.join(ROOT, "zk", "build", "halah_decision_verification_key.json")
NO_CIRCUIT_BUILD = ("zk/build holds no circuit build: bring zk/build/halah_decision.zkey, "
                    "zk/build/halah_decision_js/halah_decision.wasm and zk/build/halah_decision_verification_key.json "
                    "of the build that contracts/HalahDecisionVerifier.sol was exported from. Do not run "
                    "zk/build_decision.sh: it makes a new key. Nothing was sent.")

# The four contracts in the order of their deployment: (artefact, key of the address in the result).
ORDER = (("HalahDecisionVerifier", "groth16"), ("PoseidonT3", "poseidon"),
         ("ConsentSBTv4", "token"), ("ConsentDecisionVerifier", "verifier"))
# Line of the env file for each address.
ENV_NAMES = {"token": "CONTRACT_V4_ADDRESS", "verifier": "VERIFIER_ADDRESS", "poseidon": "POSEIDON_ADDRESS",
             "groth16": "GROTH16_VERIFIER_ADDRESS"}
# Gas of the four deployments together, rounded up (about 5.8 million on a local chain). Used for the balance check only.
ESTIMATED_GAS = 6_000_000


class DeployError(RuntimeError):
    '''The command stops: the message says what is missing or wrong. Nothing more is sent after it.'''


# ---- the verification key and the code on chain ---------------------------------------------------

def verification_key_constants(path=None):
    '''The curve points of the verification key of the decision circuit (alpha, beta, gamma, delta and the IC
    points) as integers, or None when the circuit is not built on this machine.'''
    path = path or VERIFICATION_KEY
    if not os.path.exists(path):
        return None
    with open(path) as f:
        key = json.load(f)

    def numbers(value):
        if isinstance(value, list):
            for item in value:
                yield from numbers(item)
        else:
            yield int(value)

    return [n for name in ("vk_alpha_1", "vk_beta_2", "vk_gamma_2", "vk_delta_2", "IC")
            for n in numbers(key[name]) if n > 1]          # 0 and 1 are the projective coordinates


def holds_constants(code, constants):
    '''True when every constant stands in the contract code (the Groth16 verifier pushes each one as a literal).'''
    code = bytes(code)
    return bool(constants) and all(n.to_bytes((n.bit_length() + 7) // 8, "big") in code for n in constants)


def _without_metadata(code):
    # solc appends a metadata record whose hash changes with the path of the source file, so the same
    # contract compiled in Remix ends differently. The last two bytes give the length of the record.
    if len(code) > 2:
        n = int.from_bytes(code[-2:], "big")
        if n + 2 <= len(code) and code[-n - 2] in (0xA1, 0xA2, 0xA3) and b"solc" in code[-n - 2:]:
            return code[:-n - 2]
    return code


def code_matches(code, name, immutables=()):
    '''True when `code`, read from the chain, is the contract `name` of blockchain/abi. The metadata record is
    left out, and the addresses that the constructor writes into the code (`immutables`) are blanked first.'''
    creation = bytes.fromhex(v4.load_artifact(name)["bytecode"][2:])
    body = _without_metadata(bytes(code))
    for address in immutables:
        body = body.replace(bytes(12) + bytes.fromhex(address[2:]), bytes(32))
    return len(body) > 0 and body in creation


def check_deployment(w3, addresses, signer=None, key_constants=None):
    '''Read the four contracts back from the chain and compare them with what the application expects:
    code at every address, the code of this repository, the token wired to the Poseidon contract, the decision
    verifier wired to the Groth16 verifier and to the token, the Groth16 verifier holding the verification key
    (`key_constants`, when the circuit is built here) and the token owned by `signer` (when a key is configured).
    Returns what was read. Raises DeployError at the first difference.'''
    try:
        a = {k: to_checksum_address(addresses[k]) for _, k in ORDER}
    except Exception:
        raise DeployError("the four addresses are needed: groth16, poseidon, token and verifier") from None
    code = {k: bytes(w3.eth.get_code(a[k])) for _, k in ORDER}
    for name, k in ORDER:
        if not code[k]:
            raise DeployError("no contract code at %s (given as %s)" % (a[k], name))
    token = w3.eth.contract(address=a["token"], abi=v4.load_artifact("ConsentSBTv4")["abi"])
    verifier = w3.eth.contract(address=a["verifier"], abi=v4.load_artifact("ConsentDecisionVerifier")["abi"])
    try:
        out = {"owner": token.functions.owner().call(), "hasher": token.functions.hasher().call(),
               "consent_count": int(token.functions.consentCount().call()),
               "proof_verifier": verifier.functions.proofVerifier().call(),
               "consent_token": verifier.functions.consentToken().call()}
    except Exception as e:
        raise DeployError("the contracts did not answer as ConsentSBTv4 and ConsentDecisionVerifier do: %s" % str(e)[:200]) from None
    if out["hasher"] != a["poseidon"]:
        raise DeployError("ConsentSBTv4 uses another Poseidon contract (%s)" % out["hasher"])
    if out["proof_verifier"] != a["groth16"]:
        raise DeployError("the decision verifier calls another Groth16 verifier (%s)" % out["proof_verifier"])
    if out["consent_token"] != a["token"]:
        raise DeployError("the decision verifier reads its roots from another token contract (%s)" % out["consent_token"])
    wiring = {"groth16": (), "poseidon": (), "token": (a["poseidon"],), "verifier": (a["groth16"], a["token"])}
    for name, k in ORDER:
        if not code_matches(code[k], name, wiring[k]):
            raise DeployError("the code at %s is not the %s of this repository (blockchain/abi/%s.json)" % (a[k], name, name))
    if key_constants is not None and not holds_constants(code["groth16"], key_constants):
        raise DeployError("the Groth16 verifier at %s does not hold the verification key of zk/build" % a["groth16"])
    if signer is not None and out["owner"] != signer:
        raise DeployError("the configured key (%s) is not the owner of ConsentSBTv4 (%s): the application could not mint"
                          % (signer, out["owner"]))
    return out


# ---- the env file ----------------------------------------------------------------------------------

def write_env(path, addresses, chain_id, deploy_block=None):
    '''Write the address lines into the env file. Every other line of the file stays as it is.'''
    lines = {ENV_NAMES[k]: to_checksum_address(addresses[k]) for k in ENV_NAMES}
    if deploy_block is not None:
        lines["CONTRACT_V4_DEPLOY_BLOCK"] = str(int(deploy_block))
    lines["CHAIN_ID"] = str(int(chain_id))
    for name, value in lines.items():
        set_key(path, name, value, quote_mode="never")
    return lines


def write_record(env_file, chain_id, receipts, printed):
    '''Keep what a deployment printed in a file beside the env file, named by the network and the block of the
    first deployment. It holds addresses, transactions, blocks and gas, and no key. Returns the path.'''
    first = min(r["block_number"] for r in receipts.values())
    network = "sepolia" if chain_id == SEPOLIA_CHAIN_ID else "chain%s" % chain_id
    path = os.path.join(os.path.dirname(os.path.abspath(env_file)), "deployment_%s_block%s.txt" % (network, first))
    with open(path, "w", encoding="utf-8") as f:
        f.write("Deployment of %s (UTC), python3 -m blockchain.deploy_v4\n" % datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"))
        f.write("\n".join(printed) + "\n")
    return path


# ---- the command -----------------------------------------------------------------------------------

def _arguments(argv):
    p = argparse.ArgumentParser(prog="python3 -m blockchain.deploy_v4",
                                description="Deploy ConsentSBTv4, the Poseidon contract, the Groth16 verifier and the "
                                            "decision verifier from the configured wallet, or check a deployment made elsewhere.")
    p.add_argument("--env-file", default=None, help="env file to read and to write (default: .env beside the repository)")
    p.add_argument("--dry-run", action="store_true", help="print the deployer, the balance and the estimated cost, send nothing")
    p.add_argument("--force", action="store_true", help="deploy although CONTRACT_V4_ADDRESS already names a contract on this chain")
    p.add_argument("--check", action="store_true", help="send nothing: check the four contracts and write their addresses")
    p.add_argument("--without-circuit-build", action="store_true",
                   help="go on although zk/build holds no circuit build (no proof can be made on such a machine)")
    for name in ("poseidon", "token", "groth16", "verifier"):
        p.add_argument("--" + name, default=None, help="with --check: address of this contract (default: the env file)")
    p.add_argument("--deploy-block", type=int, default=None, help="with --check: block of the token deployment, if known")
    return p.parse_args(argv)


def main(argv=None, w3=None, private_key=None, gas=None):
    '''Deploy the four contracts, or with --check verify four given ones. Returns the addresses and what was read back.
    The tests pass an in-memory chain (`w3`) and a test key. Raises DeployError with a plain message when it stops.'''
    args = _arguments(sys.argv[1:] if argv is None else argv)
    env_file = args.env_file or ENV_FILE
    printed = []

    def say(line):
        printed.append(line)
        print(line)
    config = {**(dotenv_values(env_file) if os.path.exists(env_file) else {}), **os.environ}
    private_key = private_key or config.get("PRIVATE_KEY") or ""
    w3 = w3 or Web3(Web3.HTTPProvider(config.get("RPC_URL") or DEFAULT_RPC, request_kwargs={"timeout": 30}))
    try:
        chain_id = w3.eth.chain_id
    except Exception as e:
        raise DeployError("the chain could not be reached (RPC_URL): %s" % str(e)[:200]) from None
    expected = int(config.get("CHAIN_ID") or SEPOLIA_CHAIN_ID)
    network = "Sepolia" if chain_id == SEPOLIA_CHAIN_ID else "not Sepolia"
    if chain_id != expected:
        raise DeployError("the endpoint answers for chain %s and chain %s is expected (CHAIN_ID). Nothing was sent." % (chain_id, expected))

    signer = None
    if private_key:
        try:
            signer = w3.eth.account.from_key(private_key).address
        except Exception:
            raise DeployError("PRIVATE_KEY is not a usable key") from None

    # the proving key in zk/build must belong to the verifier that is deployed, or every proof would be refused
    constants = verification_key_constants()
    if constants is None:
        if not args.without_circuit_build:
            raise DeployError(NO_CIRCUIT_BUILD)
        say("Verification key  zk/build holds none: the comparison with the Groth16 verifier is skipped (--without-circuit-build)")
    elif not holds_constants(bytes.fromhex(v4.load_artifact("HalahDecisionVerifier")["bytecode"][2:]), constants):
        raise DeployError("the verification key of zk/build is not the one inside blockchain/abi/HalahDecisionVerifier.json: "
                          "proofs made with this build would be refused on chain. Nothing was sent.")
    else:
        say("Verification key  zk/build matches blockchain/abi/HalahDecisionVerifier.json")

    if args.check:
        addresses = {k: getattr(args, k) or config.get(ENV_NAMES[k]) for k in ENV_NAMES}
        missing = [k for k, value in addresses.items() if not value]
        if missing:
            raise DeployError("no address given for: %s (use --%s, or set %s)" % (", ".join(missing), missing[0], ENV_NAMES[missing[0]]))
        read = check_deployment(w3, addresses, signer=signer, key_constants=constants)
        print("Chain             %s (%s), block %s" % (chain_id, network, w3.eth.block_number))
        for name, k in ORDER:
            print("%-24s %s" % (name, to_checksum_address(addresses[k])))
        print("Owner of the token  %s%s" % (read["owner"], "" if signer else "  (no key configured: not compared with a signer)"))
        block = args.deploy_block if args.deploy_block is not None else config.get("CONTRACT_V4_DEPLOY_BLOCK")
        lines = write_env(env_file, addresses, chain_id, deploy_block=block)
        _report(env_file, lines)
        return {**{k: to_checksum_address(addresses[k]) for k in addresses}, "chain_id": chain_id, "read_back": read, "env": lines, "sent": 0}

    if not signer:
        raise DeployError("PRIVATE_KEY is not set: the key of the deploying wallet is read from the environment or from the env file")
    balance, price = w3.eth.get_balance(signer), w3.eth.gas_price
    cost = ESTIMATED_GAS * price
    say("Deployer          %s" % signer)
    say("Chain             %s (%s), block %s" % (chain_id, network, w3.eth.block_number))
    say("Balance           %.6f ETH" % w3.from_wei(balance, "ether"))
    say("Gas price         %.4f gwei" % w3.from_wei(price, "gwei"))
    say("Estimated cost    about %s gas for the four contracts = %.6f ETH at this price" % (format(ESTIMATED_GAS, ","), w3.from_wei(cost, "ether")))
    if balance < 2 * cost:
        raise DeployError("the balance is below twice the estimated cost (%.6f ETH). Nothing was sent." % w3.from_wei(2 * cost, "ether"))
    existing = config.get("CONTRACT_V4_ADDRESS")
    if existing and not args.force and Web3.is_address(existing) and len(w3.eth.get_code(to_checksum_address(existing))) > 0:
        raise DeployError("CONTRACT_V4_ADDRESS is already %s, which holds a contract on this chain. Nothing was sent. "
                          "Check it with --check, or give --force to deploy a new set." % existing)
    if args.dry_run:
        print("DRY RUN: nothing was sent.")
        return {"chain_id": chain_id, "deployer": signer, "balance_wei": balance, "gas_price_wei": price, "sent": 0}

    out, receipts = {}, {}
    try:
        for name, k in ORDER:
            arguments = {"token": ("poseidon",), "verifier": ("groth16", "token")}.get(k, ())
            try:
                out[k], rc = v4.deploy_contract(w3, private_key, name, *[out[x] for x in arguments], gas=gas)
            except Exception as e:
                done = ", ".join("%s %s" % (n, out[x]) for n, x in ORDER if x in out) or "none"
                raise DeployError("the deployment of %s failed: %s. Deployed before it: %s. The env file was not changed."
                                  % (name, str(e)[:200], done)) from None
            tx = Web3.to_hex(rc["transactionHash"])
            receipts[k] = {"tx_hash": tx, "block_number": int(rc["blockNumber"]), "gas_used": int(rc["gasUsed"])}
            say("%-24s %s  tx %s  block %s  gas %s" % (name, out[k], tx, receipts[k]["block_number"], format(receipts[k]["gas_used"], ",")))
            if chain_id == SEPOLIA_CHAIN_ID:
                say("%-24s %s  %s" % ("", explorer_address(out[k]), explorer_tx(tx)))
        say("Total gas         %s" % format(sum(r["gas_used"] for r in receipts.values()), ","))
        read = check_deployment(w3, out, signer=signer, key_constants=constants)
        lines = write_env(env_file, out, chain_id, deploy_block=receipts["token"]["block_number"])
        _report(env_file, lines, say)
    except DeployError as error:
        printed.append("STOPPED: %s" % error)
        raise
    finally:
        # what was sent is kept, also when a later step stopped the command
        record = None
        if receipts:
            try:
                record = write_record(env_file, chain_id, receipts, printed)
                print("Record of this deployment: %s" % record)
            except OSError as failure:
                print("The record of this deployment could not be written (%s): keep the lines above." % failure)
    return {**out, "chain_id": chain_id, "deployer": signer, "receipts": receipts, "read_back": read, "env": lines,
            "sent": len(receipts), "record": record}


def _report(env_file, lines, say=print):
    say("Written to %s:" % env_file)
    for name, value in lines.items():
        say("  %s=%s" % (name, value))
    say("READY: the application reads these addresses at its next start.")


if __name__ == "__main__":
    try:
        main()
    except DeployError as error:
        sys.exit("STOPPED: %s" % error)
