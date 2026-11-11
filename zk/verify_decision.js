// node zk/verify_decision.js '{"proof":{...},"publicSignals":[t, role, purpose, context, tag, consentRoot, revocationRoot]}' [circuit name]
// Prints true or false. Needs the verification key only, so anyone with the proof and the public inputs can run it.
const path = require("path"), fs = require("fs"), snarkjs = require("snarkjs");
(async () => {
  const a = JSON.parse(process.argv[2]), name = process.argv[3] || "halah_decision";
  const vk = JSON.parse(fs.readFileSync(path.join(__dirname, "build", name + "_verification_key.json")));
  console.log(String(a.publicSignals.length === vk.nPublic && await snarkjs.groth16.verify(vk, a.publicSignals, a.proof))); process.exit(0);
})().catch(() => { console.log("false"); process.exit(0); });
