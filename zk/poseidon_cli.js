// node zk/poseidon_cli.js '<json>'   Poseidon reference values from circomlibjs (the parameters of the circuit and of the contract).
// The Python services compute the same values without Node. This helper is the JavaScript side of the shared conventions,
// and the tests use it to compare the two. One call answers one request and prints JSON with decimal strings:
//   {"op":"hash","inputs":[["1","2"],...]}                      -> {"out":[...]}   Poseidon of each list
//   {"op":"field","texts":["did:...",...]}                       -> {"out":[...]}   keccak256(utf8) with the top 8 bits cleared
//   {"op":"guardians","dids":[...],"threshold":2}                -> {"out":"..."}   digest of the sorted guardians and the threshold
//   {"op":"commitment","opening":{patient,...,blinding}}         -> {"out":"..."}   c = Poseidon of the ten opening values
//   {"op":"tag","requester":"did:...","nonce":"..."}             -> {"out":"..."}   tag = Poseidon(requester, nonce)
//   {"op":"root","depth":16,"leaves":["..",...]}                 -> {"out":"..."}   Merkle root, node = Poseidon(left, right), empty leaf 0
const { buildPoseidon } = require("circomlibjs"), { utils } = require("ethers");
const OPENING = ["patient", "guardiansDigest", "requester", "role", "purpose", "context", "scopeMask", "notBefore", "expiry", "blinding"];
(async () => {
  const a = JSON.parse(process.argv[2]); const p = await buildPoseidon();
  const H = xs => p.F.toObject(p(xs.map(x => BigInt(x))));
  const field = s => BigInt(utils.id(s)) & ((1n << 248n) - 1n);
  let out;
  if (a.op === "hash") out = a.inputs.map(xs => H(xs).toString());
  else if (a.op === "field") out = a.texts.map(s => field(s).toString());
  else if (a.op === "guardians") {
    const g = a.dids.map(field).sort((x, y) => (x < y ? -1 : x > y ? 1 : 0));
    out = H([g.slice(1).reduce((acc, x) => H([acc, x]), g[0]), a.threshold]).toString();
  } else if (a.op === "commitment") out = H(OPENING.map(k => a.opening[k])).toString();
  else if (a.op === "tag") out = H([field(a.requester), a.nonce]).toString();
  else if (a.op === "root") {
    // level by level: a missing right node is the root of an empty subtree of that height
    let level = a.leaves.map(x => BigInt(x)), zero = 0n;
    for (let h = 0; h < a.depth; h++) {
      const next = [];
      for (let i = 0; i < level.length; i += 2) next.push(H([level[i], i + 1 < level.length ? level[i + 1] : zero]));
      zero = H([zero, zero]); level = next.length ? next : [zero];
    }
    out = level[0].toString();
  } else throw new Error("unknown op " + a.op);
  console.log(JSON.stringify({ out })); process.exit(0);
})().catch(e => { console.error("POSEIDON_FAILED " + e.message); process.exit(1); });
