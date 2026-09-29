# CA2 Report — Final A-to-Z Risk Review (post PRISMA rebuild)

Build: 195 pages, Figures 1–40, Tables 1–17, Equations (1)–(76), References [1]–[81] all cited, no vendor names, all-black submission copy validated.

## RED — must fix (all applied unless listed under 'needs the author')

- [ch1:F1] §Abstract — The rebuilt Chapter 2 reports 44 included primary studies [35]–[78] (Sections 2.3.6, 2.5, 2.6); 33 is the pre-rebuild count and contradicts the whole review.  → **applied**
- [ch1:F2] §Abstract — Chapter 2 (Section 2.5) retracts the claim that these conditions are absent; the gap is that they are not conjoined in one decision predicate with multi-party approval as a standing condition, so the abstract must state   → **applied**
- [ch2a:A1] §2.3.2 — Section 2.2, Chapter 3 (SRQ1 to SRQ6) and Chapter 1 (RO1 to RO6) all state six questions and objectives, so seven review questions cannot correspond one to one; the paragraph itself then maps Questions 6 and 7 jointly to  → **applied**
- [ch2a:A2] §2.3.7 — Orphan sentence left over from the old chapter: it opens Section 2.3.7 (data extraction) with 'this concern', which has no antecedent, and refers to the prototype, which is off-topic in the methodology section.  → **applied**
- [ch2a:A3] §2.3.7 — Second sentence of the same orphan paragraph ('these properties' has no antecedent); both sentences must be deleted so that 2.3.7 begins with 'The included studies were analysed using a predefined data extraction form'.  → **applied**
- [ch2a:A4] §2.3.4 — The report contains no threats-to-validity section (the phrase occurs nowhere in the built text), so the sentence points the examiner to a section that does not exist.  → **applied**
- [ch2b:B1] §2.4.7 — The author of [64] is cited as 'Hema et al.' everywhere else; the bare letter 'S' is a garbled surname that a marker would notice.  → **applied**
- [ch2b:B2] §2.4.7 — Same garbled surname for [64]; the five Req 4 with Req 5 studies are Eneh, Mei, Panagoulias, Punia and Hema [64].  → **applied**
- [ch2b:B3] §2.4.7 — Table 9 gives Punia et al. [61] ticks on Req 3, Req 4 and Req 5, so the statement that the only Req 3 triples are in [53] and [69] is contradicted by the table itself (Madine also forms Req 1/3/5 and Req 2/3/5).  → **applied**
- [ch2b:B4] §2.5.1 — Gap 6 contradicts Sections 2.4.2, 2.4.6 and 2.5, which state that Phuyal et al. [58] test allow and deny paths over 100 runs (Req7 Yes in the workbook, tick in Table 4).  → **applied**
- [ch2b:B5] §2.5.1 — Leftover of the earlier framing in which RO5 and RO6 were deferred; it lists only four dimensions and contradicts Chapter 1 (RO5 current, RO6 current/next), the preceding sentence about operational temporal and jurisdict  → **applied**
- [ch2b:B6] §2.5.1 — The closing sentence of 2.5.1 omits the temporal and jurisdictional conditions that Eq. (6) and Gap 5 make part of the decision; same old-framing leftover as B5.  → **applied**
- [ch2b:B7] §2.5.1 — This is labelled Eq. (6) but it is the first numbered equation in the whole report (no Eqs (1)-(5) exist; Chapter 3 starts at (7)); renumber it as (1) and shift the later equation numbers, or remove the number here, othe  → **applied**
- [ch34:F1] §3.1 — [19] (Data Trusts as a Service) describes subject-controlled policy access and provenance, not multi-approver mechanisms; the review's multi-party evidence is Madine [53], Punia [61] and Tan [69], and the sentence claims  → **applied**
- [ch34:F3] §4.7 — The same section (and Chapter 4 intro, 4.5, Table 11) states that the dynamic lifecycle controls of RO5 are already delivered in the current stage, so assigning 'dynamic lifecycle conditions' to the next stage contradict  → **applied**
- [ch5:C1] §5.1 — The name verify_poc appears only in Chapter 5; Section 6.8.9 calls it 'an independent verification tool' and never introduces verify_poc, so the cross-reference cannot be followed.  → **applied**
- [ch5:C2] §5.1.4 — Same broken cross-reference: verify_poc is not named anywhere in Chapter 6.  → **applied**
- [ch5:C3] §5.2 — Third occurrence of the undefined name verify_poc; Chapter 6 describes the tool without naming it.  → **applied**
- [ch6:C6-1] §6.3.2 — Eq. (55) ends in ALLOW although Step 13 and Algorithm 3 return ACTIVATED and the text states that activation is distinct from the access decision (ALLOW is the RO4 outcome).  → **applied**
- [ch6:C6-2] §6.3.2 — Same inconsistency: Authorisation(C) takes the values ACTIVATED or PENDING in Step 13 and in Algorithm 3, not ALLOW.  → **applied**
- [ch6:C6-4] §6.6 — Duplicated phrase makes the sentence ungrammatical; a marker would notice it immediately.  → **applied**
- [ch68:C2] §7.6 (consistency with 6.8) — Section 6.8.6 states that the EXPIRED state was not reached in the demonstration and Section 6.8 shows no live policy-violation case, so Chapter 7's claim that expiration and policy violation were demonstrated live contr  → **applied**
- [ch789:F1] §9.2 — Table 15 is the publication plan; the activities whose status is reported are the next-stage activities of Table 16.  → **applied**
- [ch789:F2] §Appendix A — In Section 6.4, Eq. (57) defines the scope predicate VS and the policy predicate VP is Eq. (58); citing only (57) points the examiner to the wrong equation (in the build source the cell reads 'Eq. (52)', i.e. the auto-re  → **applied**
- [ch789:F3] §7.4 — Section 6.8.4 shows only the positive path (a request that is a non-empty subset of the authorised scope); no live over-scope denial with VP named is demonstrated there, only in the automated tests of Section 6.8.9.  → **applied**
- [global:G1] §Abstract — The rebuilt Chapter 2 (2.3, 2.4, 2.5, 2.6, 3.1) and Figure 5 all state 44 primary studies; the Abstract still carries the old count of 33.  → **applied**
- [global:G2] §2.3.7 — Orphan paragraph: Section 2.3.7 (Data Extraction) opens with two sentences about the prototype and formal analysis that belong to no methodology context ('this concern' has no antecedent); delete this sentence and the fo  → **applied**
- [global:G3] §2.4.7 — Unfinished placeholder 'S' in the Table 9 observation; from Table 9 the sixth study with Req 1 and Req 4 both ticked is Hema et al. [64] (S30).  → **applied**
- [global:G4] §2.4.7 — Second unfinished placeholder 'S'; from Table 9 the fifth study with Req 4 and Req 5 both ticked is Hema et al. [64] (S30).  → **applied**
- [global:G5] §9.2 — Wrong table number: Table 15 is the publication plan (Chapter 8); the activities whose status is reported (temporal and lifecycle trust, comprehensive empirical validation) are the next-stage activities of Table 16.  → **applied**
- [global:G6] §6.7 — Contradiction: Sections 1.3, 4.5, 6.5, 7.5 and 9.2 state that temporal and lifecycle trust (RO5) has been brought forward into the current stage, yet 6.7 still attributes Eq. (70) to a CA3 extension.  → **applied**
- [global:G7] §6.7 — Garbled phrase ('formal dynamic validity') left over from the edit that moved RO5 into the current stage; the same sentence already says the current stage delivers dynamic validity.  → **applied**
- [global:G8] §2.5.1 / whole report — The built report contains no equations (1) to (5): numbering starts at (6) because the equations of the old Chapter 2 were removed, which an examiner will read as missing equations.  → **applied**
- [global:G10] §2.5 — The full-text pool is 1,800 records everywhere else (2.3.6, Figure 2, 2.6); 1,805 is the IEEE Xplore export count and contradicts the PRISMA chain.  → **applied**
- [refs:F1] §References — Entry [50] carries database-export debris ("(corresponding)", author affiliation, the year twice) and surname-first full names unlike every other new entry.  → **applied**
- [refs:F2] §References — Entry [76] contains an author affiliation, the year twice and full given names, none of which belong in a reference entry.  → **applied**
- [refs:F3] §References — Entry [75] pastes a raw catalogue string with editors, semicolons and the year twice; no other entry is formatted this way.  → **applied**
- [refs:F4] §References — The third author of [64] is truncated to bare initials (the PRISMA export had "H. S, G. B. Sai Reddy, and S. R"); a marker will read "R. S." as an incomplete author, and the entry is also filed under S instead of H in th  → **applied**
- [refs:F5] §References — Entry [68] is the only entry that gives a single author plus "et al."; the paper has six authors (ICAC 2023, pp. 792–797) and the list elsewhere prints up to six names before "et al."; the entry is also filed after Sooho  → **applied**

## YELLOW — recommended, applied

- [ch1:F3] §1.3 — Section 1.3 opens by referring to 'its four foundational dimensions' before any dimension has been introduced (they appear five paragraphs later), so the first two paragraphs read as misplaced; the re  → applied
- [ch2a:A5] §2.3.4 — sentinels.txt records eight misses with different causes (SEN-08 misses on block C, SEN-09 on the date range, SEN-12 is an OPEN ITEM), so the claim that every miss was diagnosed and attributed to the   → applied
- [ch2a:A6] §2.3.6 — The chapter's own figures give 2,895 minus 2,515 plus 65 minus 23 = 422 within-source duplicates; the 423 in the PRISMA chain (9,256 minus 8,833 loaded) is reached only with the one uncaptured IEEE re  → applied
- [ch2a:A7] §2.2.1 — The consent object is C = (I, A, P, T, L, E) in Chapters 1, 3 and 5 and in Section 2.6; the requirement definition omits the lifecycle component L although Req 5 (2.2.5) relies on it.  → applied
- [ch2a:A8] §2.1 — The overview still names the old review areas ('multi-party trust data governance', 'Trusted Computing') whereas the rebuilt Sections 2.4.1 to 2.4.6 follow the six requirements and treat trusted execu  → applied
- [ch2a:A9] §2.3.7 — The paragraph later states that quality items were not scored for studies excluded on document type, duplication or unavailability, which contradicts 'each study assessed at the full-text stage'.  → applied
- [ch2a:A10] §2.3.7 — codebook.txt (D-150) records that QA is scored for INCLUDE and for EC2, EC4 and EC9 exclusions only; EC1 exclusions also carry blank QA, which the current wording omits.  → applied
- [ch2a:A11] §2.3.7 — 'Tier A/B/C' is used in 2.3.6 for the 39/1,066/695 full-text priority tiers and in 2.3.7 for the evidence tiers of included studies; without a distinction the reader may equate the 39 priority Tier A   → applied
- [ch2a:A12] §2.3.6 — An examiner will compute 1,800 minus 64 assessed minus 1 unretrieved and expect the chapter to state explicitly that most full texts were not read and that the corpus is a saturation-bounded checkpoin  → applied
- [ch2a:A13] §2.2.4 — The empirical claim 'most unauthorised disclosures' is uncited and unsupported by any reference in the list; softening to 'many' and anchoring it to the RQ-UCON study [11], which is motivated by physi  → applied
- [ch2b:B8] §2.4.5 — Section 2.5 and Gap 5 state that Madine [53] and Punia [61] also enforce time inside the decision (Req 5 Yes in 8 studies), and both are multi-party, so 'the three systems ... all single-party' contra  → applied
- [ch2b:B9] §2.5 — Section 2.4.3 and Table 5 describe [43] as a commercial, centralised platform used by three genomic medicine centres, so 'national platforms' misstates the evidence for Ekholm; see B9b for the co-sign  → applied
- [ch2b:B9b] §2.5 — Section 2.4.3 describes Hagström [47] as proxy-access governance gated by a professional's assessment and the minor's consent, not as guardian co-signature at registration; the synthesis overstates th  → applied
- [ch2b:B10] §2.5 — Sections 2.3.6 and 2.6 consistently report 1,800 full texts sought; 1,805 is the workbook's pre-deduplication signal-scan count and reads as a numerical inconsistency.  → applied
- [ch2b:B11] §2.4.3 — The classes are introduced in the order first, second, fifth, fourth, third, sixth; renumbering Punia's class as third (and Zhao and Su's as fifth, see B12) restores a sequential enumeration of the si  → applied
- [ch2b:B12] §2.4.3 — Companion to B11: with this change the six mechanism classes are numbered one to six in the order in which they are presented.  → applied
- [ch2b:B13] §2.5 — Section 2.4.5 states that a post-revocation denial is demonstrated by [58], [57], [44], [45] and [68]; the synthesis silently drops Eneh [44], whose evidence note records 'denied again once rule revok  → applied
- [ch2b:B14] §2.5.1 — 'rather than deferred to subsequent research' refers to a deferral that no longer exists anywhere in the report (Chapter 1 lists RO5 as current) and reads as a patch on the old text.  → applied
- [ch2b:B15] §2.6 — An examiner expects a PRISMA-reported review to state its limitations; the chapter describes the pending abstracts and the saturation rule in 2.3 but never states them as limitations of the conclusion  → applied
- [ch34:F2] §3.1 — The single-party finding concerns the SLR objects [71, 37, 44, 58, 66] and is made in Section 2.5; [10] (web consent receipts), [13] and [21] do not show that those objects are single-party and are no  → applied
- [ch34:F4] §3.2 — Section 3.2 opens with a status paragraph whose second sentence begins 'Consequently' without a premise and precedes the research question it qualifies; the lead-in makes the paragraph read as an inte  → applied
- [ch34:F5] §3.3.1 — Section 2.5.1 (Gap 1) already requires the validity interval and the jurisdiction as components of the consent object, so stating that T and L were merely 'introduced during implementation' breaks the  → applied
- [ch34:F6] §3.3.1 — Chapter 2 places jurisdiction under Req 4 / Gap 4 ('evaluated together with the jurisdiction on every request'), whereas this sentence assigns L to SRQ5 only; the replacement reconciles the two chapte  → applied
- [ch34:F7] §3.1 — Section 2.5 and 2.6 name the two gaps and stress the patient-defined approving set, but the gap statement in 3.1 neither uses the names nor mentions who defines G, so the link between Chapter 2 and Ch  → applied
- [ch34:F8] §3.3.3 — Av is introduced without any relation to the guardian set G defined in Section 3.1 and used in Chapter 6 (where 1 ≤ N ≤ |G| is stated), so the threshold notation is not fully defined here.  → applied
- [ch34:F9] §4.5 — Section 9.2 lists consent modification, delegation and guardian-set changes as next-stage RO5 extensions, which is more than 'hardening'; the two statements of remaining RO5 work should agree.  → applied
- [ch34:F10] §4.7 — Sections 7.6 and 9.2 state that a systematic performance and overhead study also remains for the next stage; 4.7 omits it, so the remaining agenda is stated inconsistently across chapters.  → applied
- [ch34:F11] §4.7 — Chapter 4 derives the objectives from the questions but never closes the RQ-gap-RO chain that Chapter 2 (Section 2.6) promises; one sentence makes the traceability explicit for the examiner.  → applied
- [ch34:F12] §3.3.5 — Chapter 6 uses VS(C, R) for data scope (Eq. 57) and VS(C, t, q) for lifecycle, and explains the clash there, but Chapter 3 introduces VS as the lifecycle predicate without warning, so a reader moving   → applied
- [ch5:C4] §5.1 — SQLite is never mentioned in Chapter 6 or Section 6.8, which refer only to 'the audit ledger' or 'the local ledger'; naming a storage technology here that the implementation chapter does not confirm i  → applied
- [ch5:C5] §5.3 — This new sentence opens Section 5.3 before any representation has been introduced, so 'this representation' has no antecedent and the paragraph reads as misplaced.  → applied
- [ch5:C6] §5.3 — Section 2.4.3 defines six mechanism classes and places Tan et al. [69] in the witness/notary class and Punia et al. [61] in the custodial M-of-N class, so the four-group summary here contradicts the C  → applied
- [ch5:C7] §5.2 — The new sentence is inserted between the lead-in 'when the threshold condition of Eq. (33) holds' and Eq. (33) itself and reads as a bare figure description; tying it to Figure 9 and Eq. (33) makes it  → applied
- [ch5:C8] §5.2 — Section 6.8.4 states that the proof is generated and verified as part of the cryptographic verification performed before access is granted, not after an ALLOW decision has already been reached.  → applied
- [ch5:C9] §5.1.1 — The subsection opens with 'therefore' and 'the two additional functions' before the six conceptual functions have been introduced, so the reader cannot tell what the eight are additional to.  → applied
- [ch5:C10] §5.3 — Reference [10] (Jesus and Pandit) proposes web consent receipts, not immutable ledger records; [28] (Tawfik et al.) surveys blockchain-based access control and auditability and supports the claim dire  → applied
- [ch5:C11] §5.11 — The sentence is immediately followed by the statement that the Model 'already includes' temporal validity, revocation and lifecycle transitions and that the Controller 'already evaluates' VT and VL, w  → applied
- [ch5:C16] §5.3 — Section 5.1.1 lists a Lifecycle component and Section 6.5 evaluates State(C), but C = (I, A, P, T, L, E) has no lifecycle element; an examiner will ask where the lifecycle state lives in the model.  → applied
- [ch6:C6-3] §6.6.2 — Step 13 of the RO6 procedure re-uses ALLOW for the RO3 activation outcome; Algorithm 3 returns ACTIVATED.  → applied
- [ch6:C6-5] §6.5 — The sentence is left dangling ('conditions that') before Eq. (63); the equation needs a proper lead-in.  → applied
- [ch6:C6-6] §6.7 — Calling Eq. (70) 'the CA3 extension' contradicts the preceding sentence that Algorithms 1–5 are realised in the current prototype and the following sentence that the implemented system enforces Eq. (7  → applied
- [ch6:C6-7] §6.7 — 'Formal dynamic validity' is garbled and contradicts the same sentence, which says dynamic validity is already established in the current stage; Chapter 3 assigns only the formal component of RO6 to C  → applied
- [ch6:C6-8] §6.3.3 — The body of Algorithm 3 uses g, siga, domain, addrp and addrr, none of which is introduced in the Require line.  → applied
- [ch6:C6-9] §6.1.2 — Algorithm 1 requires L and constructs C with it, and the procedure and the sequence Ip → D → G → Pu → SC → T → L → A validate L, but no line of the algorithm validates L.  → applied
- [ch6:C6-10] §6.4.3 — Algorithm 4 declares R = (u, PR, SR, Jur(R)) and line 27 tests Jur(R), but Step 1 of the procedure defines R without the jurisdiction element. (If PR is a subscript in the source, adjust the matched s  → applied
- [ch6:C6-11] §6.4.3 — The prose lists five conditions while the formula that follows in the same step contains seven conjuncts including (ts ≤ t ≤ te) and (Jur(R) = Jur(C)).  → applied
- [ch6:C6-12] §6.4.3 — This closing rule omits the temporal and jurisdictional conditions that Eq. (59), Step 7 and Algorithm 4 (lines 26–27) all enforce, so the section contradicts itself.  → applied
- [ch6:C6-13] §6.4.3 — Companion to C6-12: the 'respectively' list must match the extended conjunction.  → applied
- [ch6:C6-14] §6.5.2 — Eq. (18) is VS(C) = ValidState(C) ∧ ValidTransition(C) and contains no temporal term; Chapter 3 itself says Section 6.5 'additionally' adds the temporal condition, so the cross-reference misdescribes   → applied
- [ch6:C6-15] §6.3.2 — The sentence is ungrammatical, and it compares a participant u with a set of approvals a (Step 7 adds a, not u, to Av).  → applied
- [ch6:C6-16] §6.5.2 — The sentence following the displayed flow begins in lower case and reads as a fragment; it should start a new sentence (also 'overall ... overall' in the preceding sentence).  → applied
- [ch6:C6-17] §6.4.1 — Eqs. (60)–(62) apply ⊈ to SC and SR, so both must be written as sets; the built text shows no braces (apply the same change to Eq. (61): SR = {Observation, Medication, Procedure}).  → applied
- [ch6:C6-18] §6.4.3 — Algorithm 4 line 28 introduces a Groth16 proof that is never explained in the RO4 procedure or workflow; an examiner would ask what the proof is and why it appears in the decision.  → applied
- [ch68:C1] §6.8.1 — mintConsentV3 takes the purpose as a plaintext string in calldata (contracts/ConsentSBTv3.sol line 38, blockchain/contract.py line 174), so the claim that the plaintext purpose 'remains in the applica  → applied
- [ch68:C3] §6.8.10 — The screenshots (Figures 17 to 40) precede Table 14; nothing follows it, so the sentence misdescribes the structure of the section.  → applied
- [ch68:C4] §6.8.6 — RO5 claims enforced temporal expiration, but 6.8 says only that EXPIRED was not reached; the examiner needs to know where the expiry path is evidenced.  → applied
- [ch789:F4] §9.1 — Sections 7.2, 7.3, 7.6 and 6.8.11 state that k-of-n thresholds, DID resolution and a performance study remain future work, so 'no further development' and the omission of the performance study contrad  → applied
- [ch789:F5] §9.2 — The status sentence names an activity ('Temporal and lifecycle trust') that is not a row of Table 16, and does not say which part of the first row remains outstanding.  → applied
- [ch789:F6] §9.2 — The status report covers only two of the four Table 16 activities and uses an em-dash fragment inconsistent with the surrounding prose; an examiner expects every planned activity to carry a status.  → applied
- [ch789:F7] §Appendix A — Every other row is labelled by RO/RQ with its equation and algorithm; 'RO5 direction' implies RO5 is not a delivered objective, contradicting Sections 4.5, 7.5 and 9.1 which report it as largely compl  → applied
- [ch789:F8] §Appendix A — Consistency of the traceability table: the row should name the RO/RQ, the defining equation and the algorithm as the other rows do, and state explicitly that the formal half is outstanding.  → applied
- [ch789:F9] §7.6 — The sentence repeats Eq. (80) verbatim a few lines below it; the duplicated rule reads as an editing remnant.  → applied
- [ch789:F19] §7.6 — Chapter 7 has neither an introduction nor a closing summary of the six statuses; an examiner expects one consolidated statement that matches Chapter 4 and the abstract before the plan in Chapter 9 rel  → applied
- [ch789:F20] §9.2 — The plan defines metrics for the performance study but no success criterion for the formal assurance work, which is the principal remaining objective; the examiner needs to know what 'formal assurance  → applied
- [global:G9] §2.4.1 — 'Eq. (5)' refers to an equation inside Sawant and Gomes [65], but in this report it reads as a reference to the report's own (non-existent) equation (5); the same wording in Table 3 ('decision functio  → applied
- [global:G11] §6.6 — Duplicated words ('each conjunct ... each conjunct') make the sentence ungrammatical.  → applied
- [global:G12] §6.5 — Orphan equation lead-in: the sentence breaks off ('conditions that') before Eq. (63).  → applied
- [global:G13] §2.1 — Section 1.3 explicitly distinguishes the report's 'Trust Computing' from hardware 'trusted computing' and states that the latter lies outside the scope of the review in Chapter 2; the Overview then na  → applied
- [global:G14] §2.3.2 — Seven review questions cannot correspond one to one with six sub-research questions; the following paragraph itself explains that Questions 6 and 7 jointly map to Req 6.  → applied
- [global:G15] §2.4.3 — The six mechanism classes are presented in the order first, second, fifth, fourth, third, sixth; renumbering in reading order (with G16) removes an apparent error.  → applied
- [global:G16] §2.4.3 — Companion of G15: after renumbering, the delegated threshold of Zhao and Su becomes the fifth class so that the classes run first to sixth in order.  → applied
- [global:G17] §6.8.10 — Orphan lead-in: the colon introduces nothing (a page break follows); in the next sentence 'and it is followed by the screenshots of each subsystem' is also wrong because the screenshots precede Table   → applied
- [global:G18] §5.1.2 / 5.1.3 — Section 3.3 states that SRQ1–SRQ6 are referred to as RQ1–RQ6 in Chapter 4 and all remaining chapters, but Chapter 5 mixes SRQ (5.1.2, 5.1.3 and the mapping line SRQ1 → Model ...) with RQ (5.11); repla  → applied
- [global:G19] §2.6 — The eighth frozen query is the Google Scholar query itself (GS-M v2), and 2.3.6 attributes the 9,256 records to the seven database searches only; 'eight searches ... supplemented by' double-counts.  → applied
- [global:G20] §2.3.8 — Figure 3 (and likewise Figure 4, whose lead-in should be added after 'correspond to Req 1 to Req 6 respectively.' in Section 2.4) is never referred to in the text; every figure in the rebuilt chapter   → applied
- [global:G21] §2.6 — Figure 5 is never cited in the text. (Figures 12 to 15 and the screenshots 17 to 40 are likewise never cited by number; Chapter 6 relies on 'the figure above/below', which is tolerable but weaker.)  → applied
- [refs:F6] §References — Trailing double full stop after "et al." appears in eight new entries ([43], [51], [53], [57], [61], [67], [71], [77]); apply the same replacement to every occurrence.  → applied
- [refs:F7] §References — Entry [43] mixes initial-surname and surname-initial ordering within one author string.  → applied
- [refs:F8] §References — Entry [47] mixes author-name ordering and ends the author list with a double full stop.  → applied
- [refs:F9] §References — Entry [56] uses surname-comma-given-name full names, unlike every other entry in [35]–[81].  → applied
- [refs:F10] §References — Entry [67] mixes author-name ordering and has a double full stop.  → applied
- [refs:F11] §References — Entry [69] is surname-first with a double full stop; the body cites it as "Tan et al.".  → applied
- [refs:F12] §References — Entry [71] mixes author-name ordering and has a double full stop.  → applied
- [refs:F13] §References — Entry [73] is surname-first with a double full stop.  → applied
- [refs:F14] §References — Entry [74] has one surname-first author in an otherwise initial-first list and a double full stop.  → applied
- [refs:F15] §References — Entry [80] is surname-first with a double full stop and prints the journal in capitals, whereas [37] prints the same journal as "JMIR Medical Informatics" and [58], [59], [79] print the same authors i  → applied
- [refs:F16] §References — Missing spaces after initials in [42]; the venue string of the same entry is also truncated ("... Computational Intelligence Tech") and should read "... Computational Intelligence Technologies (ETAACT  → applied
- [refs:F17] §References — "(Nature Publisher Group)" is a ProQuest export artefact, not part of the journal name.  → applied
- [refs:F18] §References — Entry [46] is the only entry with an abbreviated journal name; all other journal names are written in full.  → applied
- [refs:F19] §References — The author string of [48] reads as given names treated as surnames (e.g. "G. Hancheng"), which would make the in-text "Hancheng et al." attribution wrong; the ACM page could not be reached from the au  → applied

## GREEN / KEEP — cosmetic or optional; left as is

- [ch1:F4] §Title page — The report is to be submitted at the end of September 2026; the title-page date should match the submission month (author to confirm the exact month required by the CA2 timetable).
- [ch1:F5] §1.3 — The abstract and Section 1.3 refer to 'the consent object' but Chapter 1 never introduces the notation C = (I, A, P, T, L, E) used throughout Chapters 3 to 7.
- [ch1:F6] §1.3 — An examiner expects the introduction to state the contributions explicitly; Chapter 1 currently states motivation and scope but no contribution statement.
- [ch1:F7] §1.1 — The cited works cover blockchain surveys and DID/VC, but none of them addresses policy-based access control, which [28] (blockchain access control in healthcare) and [25] (RBAC/ABAC/context-aware acce
- [ch1:F8] §1.1 — [9] is a nursing survey on confidentiality and care coordination and does not discuss guardians or institutional authorities in authorisation decisions; [31] (paediatric guardian access) supports the 
- [ch1:F9] §Abstract — Chapter 7 grades RO5 as 'Largely Completed' (modification and delegation outstanding), which the abstract itself acknowledges in its final sentence; the wording should match Chapter 7.
- [ch1:F10] §Contents — A thesis-style report with forty figures and fifteen tables is expected to carry lists of figures and tables; this is a front-matter addition rather than a sentence.
- [ch2a:A14] §2.2.2 — The statement that DIDs and VCs enable identification without a central identity provider is a technical claim that the DID/VC survey [20] and the SSI review [16] directly support.
- [ch2a:A15] §2.1 — The overview never states the size or the period of the corpus, so a reader of 2.1 does not learn until 2.3 that the chapter rests on 44 PRISMA-selected studies rather than on the background reference
- [ch2a:A16] §2.3.8 (Figure 3 caption) — Section 2.3.8 and the 2.4 introduction say a study is placed in the stream of its principal contribution, whereas the caption says strongest coded requirement; the two rules are not identical (e.g. S1
- [ch2a:A17] §2.3.1 — No version 'v1.1' of the protocol is recorded in the workbook files (searchlog, codebook, decision log); the version label cannot be traced and adds nothing.
- [ch2a:A18] §2.3.3 — The printed master query is wrapped in an extra pair of double quotation marks (opening before the first parenthesis and closing after the last), which is not part of the string executed in IEEE Xplor
- [ch2a:A19] §2.2.1–2.2.6 — The six sub-headings of 2.2 write 'Req: 1' to 'Req: 6' with a colon, whereas the rest of the chapter, Table 2 and Tables 3 to 9 write 'Req 1'; the same change applies to the other five headings.
- [ch2b:B16] §2.4.7 — Gap 5 lists five studies with decision-time temporal enforcement; the comparative analysis lists three, which is inconsistent though not wrong.
- [ch2b:B17] §2.6 — C = (I, A, P, T, L, E) has six components and Chapter 3 places the active or revoked state inside E; listing lifecycle state as a separate component gives eight items for a six-tuple.
- [ch2b:B18] §2.5.1 — Section 2.6 and Chapter 3 call them sub-research questions (SRQ1 to SRQ6); apply the same change to RQ2 to RQ6 in Gaps 2 to 6 if the SRQ label is the one retained in Chapter 3.
- [ch2b:B19] §2.4 — [17] (Li et al. 2026) is a TEE-enabled, Byzantine-resilient blockchain consensus paper for smart agriculture; 'data integrity' is a loose description of what it contributes.
- [ch2b:B20] §2.4.3 — The paragraph above says the panel recorded Al Amin [38] as a candidate class only, so listing it inside one of the six ratified forms without qualification is mildly inconsistent.
- [ch34:F13] §3.3.5 — Equation (17) names conceptual stages that differ from the six implemented states listed in Section 6.5.2; a mapping sentence prevents the examiner reading them as two different state machines.
- [ch34:F14] §3.4 — Equation (29) is only defined later in Section 4.7, so the forward reference should say where it is.
- [ch34:F15] §3.3 — Section 2.5.1 already refers to 'research question RQ1 of Chapter 3' etc., so the abbreviation is used before this sentence introduces it.
- [ch34:F16] §4.3 — Sections 4.3 to 4.6 each open with an implementation-status paragraph before the objective itself is stated; the lead-in signals that the paragraph is a status note so the ordering reads as deliberate
- [ch5:C12] §5.1 — The threshold itself is defined in Eq. (33)/(37) of Sections 5.2 and 5.3, Section 5.6 defines the verified approval set, and the EIP-712 verification is in Section 6.8.3, so the cross-references shoul
- [ch5:C13] §5.1.2 — The preceding paragraph already states that lifecycle validity and revocation are evaluated within VA; the repetition in consecutive paragraphs reads as duplicated text.
- [ch5:C14] §5.8 — Missing hyphen/space in 'roleverification' (verify in the source, since it may be a layout artefact).
- [ch5:C15] §5.1.1 — The text later says the Controller 'is decomposed into six principal security functions'; the author should confirm that the Figure 7 image actually shows eight Controller functions, otherwise the cla
- [ch5:C17] §5.4 — The View section never states how the View layer is realised in the prototype, whereas Sections 5.1 and 5.3 now link the Model and Controller to Section 6.8; the mapping is needed for consistency with
- [ch5:C18] §5.9 — The architectural security properties are never linked to an evaluation criterion; Section 6.8.9 reports 23 automated tests covering per-dimension failures, and the link is what an examiner expects be
- [ch6:C6-19] §6.4 — Eq. (59) uses VT and VL before they are defined (Eqs. (63) and (64)); a forward reference is needed.
- [ch6:C6-20] §6.2.2 — 'This condition' has no clear referent because the paragraph is placed after Step 7 while 'the four conditions above' belong to Step 4.
- [ch6:C6-21] §6.4.2 — Section 6.4.2 opens directly with the listing and reverses the procedure-then-algorithm order used in 6.1–6.3 and 6.5; a one-sentence lead-in removes the abrupt start.
- [ch6:C6-22] §6.6.2 — Subscripts T and L collide with the temporal (T) and jurisdictional (L) components of C used throughout the chapter; N (threshold) and Q (lifecycle transition q) avoid the clash.
- [ch6:C6-23] §6.4.3 — This paragraph repeats the RO3 statement of Section 6.3 inside the RO4 procedure without a cross-reference.
- [ch6:C6-24] §6.1.1 — The component A of C is named the authorisation component elsewhere in Section 6.1; 'authority' is the RO2 notion.
- [ch68:C5] §6.8.5 — The negative demonstration depends on a self-declared jurisdiction; stating the limitation where the evidence is presented pre-empts the obvious examiner objection (the limitation currently appears on
- [ch68:C6] §6.8.11 — The blue VI sentence follows the performance paragraph, so 'in the same way' has no antecedent and reads as an insertion; the content itself is consistent with Section 7.2.
- [ch68:C7] §6.8.9 — Chapter 5 states that 'the independent verifier verify_poc [is] described in Section 6.8', but Section 6.8 never names the tool, so the forward reference cannot be resolved by the reader.
- [ch68:C8] §6.8 (introduction) — Figure 8 (trust-predicate evaluation), cited in the same sentence, is in Section 5.1.2, not in Chapter 6.
- [ch68:C9] §6.8.4 — 'This section' is ambiguous (6.8.4 versus 6.8); Chapter 7 already cites Section 6.8.11 for the same limitation.
- [ch68:C10] §6.8.6 — Section 6.1 defines E as authorisation evidence and Table 14 labels the row 'Authorisation Evidence / Revocation (E)'; 'Enforcement State Management' is a name used nowhere else.
- [ch68:C11] §6.8.10 — The colon introduces nothing (a page break and then the Table 14 sentence follow), leaving a dangling sentence.
- [ch68:C12] §7.4 (consistency with 6.8) — Section 6.8.4 states the non-empty-subset rule but shows no over-scope request being refused, so 'demonstrated' overstates what 6.8 presents (fix belongs to the Chapter 7 reviewer).
- [ch68:C13] §6.8.1 — Optional: [28] (Tawfik et al., blockchain-based access control survey) supports the traceability role; the chapter's only citation, [20] for DIDs, is correct and sufficient otherwise.
- [ch68:C14] §6.8.4 — Figure 28 reproduces Figure 8; making the repetition explicit avoids the impression of a new artefact (an examiner may prefer a cross-reference to a repeated figure).
- [ch789:F10] §7.1 — The five studies are exactly the Req 1 = Yes evaluable consent objects of Chapter 2 and none has a guardian set or threshold, so the citation is correct; however [44], [58] and [66] already carry vali
- [ch789:F11] §9.2 — Eq. (81) drops the time argument that Eq. (80), Eq. (59) and Eq. (65) carry, although the sentence that follows explicitly includes the temporal condition; the numbered equation should match the imple
- [ch789:F12] §7.2 — The N-of-N limitation is stated in full both here (RO2 section) and at the end of Section 7.3; the RO2 section should only cross-refer, since the limitation belongs to RO3.
- [ch789:F13] §7.1 — The component-by-component description of C omits T and L, which are then explained in a detached sentence after the paragraph's concluding statement; moving that sentence here keeps the six component
- [ch789:F14] §7.1 — Dangling sentence after the section's concluding statement; it becomes redundant once F13 is applied (apply only together with F13).
- [ch789:F15] §8 — The third planned paper is titled Formal Security and Lifecycle Analysis, but its thesis alignment names only Section 6.6; lifecycle trust is defined in Section 6.5.
- [ch789:F16] §9.2 Table 16 — 'Benchmark datasets' is not an outcome planned anywhere else in the report (all evaluation uses synthetic records), whereas the performance metrics listed in the preceding paragraph are not reflected 
- [ch789:F17] §9.2 — Table 16 lists the lifecycle extensions first, whereas the text schedules them last; a one-clause acknowledgement prevents an examiner reading the table order as the timeline.
- [ch789:F18] §Appendix A — Caption is placed below the table whereas Tables 10 to 16 carry their captions above; move the caption above the table for consistency (text unchanged).
- [ch789:F21] §8 — The publication plan describes the first paper as 'Almost Ready' while Chapter 7 records prototype limitations; a sentence tying the paper's claims to those limitations pre-empts an examiner's concern
- [ch789:F22] §9.2 — Checked against S_full.txt: [13] (Khalid et al., dynamic consent management with decentralised controllers) and [24] (Narkhede et al., dynamic and granular consent frameworks) both support the phrase;
- [global:G22] §1.3 — Section 1.3 opens with 'has also been extended' before the four foundational dimensions have been introduced, and the same RO5 content is repeated later in the section ('In addition, trust cannot be r
- [global:G23] §3.2, 4.3-4.6, 5.1.1, 5.3 — In each of these sections the prototype status is stated before the research question, objective or model it refers to has been introduced, so the opening paragraph reads as an orphan ('therefore', 't
- [global:G24] §2.3.1 / 2.3.6 / 2.3.7 / 2.4.6 — 'PRISMA 2020 master workbook' is a recognised way of describing the spreadsheet in which PRISMA screening records are kept and does not read as tooling; the repeated 'workbook requirements Req1 to Req
- [global:G25] §2.4 / 2.4.3 — [34] is the PRISMA 2020 statement, not a background survey; the same range appears in 2.4.3 ('based on the background corpus [1]–[34]') and should also read [1]–[33].
- [refs:F20] §References — Stray space inside a hyphenated initial (IEEE export artefact).
- [refs:F21] §References — The visible inconsistencies between the blocks are: DOI present only in [35]–[81]; full given names in [1]–[34] versus initials in [35]–[81]; volume/issue/pages present in [1]–[34] but absent from alm
- [refs:F22] §References — Mixed title-case and sentence-case titles are the most visible stylistic inconsistency in the list, but each title is copied as published and the fix is optional.
- [refs:F23] §References — A series name without a conference or volume does not let a reader locate the paper without the DOI; the DOI mitigates this, so the fix is optional.
- [refs:F24] §2.3 — The list is alphabetical within [1]–[34] and again within [35]–[81] with [34] (Page et al., PRISMA) appended out of order and [64] and [68] misfiled; a numbered list ordered this way is unusual but ha

## Needs the author personally before submission

1. Reference [64]: confirm the third author's surname on IEEE Xplore (record 11485301).
2. Reference [68] (Ranaweera et al.): confirm the six co-authors from the ICAC 2023 record; the export was garbled.
3. Reference [48]: confirm author name order against the ACM record (10.1145/3771992).
4. Title page date 'August 2026' versus transaction evidence dated 24 September 2026.
5. Main research question (Section 3.2): reviewers suggest adding 'verify'; left unchanged because it is the registered question.
6. The review panel of Section 2.3.1 is described as a six-member panel with a chair — be ready to explain who performed the coding if asked.
7. The full-text pool: 64 of 1,800 records assessed at the D-166 checkpoint (stated honestly in 2.3.6 and 2.6) — confirm with the supervisor that reporting 'as at checkpoint' is acceptable.
8. Earlier standing items: Sepolia links open, PRISMA counts match the workbook (they do now), search logs archived, Welzel [21] read.