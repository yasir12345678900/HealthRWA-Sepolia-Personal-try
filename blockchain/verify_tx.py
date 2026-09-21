"""Verify a tx hash really exists on Sepolia:  python3 -m blockchain.verify_tx 0x<hash>"""
import os, sys
from dotenv import load_dotenv
from web3 import Web3
load_dotenv()
def main(a):
    if len(a)<2: print(__doc__); return 2
    w3=Web3(Web3.HTTPProvider(os.environ.get("RPC_URL","https://ethereum-sepolia-rpc.publicnode.com")))
    try: r=w3.eth.get_transaction_receipt(a[1].strip())
    except Exception as e: print("NOT FOUND on Sepolia:",a[1],type(e).__name__); return 1
    print(f"ON-CHAIN block={r['blockNumber']} status={'SUCCESS' if r['status']==1 else 'REVERTED'} gas={r['gasUsed']}")
    print(f"https://sepolia.etherscan.io/tx/{a[1].strip()}"); return 0
if __name__=="__main__": sys.exit(main(sys.argv))
