"""Deploy a HALAH contract artifact to Sepolia from .env (PRIVATE_KEY = deployer/owner).
    python3 -m blockchain.deploy ConsentSBTv3
Then set CONTRACT_ADDRESS=<addr> and CONTRACT_VERSION=3 in .env."""
import json, os, sys
from dotenv import load_dotenv
from web3 import Web3
load_dotenv()

def main(name="ConsentSBTv3"):
    art = json.load(open(os.path.join(os.path.dirname(__file__), "abi", f"{name}.json")))
    w3 = Web3(Web3.HTTPProvider(os.environ.get("RPC_URL", "https://ethereum-sepolia-rpc.publicnode.com")))
    acct = w3.eth.account.from_key(os.environ["PRIVATE_KEY"])
    print(f"deployer={acct.address} chain={w3.eth.chain_id} balance={w3.from_wei(w3.eth.get_balance(acct.address),'ether'):.4f} ETH")
    C = w3.eth.contract(abi=art["abi"], bytecode=art["bytecode"])
    tx = C.constructor().build_transaction({"from": acct.address, "nonce": w3.eth.get_transaction_count(acct.address), "chainId": w3.eth.chain_id})
    signed = acct.sign_transaction(tx)
    h = w3.eth.send_raw_transaction(getattr(signed, "raw_transaction", None) or signed.rawTransaction)
    print("tx:", Web3.to_hex(h), "- waiting for confirmation...")
    rc = w3.eth.wait_for_transaction_receipt(h, timeout=240)
    print(f"STATUS={'SUCCESS' if rc['status']==1 else 'FAILED'} block={rc['blockNumber']} gas={rc['gasUsed']}")
    print("CONTRACT_ADDRESS=" + rc["contractAddress"])
    print("https://sepolia.etherscan.io/address/" + rc["contractAddress"])

if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "ConsentSBTv3")
