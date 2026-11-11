#!/usr/bin/env bash
# Decision circuit (zk/halah_decision.circom): circom -> r1cs/wasm -> Groth16 setup -> verification key + Solidity verifier.
# Output: zk/build/halah_decision.* and contracts/HalahDecisionVerifier.sol
#
# TRUSTED SETUP. What this script runs by default is a DEVELOPMENT setup made on one machine: whoever ran it could
# forge proofs, so it is not the ceremony of the thesis. Both phases can be replaced without changing the script:
#   PTAU=/path/to/final.ptau   phase one from a public Powers of Tau ceremony (a prepared file of power 14 or more,
#                              for example powersOfTau28_hez_final_14.ptau). Without PTAU a development phase one is made here.
#   ZKEY=/path/to/final.zkey   the result of a phase two with independent contributors for THIS r1cs and PTAU. It is
#                              verified against both and used as it is. Without ZKEY two development contributions are made here.
# The hashes of the circuit, of both phases and of the keys are written to zk/build/halah_decision_setup.txt.
#
#   DEPTH=20 bash zk/build_decision.sh   the same circuit for another tree depth, as halah_decision_d20 (each depth is a
#                                        circuit of its own with its own phase two, and no Solidity verifier is exported)
set -e; HERE="$(pwd)"; cd "$(dirname "$0")"; ZK="$(pwd)"
absolute() { case "$1" in /*|"") echo "$1";; *) echo "$HERE/$1";; esac; }
PTAU="$(absolute "$PTAU")"; ZKEY="$(absolute "$ZKEY")"
[ -f node_modules/snarkjs/package.json ] || { npm init -y >/dev/null 2>&1; npm install --silent snarkjs@0.7.4 circomlib@2.0.5 circomlibjs@0.1.7 circom2@0.2.23; }
DEPTH="${DEPTH:-16}"; NAME=halah_decision; SRC="$ZK/halah_decision.circom"
mkdir -p build && cd build
if [ "$DEPTH" != 16 ]; then
  NAME="halah_decision_d$DEPTH"; SRC="$ZK/build/$NAME.circom"
  sed "s/HalahDecision(16, 4)/HalahDecision($DEPTH, 4)/" "$ZK/halah_decision.circom" > "$SRC"
fi
plain() { sed 's/\x1b\[[0-9;]*m//g'; }                                   # snarkjs colours its log lines
snark() { node "$ZK/node_modules/snarkjs/build/cli.cjs" "$@"; }
quiet() { "$@" >"$NAME.log" 2>&1 || { plain <"$NAME.log"; echo "ZK DECISION BUILD FAILED: $*"; exit 1; }; rm -f "$NAME.log"; }

# Compile with full simplification of the linear constraints (--O2), which Groth16 allows. The compiler of circom2 runs in
# a sandbox that reads below its working directory only, so it is started at / and every path is absolute and resolved.
LIB="$(cd -P "$ZK/node_modules/circomlib/.." && pwd)"
compile() { (cd / && node "$ZK/node_modules/circom2/cli.js" "$SRC" --r1cs --wasm --sym --O2 -o "$ZK/build" -l "$LIB"); }
quiet compile
INFO="$(snark r1cs info "$NAME.r1cs" | plain)"
CONSTRAINTS="$(echo "$INFO" | sed -n 's/.*# of Constraints: //p')"
PUBLIC="$(echo "$INFO" | sed -n 's/.*# of Public Inputs: //p')"
[ "$PUBLIC" = 7 ] || { echo "ZK DECISION BUILD FAILED: the circuit must have 7 public inputs, found '$PUBLIC'"; exit 1; }
POWER=1; while [ $((1 << POWER)) -le $((CONSTRAINTS + PUBLIC)) ]; do POWER=$((POWER + 1)); done

# Phase one (not specific to the circuit).
if [ -n "$PTAU" ]; then
  PHASE1="$PTAU"; PHASE1_LABEL="given file $(basename "$PTAU")"
else
  PHASE1="$ZK/build/pot${POWER}_dev_final.ptau"; PHASE1_LABEL="DEVELOPMENT (one contributor on this machine)"
  if [ ! -f "$PHASE1" ]; then
    quiet snark powersoftau new bn128 "$POWER" "pot${POWER}_0000.ptau"
    quiet snark powersoftau contribute "pot${POWER}_0000.ptau" "pot${POWER}_0001.ptau" --name="halah-dev" -e="halah-dev-$(date +%s)"
    quiet snark powersoftau prepare phase2 "pot${POWER}_0001.ptau" "$PHASE1"
    rm -f "pot${POWER}_0000.ptau" "pot${POWER}_0001.ptau"
  fi
fi

# Phase two (specific to this circuit).
if [ -n "$ZKEY" ]; then
  FINAL="$ZKEY"; PHASE2_LABEL="given file $(basename "$ZKEY")"
else
  FINAL="$ZK/build/${NAME}_0002.zkey"; PHASE2_LABEL="DEVELOPMENT (two contributions on this machine)"
  quiet snark groth16 setup "$NAME.r1cs" "$PHASE1" "${NAME}_0000.zkey"
  quiet snark zkey contribute "${NAME}_0000.zkey" "${NAME}_0001.zkey" --name="halah-dev-1" -e="halah-dev-1-$(date +%s)"
  quiet snark zkey contribute "${NAME}_0001.zkey" "$FINAL" --name="halah-dev-2" -e="halah-dev-2-$(date +%N)"
  rm -f "${NAME}_0000.zkey" "${NAME}_0001.zkey"
fi
# The final key must belong to this r1cs and this phase one, whoever made it. Only then does it replace the key in use.
TRANSCRIPT="$(snark zkey verify "$NAME.r1cs" "$PHASE1" "$FINAL" 2>&1 | plain)"
echo "$TRANSCRIPT" | grep -q "ZKey Ok!" || { echo "$TRANSCRIPT"; echo "ZK DECISION BUILD FAILED: the key does not match the circuit and phase one"; exit 1; }
[ "$FINAL" -ef "$NAME.zkey" ] || cp "$FINAL" "$NAME.zkey"
[ -n "$ZKEY" ] || rm -f "$FINAL"
quiet snark zkey export verificationkey "$NAME.zkey" "${NAME}_verification_key.json"
if [ "$DEPTH" = 16 ]; then quiet snark zkey export solidityverifier "$NAME.zkey" ../../contracts/HalahDecisionVerifier.sol; fi

{ echo "HALAH decision circuit, setup record"
  echo "circuit: $NAME, tree depth $DEPTH, constraints $CONSTRAINTS, public inputs $PUBLIC, power $POWER"
  echo "phase one: $PHASE1_LABEL"
  echo "phase two: $PHASE2_LABEL"
  echo "sha256:"
  sha256sum "$NAME.r1cs" "$NAME.zkey" "${NAME}_verification_key.json"
  (cd "$(dirname "$PHASE1")" && sha256sum "$(basename "$PHASE1")")
  echo "zkey verify (circuit hash and the hash of every phase-two contribution):"
  echo "$TRANSCRIPT"; } > "${NAME}_setup.txt"
echo "ZK DECISION BUILD OK: $NAME, depth $DEPTH, $CONSTRAINTS constraints, phase one: $PHASE1_LABEL, phase two: $PHASE2_LABEL"
