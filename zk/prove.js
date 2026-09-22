const path = require("path"), snarkjs = require("snarkjs"), { buildPoseidon } = require("circomlibjs");
(async () => {
  const a = JSON.parse(process.argv[2]); const p = await buildPoseidon();
  const commitment = p.F.toObject(p([BigInt(a.secret), BigInt(a.expiry)])).toString();
  const b = path.join(__dirname, "build");
  const { proof, publicSignals } = await snarkjs.groth16.fullProve({ secret: a.secret, expiry: a.expiry, commitment, now: a.now },
      path.join(b, "consent_validity_js/consent_validity.wasm"), path.join(b, "consent_validity.zkey"));
  console.log(JSON.stringify({ commitment, proof, publicSignals })); process.exit(0);
})().catch(e => { console.error("PROVE_FAILED " + e.message); process.exit(1); });
