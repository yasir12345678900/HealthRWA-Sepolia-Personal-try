const ATT=[
 {
  "id": "A1",
  "name": "Approval signed by a signer outside G",
  "comp": [
   "A"
  ],
  "before": "Accepted at unit level (blocked in the interface)",
  "after": "Refused"
 },
 {
  "id": "A2",
  "name": "Guardian signature replayed from another consent",
  "comp": [
   "I"
  ],
  "before": "Refused",
  "after": "Refused"
 },
 {
  "id": "A3",
  "name": "Same guardian approves twice to reach N",
  "comp": [
   "A"
  ],
  "before": "Accepted at unit level (blocked in the interface)",
  "after": "Refused"
 },
 {
  "id": "A4",
  "name": "Requested scope exceeds the authorised scope",
  "comp": [
   "P"
  ],
  "before": "Refused",
  "after": "Refused"
 },
 {
  "id": "A5",
  "name": "Request with an empty scope",
  "comp": [
   "P"
  ],
  "before": "Accepted at unit level (blocked in the interface)",
  "after": "Refused"
 },
 {
  "id": "A6",
  "name": "Request before notBefore or after expiry",
  "comp": [
   "T"
  ],
  "before": "Refused",
  "after": "Refused"
 },
 {
  "id": "A7",
  "name": "Requester declares a different jurisdiction",
  "comp": [
   "L"
  ],
  "before": "Refused",
  "after": "Refused"
 },
 {
  "id": "A8",
  "name": "Access after revocation",
  "comp": [
   "E"
  ],
  "before": "Refused",
  "after": "Refused"
 },
 {
  "id": "A9",
  "name": "Tampered Groth16 proof or public signal",
  "comp": [
   "E"
  ],
  "before": "Refused",
  "after": "Refused"
 },
 {
  "id": "A10",
  "name": "Honest proof generation for an expired consent",
  "comp": [
   "T"
  ],
  "before": "Refused",
  "after": "Refused"
 },
 {
  "id": "A11",
  "name": "Result field of a recorded audit event rewritten",
  "comp": [
   "E"
  ],
  "before": "Digest differs",
  "after": "Digest differs"
 },
 {
  "id": "A12",
  "name": "Mint or revoke by a non-owner, or token transfer",
  "comp": [
   "Contract"
  ],
  "before": "Refused",
  "after": "Refused"
 }
];
