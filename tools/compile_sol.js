// node tools/compile_sol.js <file.sol> <ContractName> <out.json>  (solc 0.8.24, optimizer 200, OZ from node_modules)
const fs = require("fs"), path = require("path"), solc = require("solc");
const src = fs.readFileSync(process.argv[2], "utf8"), name = process.argv[3], out = process.argv[4];
const findImports = p => { const f = path.join("tools", "node_modules", p); return fs.existsSync(f) ? { contents: fs.readFileSync(f, "utf8") } : { error: "not found " + p }; };
const input = { language: "Solidity", sources: { [name + ".sol"]: { content: src } },
  settings: { optimizer: { enabled: true, runs: 200 }, outputSelection: { "*": { "*": ["abi", "evm.bytecode.object"] } } } };
const res = JSON.parse(solc.compile(JSON.stringify(input), { import: findImports }));
const errs = (res.errors || []).filter(e => e.severity === "error");
if (errs.length) { console.error(errs.map(e => e.formattedMessage).join("\n")); process.exit(1); }
const c = res.contracts[name + ".sol"][name];
fs.writeFileSync(out, JSON.stringify({ contractName: name, compiler: "solc 0.8.24 optimizer 200", abi: c.abi, bytecode: "0x" + c.evm.bytecode.object }, null, 1));
console.log("COMPILED", name, "| functions:", c.abi.filter(x => x.type === "function").length, "| bytecode bytes:", c.evm.bytecode.object.length / 2);
