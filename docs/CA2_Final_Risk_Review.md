# CA2 Report — Final A-to-Z Check (figures, tables, algorithms, equations, references, code, style)

Build: 190 pages. Figures 1–40, Tables 1–17 and Equations (1)–(76) are in sequence; references [1]–[81] are all cited in the body; the submission copy is all black and validates. Colour convention of the review copy: **pink = a fix to existing text, blue = added content**.

Twelve reviewer passes were run over the previous build (figures, algorithms, equations, references, five style passes, two long-sentence passes). 275 items were curated; 173 applied automatically and the rest by hand after re-anchoring. Everything below is applied in both copies unless it is marked as the author's decision.

## RED — defects that had to be fixed (applied)

- Equation (10) was missing from the built report (a legacy override attached to it suppressed the equation). It now reads V_T(C, t) = 1 if t_s ≤ t ≤ t_e, 0 otherwise, directly after "Temporal validity is defined as".
- Equation (59) was missing for the same reason: "The jurisdictional condition can be expressed as" was followed by the where-clause only. It now reads V_L(C, R) = 1 ⟺ Jur(R) = Jur(C) ∨ Jur(C) = ∅.
- Section 7.4: the where-clause of Eq. (73) came before the equation, and a leftover "Status: Completed. S_R, and the request…" paragraph sat at the end. Order is now lead-in → Eq. (73) → where-clause → example → closing paragraph, with the Status line under the heading as in every other section.
- Section 7.5 had no Status line. Added: "Status: Largely Completed (temporal validity and on-chain revocation enforced; consent modification, delegation and guardian-set changes outstanding)".
- Section 6.4.1: "Figure 14 presents this workflow." had been inserted inside "For example, if … (55) … (56)". Moved before the example.
- Twelve doubled passages left by the previous apply pass were removed (Sections 1.2, 2.3.2, 2.4.1, 2.4.2, 2.4.3 closing argument, 2.4.4, 2.5 Gaps 2 and 4, 3.1, 4.6, 5.3, 6.1, 6.5.2, 6.6, 6.8.7, 7.2, 7.6, and the deployment paragraph of 6.8.2). Two truncated paragraphs (1.4 scope note; 2.3.2 review-question note) were restored from the backup.
- Algorithm 3 now matches the code: a failed guardian identity/authority check records the invalid approval and returns DENY; on reaching the threshold a local token identifier is recorded and the consent becomes ACTIVE once t_s is reached; the on-chain confirmation replaces the local identifier; reconciliation runs on request from the guardian view, not "on next lookup".
- Section 6.7 algorithm status now says Algorithms 1, 3 and 4 are realised, Algorithm 5 except its transition check (lines 16–20), Algorithm 2 in structural form, and the empirical branch of Algorithm 6 executed.
- Decision(C, R) written where the time-dependent rule is meant: Eqs. (11), (16), (18) and (76) now write Decision(C, R, t).
- Section 6.1: the where-clause of C = (I, A, P, T, L, E) now lists I, A, P, T, L, E in order in one sentence; the bolted-on "In addition, I represents…" sentence is gone.
- Section 7.3: Eq. (69) is now introduced as "defined in Eq. (49)" instead of being restated without reference.
- Section 4.6: the duplicated RO6 statement and the orphan "signature rejection and proof tampering; …" fragment are removed.

## YELLOW — layout and figure items (applied)

- Table 2: Study, Ref. and Role columns widened; no more "Stud y", "Ref ." or "Supportin g" wraps.
- Tables 14 and 17: captions moved above the table in the standard "Table n: …" style used everywhere else.
- Tables 3–9 and the legend: the tick is now ✓ (U+2713) instead of √ (square root sign).
- Figure 17: the Remix AI assistant panel, the "Upgrade / Get AI Credits" bar and the status bar are cropped out. Figure 20: the Etherscan sponsored banner is cropped out. Figure 25: the half-cut title line is cropped. Figure 40: white space added under the clipped result strip.
- References [1]–[34]: middle initials now carry stops (Jan F. Nygård, Daniel C. Park, …) so the two halves of the list use the same style.

## STYLE — author's voice (applied)

- All remaining semicolon chains and 45–60-word sentences flagged by the two long-sentence passes are split (abstract, 2.4.1–2.4.5, 2.5, 6.2.2, 6.4.3, 6.5.3, 6.7, 6.8.2, 7.5). No "so that … rather than …" closers, no parenthetical asides in the running text.

## Author's decisions (not changed)

