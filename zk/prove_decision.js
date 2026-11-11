// node zk/prove_decision.js '<circuit inputs as JSON>' [circuit name]   Groth16 proof of the decision statement (Algorithm 7.2).
// The inputs are the public inputs and the witness that services/zk_decision_service.py assembles. A witness that does not
// satisfy the circuit gives no proof: the script fails with PROVE_FAILED.
const path = require("path"), snarkjs = require("snarkjs");
(async () => {
  const input = JSON.parse(process.argv[2]), name = process.argv[3] || "halah_decision", b = path.join(__dirname, "build");
  const { proof, publicSignals } = await snarkjs.groth16.fullProve(input, path.join(b, name + "_js", name + ".wasm"), path.join(b, name + ".zkey"));
  console.log(JSON.stringify({ proof, publicSignals })); process.exit(0);
})().catch(e => { console.error("PROVE_FAILED " + e.message); process.exit(1); });
