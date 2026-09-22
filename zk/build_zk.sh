#!/usr/bin/env bash
# circom -> r1cs/wasm -> Groth16 dev trusted setup -> verification key + Solidity verifier. Output: zk/build/
set -e; cd "$(dirname "$0")"
[ -f node_modules/snarkjs/package.json ] || { npm init -y >/dev/null 2>&1; npm install --silent snarkjs@0.7.4 circomlib@2.0.5 circomlibjs@0.1.7; }
[ -x ./circom ] || { curl -sL -o circom https://github.com/iden3/circom/releases/download/v2.1.9/circom-linux-amd64; chmod +x circom; }
mkdir -p build && cd build
../circom ../consent_validity.circom --r1cs --wasm --sym -o . -l ../node_modules >/dev/null
S="npx snarkjs"
$S powersoftau new bn128 10 pot10_0000.ptau >/dev/null 2>&1
$S powersoftau contribute pot10_0000.ptau pot10_0001.ptau --name="halah-dev" -e="halah-dev-$(date +%s)" >/dev/null 2>&1
$S powersoftau prepare phase2 pot10_0001.ptau pot10_final.ptau >/dev/null 2>&1
$S groth16 setup consent_validity.r1cs pot10_final.ptau cv_0000.zkey >/dev/null 2>&1
$S zkey contribute cv_0000.zkey consent_validity.zkey --name="halah-dev-2" -e="entropy-$(date +%N)" >/dev/null 2>&1
$S zkey export verificationkey consent_validity.zkey verification_key.json >/dev/null 2>&1
$S zkey export solidityverifier consent_validity.zkey ../../contracts/ConsentValidityVerifier.sol >/dev/null 2>&1
echo "ZK BUILD OK"