- Cover date "August 2026" while Section 2.3 reports searches on 24–25 August and a workbook checkpoint of 10 September 2026 and an ACM search on 5 September. If the cover is the submission month, change it to September 2026.
- "Six review roles" in 2.3.1/2.3.7: the workbook shows six agent roles operated and ratified by the author. The text says so; confirm with the supervisor that this wording is acceptable.
- PRISMA checkpoint and the 25-study analysed set (23 core + Albalwy [37] + Li [51]): confirm with the supervisor.
- Code-versus-text caveats kept in the text as limitations: V_I is a structural DID check; the Poseidon commitment is held in the application record, not on-chain; the prover and verifier run on the same server; k-of-n thresholds are not configurable (N = |G|).
- Figures 25, 38 and 40 are screenshots with low resolution in the source; they cannot be sharpened without recapturing them.

## Checks on the final build

- Marker leaks 0; references [1]–[81] all cited; Table/Figure captions 1–17 / 1–40 exactly once each; equations (1)–(76) without gaps; no vendor or tool names; docx validation passed for both copies; submission copy contains only black (000000) and the grey (555555) used for table notes.

## Addendum — corpus restated as 25 included studies (author's instruction)

- The review corpus is now the 25 primary studies (23 core + Albalwy [37] + Li [51]). The other 19 reports that passed the full-text screen are "supporting references": coded, cited in the supporting-reference paragraph of each stream, kept in the reference list, but outside the corpus and outside Tables 2–9.
- Figure 2 (PRISMA): final box now reads 25 included, 19 supporting references, 3 secondary. All upstream counts unchanged (64 assessed − 17 excluded = 47).
- Figure 3: year distribution and stream counts recomputed over the 25 (2020: 3, 2021: 1, 2023: 3, 2024: 3, 2025: 5, 2026: 10; streams 2/3/8/4/4/4; sources Scopus 13, IEEE Xplore 10, ProQuest 2).
- Figure 5: requirement counts recomputed over the 25 (Req 1: 12, Req 2: 7, Req 3: 6, Req 4: 10, Req 5: 8, Req 6: 4).
- Table 2: 25 rows, labels S1–S25, Role column removed. Tables 3–9: study labels renumbered S1–S25 to match.
- All coding counts in 2.4 and 2.5 recomputed over the 25 (T2 10/15; T3 6/4/15; T4 11/10/4; T5 8, T6 7; Req 1 12/13; Req 2 7/18; Req 4 10/11/4; Req 5 8/13/4; Req 6 4/9/12; Req 7 5/19/1; combined Req 6 tick 9; purpose-of-use in the decision 6 of 25 plus one supporting reference).
- Abstract, Section 2.6 conclusion and Section 3.1 now say 25 primary studies. The number 44 remains only where it means the 44 reports that passed the full-text screen.

## Addendum — figures, flowcharts and tables audit (five reviewers, 105 checks)

RED (fixed): Figure 5 Req 6 label now "assured decision: 9 of 25 (proof: 4)"; Figure 7 text no longer claims eight Controller boxes; Figure 7 no longer splits a sentence; Figure 9 text no longer claims steps the drawing does not show, and the figure now follows Eq. (28); Figure 16 sentence corrected (the drawing shows the empirical branch only); Figure 35 redrawn as a state machine with revoke transitions from every non-REVOKED state, subscript predicates and a compact canvas; Figure 40 strip cleaned of the cut line and cursor.
YELLOW (fixed): flowcharts of Figures 10, 12–16 redrawn with larger, single-weight type; Figure 10 box "Specify Data Scope (purpose fixed: Treatment)"; Figure 12 and 15 gain the evidence-recording step; Figure 13 verification covers signature, membership and duplicate approval; Figure 14 gains the consent-state, temporal and jurisdiction checks; Figure 16 node names follow Algorithm 6; Figure 11 lifecycle line shows all six states; captions of Figures 6–9 in sentence case; a note after Figure 6 reconciles its seven Controller boxes with the six functions of Figure 7; every screenshot figure (17–40) is now cited by number, Figures 2 and 10 and Table 1 are cited before they appear; screenshots 18, 19, 23, 25, 26, 27, 29, 30, 37 re-cropped (overlap strip, unreadable gas rows, half-cut heading, stray line, scrollbars); Table 1 column widths; Table 15 titles separated from descriptions; long table rows may now break across pages (no more blank bands); the 60-event ledger count is now stated in 6.8.8.
Left as is: Figure 28 kept (it is the Figure 8 flow labelled with the implementation's dimensions); Figures 6–9 are fixed drawings ("Authorization" spelling inside Figure 9 and underscore labels in Figure 8 cannot be edited without redrawing); low-resolution source screenshots (Figures 36, 38, 39) cannot be sharpened without recapture.
