"""Mint a consent SBT on Sepolia from the terminal (REAL transaction)."""
import argparse, sys
from datetime import datetime, timedelta
from blockchain import contract as chain
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--patient", default="did:patient:demo")
    ap.add_argument("--requester", default="did:hospital:001")
    ap.add_argument("--purpose", default="Treatment")
    ap.add_argument("--days", type=int, default=100)
    a = ap.parse_args()
    if not chain.is_configured(): sys.exit("NOT CONFIGURED: .env missing")
    c = chain.ConsentContract(); s = c.status()
    print(f"signer={s['signer']} owner={s['owner']} balance={s['balance_eth']:.4f} ETH chain={s['chain_id']}")
    if s.get("signer_is_owner") is False: sys.exit("signer is NOT the owner - would revert")
    exp = int((datetime.now() + timedelta(days=a.days)).timestamp())
    print("sending mintConsent ... waiting for Sepolia confirmation (~15-30 s)")
    r = c.mint_consent(a.patient, a.requester, a.purpose, exp)
    print(f"STATUS={'SUCCESS' if r['status']==1 else 'REVERTED'} block={r['block_number']} gas={r['gas_used']} token_id={r['token_id']}")
    print("TX      :", r["tx_hash"]); print("Etherscan:", r["explorer_tx"])
    if r.get("explorer_token"): print("Token   :", r["explorer_token"])
if __name__ == "__main__": main()
