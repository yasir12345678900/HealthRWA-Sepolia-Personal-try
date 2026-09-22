const path = require("path"), fs = require("fs"), snarkjs = require("snarkjs");
(async () => {
  const a = JSON.parse(process.argv[2]);
  const vk = JSON.parse(fs.readFileSync(path.join(__dirname, "build", "verification_key.json")));
  console.log(String(await snarkjs.groth16.verify(vk, a.publicSignals, a.proof))); process.exit(0);
})().catch(() => { console.log("false"); process.exit(0); });
