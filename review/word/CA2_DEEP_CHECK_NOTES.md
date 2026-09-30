# Deep-check round (round 5) – what changed and why

Files: `Yasir_CA2_Report_REVIEW_v5.docx` (orange = this round's fixes, struck through = removed; earlier rounds already accepted) and `Yasir_CA2_Report_FINAL.docx` (clean, for submission).

How this round was done: 55 specialist passes (one per figure with the image open, one per group of tables, one per algorithm checked against its equations and the HALAH source code, one for all equations, five for the references with a literature database, and a voice pass and a language pass per chapter that compared the text with your original report), then a sceptical reviewer and a writing-voice reviewer judged every proposed text fix. Only fixes that both accepted were applied, plus the items I added after reading the reviewers' notes against the text and the code.

Total text fixes applied: 86.

## Figures redrawn (same gold style, same tool)

- **Figure 2.2** – exclusion reason 2 now reads 'Subject matter outside the review scope', as in Section 2.3.4 and Table 2.2.
- **Figure 5.1** – the auditor interface now receives audit evidence (arrow reversed, as Sections 5.1 and 5.8 say); DID/VC verification is linked to the credential store; the three band labels use one format.
- **Figure 5.2** – the Protected Resource band carries its title at the top like the other bands.
- **Figure 5.3** – both layer headings in bold.
- **Figure 5.4** – redrawn in a two-lane layout so it is legible at page width; a failed identity/authority check now leads to DENY (Eq. (6)); equation reference written 'Eq. (6)'.
- **Figure 6.1** – terminal 'Return Consent Object C' added (Step 12, Algorithm 1 line 18).
- **Figure 6.2** – two-lane layout; the credential decision covers retrieval failure ('VC Retrieved and Valid?').
- **Figure 6.3** – two-lane layout; 'Define Authorisation Threshold N' added (Step 2); the success tail now reads Activate → Generate Activation or Token Evidence → Record Threshold-Satisfied Event (Steps 9–11); the pending branch records the threshold-pending event.
- **Figure 6.4** – 'Identity and Authority Valid?' and 'Generate or Verify Access Evidence', matching Steps 2 and 8.
- **Figure 6.5** – two-lane layout; validity interval retrieved before the lifecycle state (Steps 1 and 3); 'State Permits Operation?'; evidence recorded on the successful path (Step 8); denial recorded before the deny result, as in Algorithm 5.
- **Figure 6.6** – scenario classes named as in Steps 2–4; the 'functional and practical performance' box removed (not in the procedure, and 3.3.6 says performance is not evaluated); failed cases are analysed and documented instead of an undefined 'refine and iterate' loop.
- **Figure 7.6** – the release gate now reads 'State = ACTIVE, access proof valid and S_R ⊆ S_C' (Sections 6.4, 7.4, 7.13); ONCHAIN_MINT added to the audit-log list; SIGN_CONSENT and STATE_CHECK now have arrows into the audit log.
- **Figures 7.1–7.5** – recaptured from the running prototype (version 1, current repository) so that they show what the text describes: the filled consent form with Medication and Procedure selected; the guardian page after the second signature (2/2, SBT minted); the doctor page with the decision matrix, the ACTIVE state and the authorised scope; the request block with both the MEDICATION and PROCEDURE record tables; and the lifecycle with CREATE_CONSENT, both SIGN_CONSENT records, MINT_SBT, STATE_CHECK and the final DATA_ACCESS/GRANTED record. Two things to know: the app ran in its off-chain demo mode (no Sepolia key in this environment), and the repository's data/synthea medications.csv, procedures.csv and observations.csv are corrupted after about 393 KB (pandas cannot read them, so the app shows 'No records found'); the recapture used copies truncated at the last clean line. Re-export those three files in the repository.

## Chapter 2 (16)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 2.3.1 | consistency | The review process was structured according to the Preferred Reporting Items for Systematic Re… | The review process was structured according to the PRISMA framework. | PRISMA is already expanded at its first use in the opening paragraph of Section 2.3 (six lines earlier); the second expansion is redundant. |
| 2.4.7 | terminology |   Blockchain-based data governance   |   Blockchain-based healthcare data governance   | Table 2.3, Section 2.4.2 and the Table 2.5 caption all name this stream 'Blockchain-based healthcare data governance'; Table 2.10 drops 'healthcare' … |
| 2.1 | style | The objective of this chapter is therefore to examine, through a systematic literature review,… | The following sections analyse these research areas and identify the gap addressed by the prop… | Editor-added sentence restates 'The objective of the review is ... to examine how existing approaches address different conditions' two paragraphs ab… |
| 2.2.5 | style | These five requirements form the basis of the comparison of the existing approaches in Section… | Whether each shortlisted study addresses each requirement is recorded in Tables 2.4--2.9, and … | The first sentence repeats the last sentence of the Section 2.2 introduction ('They form the basis on which the shortlisted studies are compared in S… |
| 2.3 | style | Consistent with the four-step approach adopted in this research group, the process is reported… | The process is reported in four steps: searching the literature (Step 1) | 'Consistent with the four-step approach adopted in this research group' is an editor-added justification that the author never uses; the four steps a… |
| 2.3.3 | grammar | using the following academic databases including 1) IEEE Xplore, 2) ACM Digital Library, 3) Sc… | using the following academic databases: 1) IEEE Xplore, 2) ACM Digital Library, 3) ScienceDire… | 'the following ... including' is doubled, and the stray semicolon before 'and 7)' breaks the comma list. |
| 2.3.5 | style | for this review, prepared following PRISMA 2020 [40], which summarises | for this review, which summarises | Editor-inserted clause; that the review follows PRISMA 2020 [40] is already stated at the start of Section 2.3 and again in 2.3.1, and the author's o… |
| 2.4.3 | style |   Comprehensive survey of decentralised identifiers and verifiable credentials, their standard… |   Survey of decentralised identifiers and verifiable credentials, their standards, architectur… | 'Comprehensive' is an evaluative adjective the author does not use for other survey studies in Tables 2.4--2.9 (e.g. 'Survey of blockchain architectu… |
| 2.3.3 | consistency | including title, author, DOI, and publication year | including title, author, digital object identifier (DOI), and publication year | DOI is used here before it is spelled out two paragraphs later; the abbreviation should be defined at first use (companion fix in the next finding). |
| 2.3.3 | consistency | the digital object identifier used for duplicate detection | the DOI used for duplicate detection | The full form belongs at the first use in the previous paragraph; here the abbreviation already introduced should be used. |
| 2.3.2 | consistency | This systematic literature review (SLR) is guided by | This SLR is guided by | SLR is already defined in the first sentence of Section 2.3.1; the abbreviation is expanded twice. |
| 2.3.4 | terminology | healthcare data sharing, electronic health records, patient consent, healthcare access control | healthcare data sharing, electronic health records (EHRs), patient consent, healthcare access … | EHR is used without definition in Tables 2.3, 2.4, 2.5, 2.7 and 2.8 and nowhere in the report is it expanded; this is the first prose mention of the … |
| 2.4.1 | terminology | under the GDPR, the common law and professional ethics | under the General Data Protection Regulation (GDPR), the common law and professional ethics | GDPR is never expanded anywhere in the report; this Table 2.4 cell is its first use. |
| 2.4.1 | terminology | measured with HIPAA, privacy-impact and EHR security assessment tools | measured with Health Insurance Portability and Accountability Act (HIPAA), privacy-impact and … | HIPAA is never expanded anywhere in the report; this Table 2.4 cell is its first use. |
| 2.1 | consistency | evaluating quality and analysing the data | evaluating quality, and extracting and categorising the data | Step 4 is named "Data Extraction and Categorisation" in the heading of 2.3.6 and "extracting and categorising the data (Step 4)" in Section 2.3; "ana… |
| 2.3.4 | consistency | four studies from outside the healthcare domain were retained because the mechanism they contr… | five studies from outside the healthcare domain were retained because the mechanism they contr… | S33 (Ménétrey et al. [22], TEE attestation) is also a non-healthcare study in the review set (Table 2.3, Section 2.4.6); the count and list omitted i… |

## Chapter 5 (8)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 5.1.2 | cross-reference | The relationship between the MVC components and the trust predicates introduced by SRQ1--SRQ5 … | The trust predicates introduced by SRQ1--SRQ5 and the resulting authorisation decision are ill… | Figure 5.3 shows only the Model box and the Controller subgraph; the View does not appear, so "the MVC components" overstates what the figure illustr… |
| 5.2 | grammar | For the current stage scope of the proposed framework, the decision is given by Eq. (6), | For the current stage scope of the proposed framework, the decision is given by Eq. (6). | The sentence ends in a comma and the next paragraph starts with 'where', because the display equation between them was replaced by a reference; it no… |
| 5.2 | grammar | where *V*~I~(*u*) represents the validity of the requesting participant's identity and authori… | In Eq. (6), *V*~I~(*u*) represents the validity of the requesting participant's identity and a… | Paragraph begins with a lower-case 'where' that continues nothing, since the equation it explained is no longer displayed here; same fix pattern the … |
| 5.5 | grammar | Identity verification is given by Eq. (8), | Identity verification is given by Eq. (8). | Same broken-sentence pattern as Eq. (6): the sentence ends in a comma and the next paragraph starts with 'where'. |
| 5.5 | grammar | where *VerifyDID*(*u*) determines whether the decentralised identity of participant *u* can be… | In Eq. (8), *VerifyDID*(*u*) determines whether the decentralised identity of participant *u* … | Paragraph begins with a dangling lower-case 'where' after the equation was moved out of the text. |
| 5.6 | consistency | the combination of identity verification and collective decision making. | the combination of identity verification and collective decision-making. | The report hyphenates 'decision-making' elsewhere (Chapter 3 uses 'distributed decision-making' and 'collective decision-making'); this is the only u… |
| 5.10 | consistency | This mapping is summarised in Table 5.2. | This mapping is summarised in Table 5.2, which also lists the next-stage objectives RO5 and RO… | The text describes RO1–RO4 only, but Table 5.2 has RO5 and RO6 rows. |
| 5.9–5.11 | layout | Tables 5.1 and 5.2 placed inside Section 5.11 | Tables 5.1 and 5.2 placed after the sentences that introduce them (5.9 and 5.10) | The two tables split a paragraph of 5.11; moved silently (no colour mark). |

## Chapter 6 (16)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 6.1.1 | consistency | After validation, the system creates the consent object, assigns a consent identifier, persist… | After validation, the system assigns a consent identifier, creates the consent object, persist… | Figure 6.1 (Generate Consent Identifier before Create Trust-Aware Consent Object), procedure Steps 8-9 and Algorithm 1 lines 14-15 all generate the i… |
| 6.4.1 | consistency | The system retrieves the relevant consent object and verifies the requesting participant. It t… | The system retrieves the relevant consent object, verifies the requesting participant and eval… | Figure 6.4 (and Procedure Step 3 / Algorithm 4 lines 6-10) has an 'Evaluate Consent State / Consent Active?' step between identity verification and m… |
| 6.5.1 | consistency | evaluates the consent's temporal interval, lifecycle state, and revocation status before the s… | evaluates the consent's temporal interval, lifecycle state, revocation status and requested tr… | Figure 6.5, Step 6 and Algorithm 5 lines 16-20 also check the requested transition; the sentence describing the figure omits it. |
| 6.1.3 | consistency |   10: **if** $t_e \leq t_s$ **then** |   10: **if** $D$, $G$, $P_u$ or $S_C$ is invalid **or** $t_e \leq t_s$ **then** | Steps 2-6 and Step 12 of the procedure say an invalid doctor, guardian set, purpose, scope or interval returns REJECT, and Figure 6.1 has one 'Consen… |
| 6.1.2 | factual | In the HALAH prototype (Section 7.2), Steps 1--3 currently perform a syntactic DID check, and … | In the HALAH prototype (Section 7.2), Steps 1--3 are not yet enforced at creation: the doctor … | In app.py the Patient page passes patient_did, doctor and guardians straight to create_consent() without any DID check; verify_vc (the syntactic chec… |
| 6.3.3 | consistency | Algorithm 3 explicitly distinguishes between invalid, duplicate, and valid approvals. | Algorithm 3 explicitly distinguishes between invalid, unauthorised, duplicate, and valid appro… | The algorithm has a separate branch for an unauthorised approval (lines 7-10, participant not in G) and Step 13 lists "Invalid, unauthorised, or dupl… |
| 6.5.2 | factual | the consent to be active. The state-transition condition can be represented as | the consent to be active. The state condition can be represented as | Step 4 checks whether the current state permits the operation (State(C) ⊨ q); the state-transition condition is introduced separately in Step 6, so c… |
| 6.5.1 | cross-reference | formal analysis of the lifecycle properties (Eqs. (23)--(24)) | formal analysis of the temporal and lifecycle properties (Eqs. (23)--(24)) | Eq. (23) (built (20)) is the temporal-safety property and only Eq. (24) (built (21)) is lifecycle safety, so 'lifecycle properties' does not describe… |
| 6.3.2 | style | $ (all designated guardians must approve); configurable k-of-n thresholds are Stage 2 work. | $, so all designated guardians must approve. Configurable k-of-n thresholds are planned for St… | Editor-added aside uses a bracketed gloss, a semicolon and the casual phrase 'are Stage 2 work'; the author states plans as 'planned for'/'scheduled … |
| 6.1.2 | punctuation | *T* = (*t*~s~*, t*~e~), where *t*~s~ represents the consent start time | *T* = (*t*~s~, *t*~e~), where *t*~s~ represents the consent start time | Split italics: the comma is inside the italic run and the second symbol is italicised as "*, t*"; each symbol should be italicised on its own, as in … |
| 6.5.2 | punctuation | *V*~L~(*C, t, q*) = *TimeValid*(*C, t*)∧*StateValid*(*C, q*)∧¬*Revoked*(*C*)∧*TransitionValid*… | *V*~L~(*C, t, q*) = *TimeValid*(*C, t*) ∧ *StateValid*(*C, q*) ∧ ¬*Revoked*(*C*) ∧ *Transition… | The conjunction symbols are run together with the operands with no spaces, unlike every other conjunction in the chapter. |
| 6.5.2 | punctuation | distinction between *consent* *existence* and *consent usability* | distinction between *consent existence* and *consent usability* | Split italics: "consent existence" is broken into two italic runs while the parallel term "consent usability" is one. |
| 6.6.1 | terminology | The empirical component will evaluate both valid and invalid scenarios. Valid scenarios | The empirical component will evaluate both valid and negative scenarios. Valid scenarios | The next sentence and Section 6.6.2 call the second class "negative scenarios"; "invalid" is used nowhere else for the scenario class. |
| 6.5.1 | punctuation | PENDING_SIGNATURE, PENDING_TOKEN, NOT_STARTED, EXPIRED and ACTIVE, and only an ACTIVE consent | PENDING_SIGNATURE, PENDING_TOKEN, NOT_STARTED, EXPIRED, and ACTIVE, and only an ACTIVE consent | The chapter otherwise uses the serial comma in lists (e.g. "Observation, Medication, Condition, and Procedure"); this list omits it. |
| 6.4.1 | punctuation | requires an ACTIVE consent state, a valid access proof and a valid scope. | requires an ACTIVE consent state, a valid access proof, and a valid scope. | Serial comma omitted where the rest of the chapter uses it in three-item lists. |
| 6.6.3 | consistency |   **Require:** Framework implementation $F$, validation scenarios $S$, security properties $P$ |   **Require:** Framework implementation $F$ | Lines 1–4 of Algorithm 6 define P and the scenario sets inside the algorithm, so they are not inputs. |

## Chapter 7 (9)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 7.4 | punctuation | Instead, the flow goes as below | Instead, the flow goes as below: | The sentence introduces the display equation that follows and ends without any punctuation. |
| 7.10 | consistency | Consent state: PENDING_SIGNATURE, PENDING_TOKEN, NOT_STARTED, EXPIRED, REVOKED, ACTIVE ($V_A$,… | Consent state: PENDING_SIGNATURE, PENDING_TOKEN, NOT_STARTED, EXPIRED, REVOKED, ACTIVE ($V_A$,… | Table 7.3 (T3, T4) attributes the state transitions computed by services/state_service.py (PENDING_SIGNATURE -> ACTIVE -> REVOKED) to V_L, and Eq. (1… |
| 7.11 | terminology | Negative cases still to be added in Stage 2 include insufficient approvals at the data-release… | Negative and adversarial cases still to be added in Stage 2 include insufficient approvals at … | Step 4 of 6.6.2 classes duplicate approvals as an adversarial scenario, not a negative one; the sentence before this one already uses the three-class… |
| 7.10 | consistency |   Controller   services/identity_service.py   DID check; EIP-712 approval signing and verifica… |   Controller   services/identity_service.py   DID check; EIP-712 approval signing and verifica… | Guardian approval verification implements Algorithm 3 as well (Section 7.3, Table 7.1); Table 7.2 mentioned only Algorithm 2. |
| 7.10 | consistency |   Controller   services/state_service.py   |   Controller   services/state_service.py (Algorithm 5)   | Table 7.2 gave no mapping for Algorithm 5; the state service is where the temporal and lifecycle checks run. |
| 7.10 | factual |   Smart contract   contracts/ConsentSBTv3.sol   |   Smart contract   contracts/ConsentSBTv3.sol (ConsentSBT_v2_hardened.sol for the on-chain evi… | The tokens in Table 7.4 were minted by the v2 contract (evidence/onchain_mints_2026-09-21.txt); the table named only v3. |
| 7.12 | factual | by the ConsentSBTv2 contract at address | by the ConsentSBTv2 contract (contracts/ConsentSBT_v2_hardened.sol, the version deployed when … | Explains why the on-chain evidence comes from v2 while the source mapping names v3. |
| 7.4 | consistency | The system displays the requested modules and performs cryptographic verification before grant… | The system displays the requested modules and performs cryptographic verification before grant… | Figure 7.4 shows a zero-knowledge button that the section never mentioned; Section 7.13 and Table 7.3 (T9) say the circuit is not built. |
| 7.5 | grammar | More importantly, the **Consent Lifecycle** section reconstructs the sequence of events associ… | More importantly, the **Consent Lifecycle** section reconstructs the sequence of events associ… | Six paragraph fragments joined back into the one sentence they were (a conversion artefact of the original document); the figure note says what Figur… |

## Chapter 4 (4)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 4 | australian-english | The complete research program consists of six research objectives | The complete research programme consists of six research objectives | Author's prose uses Australian spelling; the original report has "research programme" here and the guide lists "programme". |
| 4 | australian-english | as part of the next research program. | as part of the next research programme. | Same sentence in the author's original reads "next research programme"; Australian spelling in the author's prose. |
| 4.5 | australian-english | This objective constitutes a principal component of the next-stage research program. | This objective constitutes a principal component of the next-stage research programme. | Author's original reads "research programme"; Australian spelling in the author's prose. |
| 4.7 | australian-english | The mapping follows the structure of the research program and maintains | The mapping follows the structure of the research programme and maintains | Author's original reads "research programme"; Australian spelling in the author's prose (ch03 has one more "program" outside this chapter's scope). |

## Chapter 9 (1)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 9 | style | The publication strategy is aligned with the progression of the research. The current stage wo… | The current stage work establishes | The first sentence was added in editing and reads as stock phrasing ("is aligned with the progression of"); the author's original paragraph began dir… |

## Chapter 10 (1)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 10.2 | punctuation | *static consent* *management* to *dynamic trustworthy authorisation* | *static consent management* to *dynamic trustworthy authorisation* | The italic markup is split mid-phrase ("*static consent* *management*"), which renders as two separate italic runs with an un-italicised gap; the aut… |

## Chapter 3 (4)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 3.3.1 | grammar | the proposed model represents consent as a structured and evaluable authorisation object that | the proposed model represents consent as a structured and evaluable authorisation object | The sentence runs straight into display equation (7); 'object that C = (I, A, P, E)' is not a sentence, and the following 'where I represents ...' al… |
| 3.4 | punctuation | where *V*~I~ represents identity and authority validity | In Eq. (27), *V*~I~ represents identity and authority validity | Equation (27) (built as (24)) ends with a full stop, so the next paragraph cannot start with lowercase 'where'; the author's own pattern elsewhere is… |
| 3.3.6 | australian-english | the final assurance stage of the research program by connecting | the final assurance stage of the research programme by connecting | Author's prose uses Australian spelling; the original report has 'research programme' in this very sentence (ORIGINAL_STYLE.txt line 531). |
| 3.1 | style | In particular, the review defined five key requirements | The review defined five key requirements | Two consecutive paragraphs open or pivot on 'In particular' (this editor-added paragraph and the next one); the connector adds nothing here. |

## References (18)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| References | consistency | *Cryptography*, 9(3):52, 2025. | *Cryptography*, 9(3):52, 2025. doi:10.3390/cryptography9030052. | Entries [5] and [8] carry a DOI while the other journal entries do not; DOI verified from the Paperguide record for this paper. |
| References | consistency | *IEEE Access*, 10:5768--5789, 2022. | *IEEE Access*, 10:5768--5789, 2022. doi:10.1109/ACCESS.2022.3141079. | Same journal and format as entry [5], which carries a DOI; DOI verified from the Paperguide record (volume 10, pages 5768-5789 confirmed). |
| References | consistency | *Journal of Network and Computer Applications*, 215:103633, 2023. | *Journal of Network and Computer Applications*, 215:103633, 2023. doi:10.1016/j.jnca.2023.1036… | DOI missing while [5] and [8] have one; DOI verified from the Paperguide record (volume 215, article 103633 confirmed). |
| References | consistency | *IEEE Communications Surveys & Tutorials*, 25(1):386--424, 2023. | *IEEE Communications Surveys & Tutorials*, 25(1):386--424, 2023. doi:10.1109/COMST.2022.322464… | DOI missing while [5] and [8] have one; DOI verified from the Paperguide record (volume 25, pages 386-424 confirmed). |
| References | consistency | *IEEE Transactions on Computers*, 73(8):2051--2065, 2024. | *IEEE Transactions on Computers*, 73(8):2051--2065, 2024. doi:10.1109/TC.2024.3398509. | DOI missing while [5] and [8] have one; DOI verified from the Paperguide record (volume 73, pages 2051-2065 confirmed). |
| References | consistency | *Journal of Information Security and Applications*, 83:103789, 2024. | *Journal of Information Security and Applications*, 83:103789, 2024. doi:10.1016/j.jisa.2024.1… | DOI missing while [5] and [8] have one; DOI verified from the Paperguide record (volume 83, article 103789 confirmed). |
| References | consistency | *Systems*, 11(1):38, 2023. | *Systems*, 11(1):38, 2023. doi:10.3390/systems11010038. | DOI missing while [5] and [8] have one; DOI verified from the Paperguide record (Systems 11(1):38, 2023 confirmed). |
| References | consistency | *BMC Nursing*, 23(1):564, 2024. | *BMC Nursing*, 23(1):564, 2024. doi:10.1186/s12912-024-02231-1. | Reference list gives DOIs for some entries ([5], [8], [10], [27]–[34], [40], [41]) but not others; DOI verified with Paperguide (BMC Nursing, vol. 23… |
| References | consistency | *IEEE Access*, 10:28545--28563, 2022. | *IEEE Access*, 10:28545--28563, 2022. doi:10.1109/ACCESS.2022.3157850. | DOI added for consistency with [5] and [8] (other IEEE Access entries carry a DOI); verified with Paperguide (vol. 10, pp. 28545–28563, 2022). |
| References | consistency | *Journal of Big Data*, 10(1):104, 2023. | *Journal of Big Data*, 10(1):104, 2023. doi:10.1186/s40537-023-00783-8. | DOI added for consistency with the DOI-bearing entries; verified with Paperguide (Journal of Big Data, 2023, Jiang, Chen, Yu, Zhang, Ding). |
| References | consistency | *Digital Health*, 10:20552076241290964, 2024. | *Digital Health*, 10:20552076241290964, 2024. doi:10.1177/20552076241290964. | DOI added for consistency; verified with Paperguide (Digital Health, 2024; the DOI suffix equals the article number already given). |
| References | consistency | *Electronics*, 12(24):4973, 2023. | *Electronics*, 12(24):4973, 2023. doi:10.3390/electronics12244973. | DOI added for consistency; verified with Paperguide (Electronics 12(24):4973, December 2023). |
| References | consistency | *Strategic Change*, 32(6):223--237, 2023. | *Strategic Change*, 32(6):223--237, 2023. doi:10.1002/jsc.2558. | DOI added for consistency; verified with Paperguide (Strategic Change vol. 32, pp. 223–237, 2023). |
| References | consistency | *IoT*, 6(4):65, 2025. | *IoT*, 6(4):65, 2025. doi:10.3390/iot6040065. | DOI added for consistency; verified with Paperguide (IoT 6(4):65, published 28 October 2025, before the 15 August 2026 search date... note: publicati… |
| References | consistency | *Computer Networks and Communications*, pages 244--271, 2023. | *Computer Networks and Communications*, pages 244--271, 2023. doi:10.37256/cnc.1220233048. | DOI added for consistency; verified with Paperguide (Kyriakidou, Papathanasiou, Polyzos, Computer Networks and Communications, August 2023). |
| References | factual | *IEEE Transactions on Information Forensics and Security*, pages 4999--5014, 2025. | *IEEE Transactions on Information Forensics and Security*, 20:4999--5014, 2025. | Volume number is missing; IEEE Xplore citation, researchr and Google Scholar all give vol. 20, pp. 4999-5014, 2025 for DP-DID. |
| References | consistency | *Cluster Computing*, 28(8):529, 2025. | *Cluster Computing*, 28(8):529, 2025. doi:10.1007/s10586-025-05308-x. | Neighbouring entries [28], [29], [31]-[34] carry a DOI; this one does not. DOI verified from Paperguide fetch and the Springer article page (Cluster … |
| References | consistency | *Journal of Systems Architecture*, 148:103081, 2024. | *Journal of Systems Architecture*, 148:103081, 2024. doi:10.1016/j.sysarc.2024.103081. | Neighbouring entries carry a DOI; this one does not. DOI verified from Paperguide search result (Yin et al., Journal of Systems Architecture, 2024-02… |

## Chapter 1 (6)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 1.1 | style | These instruments illustrate, in a concrete jurisdiction, the three conditions examined in thi… | These instruments show, for one jurisdiction, three of the conditions examined in this researc… | Editor-added sentence; 'the three conditions' contradicts Section 1.3, which sets out four dimensions (identity, authority, multi-party authorisation… |
| 1.1 | style | governs the national identifiers used for individuals (IHI), practitioners (HPI-I) and organis… | governs the national identifiers used for individuals (Individual Healthcare Identifier, IHI),… | IHI, HPI-I and HPI-O are used without expansion at first use, and the list lacks the serial comma the author uses everywhere else in the chapter. |
| 1.1 | punctuation | through purpose-bound consent, module-level data scope and an explicit jurisdiction attribute | through purpose-bound consent, module-level data scope, and an explicit jurisdiction attribute | The author's prose uses the serial comma consistently (e.g. 'validity periods, expiration, revocation, and'); this editor-added sentence omits it. |
| 1.4 | punctuation | through its workflow, procedure and algorithm. | through its workflow, procedure, and algorithm. | Serial comma missing; the author uses it consistently throughout Chapter 1. |
| 1.4 | punctuation | the mapping to the source code, the automated test evidence and the on-chain evidence. | the mapping to the source code, the automated test evidence, and the on-chain evidence. | Serial comma missing; the author uses it consistently throughout Chapter 1. |
| 1.4 | consistency | Chapter 10 sets out the research plan for the next stage. | Chapter 10 sets out the research plan for the current and next stages. | Chapter 10 has two sections, '10.1 Current Stage: Completed and Current Work' and '10.2 Next Stage: Planned Work' (INDEX.md), so it does not cover th… |

## Chapter 8 (3)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 8.5 | punctuation | The consent validity interval is represented as [*t*~s~*, t*~e~], with temporal validity defin… | The consent validity interval is represented as [*t*~s~, *t*~e~], with temporal validity defin… | Split italics: the comma and space are italicised with the second t; Chapter 3 (SRQ5) writes the same interval as [*t*~s~, *t*~e~]. |
| 8.4 | consistency | The Doctor interface (Figures 7.3--7.4, Section 7.4) | The doctor interface (Figures 7.3--7.4, Section 7.4) | Section 6.4.1 and Chapter 7 write 'doctor interface' / 'doctor subsystem' in lower case; capital D is inconsistent. |
| 8.1 | grammar | This provides a conceptual basis for dynamic access decisions and allows subsequent authorisat… | This representation provides a conceptual basis for dynamic access decisions and allows subseq… | After the inserted sentence about the prototype tuple, the bare 'This' now points at the prototype implementation rather than the consent representat… |

## Checked and found correct

- All 45 references exist with the details given; the DOIs added this round were each taken from the database record. Every citing sentence was judged against the paper's abstract; no misattribution was found.
- Equation numbering is continuous and every 'Eq. (n)' reference points to the equation it describes.
- Chapter 7 claims were checked against the repository at commit 0a960ca: file names, test IDs and counts (16 passed, 2 skipped), state names, the 2-of-2 rule and EIP-712 signing all match. The one discrepancy (v2 contract for the on-chain evidence, v3 in the source) is now explained in 7.10 and 7.12.

## Points left for you to decide (not changed)

- **3.3.6 / 3.4 / 10.2** – Decision(C, R) versus Decision(C, R, t): only the integrated Eq. (24) carries t. Either add t where V_T is involved or drop it in (24).
- **3.3.3 / 5.3 / 6.3.2** – A_v is a set of participants in most places but Step 7's update adds an approval a. Changing the update to A_v ∪ {u} (in the maths) would make it consistent.
- **3.3.5 / 6.5.2** – V_L(C) (Eq. (15)) and V_L(C, t, q) in 6.5.2 are two different predicates under one name; one sentence stating that the procedure's combined predicate equals V_T ∧ V_L ∧ the transition check would resolve it.
- **6.2.2** – Procedure Step 7 ('Establish Identity–Authority Binding') has no line in Algorithm 2 and no box in Figure 6.2; either add it or fold it into Step 8.
- **6.4.3** – Algorithm 4 has no line for Step 1 (retrieve the consent object) or Step 7 (the final conjunction).
- **6.6.3** – Algorithm 6 has no line that performs formal reasoning, although its title says 'Formal and Empirical'.
- **7.1** – HALAH is never expanded; if it is an acronym, give the expansion at first use in 1.1.
- **8.4** – RO4 is marked 'Completed (prototype level)' although purpose binding and the full decision matrix are deferred to Stage 2; RO5 in the same position is marked differently.
- **9 / Table 9.1** – The 'Thesis Alignment' column points to thesis chapters (Chapter 5 for the HALAH and formal work), which no longer match the report's own chapter numbers; say 'thesis Chapter 5' if that is what is meant.
- **10.2 / Table 10.1** – Row 3 promises runtime-performance measurement and benchmark datasets, while 3.3.6 and 7.13 say performance is not evaluated; and the deferred RO2/RO4 items (VC verification, purpose binding) are not in the next-stage plan.
- **2.3.3** – Search day (15 August 2026) and per-database counts are still the assumed values.
- **Table 9.1** – Venue 'Computers & Security (Elsevier)' and 'submission planned November 2026' were filled in an earlier round; confirm.
