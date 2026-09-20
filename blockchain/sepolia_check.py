'''Run:  python3 -m blockchain.sepolia_check   -> prints an on-chain readiness report.'''
import os
import sys
from dotenv import load_dotenv

load_dotenv()
OK, NO = "[OK] ", "[XX] "


def main():
    from blockchain import contract as chain
    print("HALAH - Sepolia readiness check")
    print("-" * 44)
    rpc = os.environ.get("RPC_URL", chain.DEFAULT_RPC)
    addr = os.environ.get("CONTRACT_ADDRESS")
    pk = os.environ.get("PRIVATE_KEY")
    print((OK if addr else NO) + "CONTRACT_ADDRESS: " + (addr or "missing -> deploy ConsentSBTv2 in Remix, put 0x... in .env"))
    print((OK if pk else NO) + "PRIVATE_KEY: " + ("set (hidden)" if pk else "missing -> owner TEST wallet key in .env"))
    print("[..] RPC_URL: " + rpc)
    if not (addr and pk):
        print("\nMode: DEMO (local ledger). Fill .env to enable on-chain mode.")
        return 1
    try:
        s = chain.ConsentContract().status()
    except Exception as e:
        print(NO + "RPC / contract error: " + str(e))
        return 2
    print((OK if s["is_sepolia"] else NO) + f"Network: chainId {s['chain_id']} " + ("(Sepolia)" if s["is_sepolia"] else "(NOT Sepolia!)") + f" - block {s['block']}")
    print((OK if s["balance_eth"] > 0 else NO) + f"Signer {s['signer']} balance: {s['balance_eth']:.5f} ETH" + ("" if s["balance_eth"] > 0 else "  -> get test ETH from a Sepolia faucet"))
    print((OK if s["contract_has_code"] else NO) + f"Contract {s['contract']} has code")
    print((OK if s["signer_is_owner"] else NO) + f"Signer is contract owner (owner = {s['owner']})")
    print("Explorer: " + s["explorer_contract"])
    ready = s["is_sepolia"] and s["balance_eth"] > 0 and s["contract_has_code"] and bool(s["signer_is_owner"])
    print("\nREADY - run the app and complete a 2/2 guardian signature to mint on-chain." if ready else "\nNOT READY - fix the [XX] items above.")
    return 0 if ready else 3


if __name__ == "__main__":
    sys.exit(main())
