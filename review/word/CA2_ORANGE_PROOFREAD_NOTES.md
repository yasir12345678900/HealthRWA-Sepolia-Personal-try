# Orange proofreading round – what changed and why

Files: `Yasir_CA2_Report_REVIEW_v4.docx` (orange = this round's fixes, struck through = removed; all earlier rounds already accepted) and `Yasir_CA2_Report_FINAL.docx` (clean, for submission).

How this round was done: three editors read every chapter independently (language and Australian English; consistency and cross-references; readability and human voice), then two further reviewers tried to refute every proposed fix (is the original really wrong, is the fix minimal and in the author's voice). Only fixes that survived both were applied, plus a small number of items I added after checking the reviewers' notes against the text. Rejected suggestions (rewrites for taste, duplicates, or changes to titles and identifiers) were not applied.

Total applied: 98 fixes. Nothing else in the text changed.

## Chapter 1 (5)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 1.1 | grammar | The increasing digitisation and decentralisation of healthcare information enables | The increasing digitisation and decentralisation of healthcare information enable | Compound subject 'digitisation and decentralisation' takes a plural verb. |
| 1.2 | punctuation | *trustworthy* *authorisation enforcement* | *trustworthy authorisation enforcement* | The italic phrase is split into two spans with an un-italicised space between them; it is one term and should be a single italic span, matching *cons… |
| 1.3 | consistency | RO1: Trust-Centric Consent Modelling | RO1: Trust-Centric Consent Model | RO1 is titled 'Trust-Centric Consent Model' in Chapters 4, 6 and 8 ('Modelling' is the SRQ1 title in Chapter 3); Table 1.1 labels the objective incon… |
| 1.4 | style | Chapter 5 describes the MVC-based research architecture | Chapter 5 describes the Model--View--Controller (MVC) research architecture | MVC is used here for the first time in the report body without being expanded. |
| 1.3 | consistency | RO4: Policy- and Context-Aware Authorisation | RO4: Policy- and Context-Aware Access Control | RO4 is titled 'Policy- and Context-Aware Access Control' in Chapters 3, 4 and 6 (INDEX) and 1.3 itself calls it 'policy-aware access control'; one sp… |

## Chapter 2 (14)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 2.1 | cross-reference | introduces the research questions and objectives of Chapter 3. | introduces the research questions and objectives of Chapters 3 and 4. | Per INDEX.md the research questions are in Chapter 3 and the research objectives (RO1-RO6) in Chapter 4. |
| 2.3 | punctuation | summarised in Figure 2.2.Consistent with the four-step approach | summarised in Figure 2.2. Consistent with the four-step approach | Missing space after the full stop between two sentences. |
| 2.3.3 | grammar | The search was performed in **15 August 2026**. | The search was performed on **15 August 2026**. | A search is performed 'on' a date, not 'in' it. |
| 2.3.6 | consistency | multi-party-trust healthcare data sharing | multi-party trust healthcare data sharing | Only hyphenated occurrence in the chapter; the same phrase is written 'multi-party trust healthcare data management' in Section 2.3.3 and 'multi-part… |
| 2.4.3 | terminology | Decentralised Identity (DID) and Verifiable Credentials (VCs) provide | Decentralised Identifiers (DIDs) and Verifiable Credentials (VCs) provide | DID abbreviates 'decentralised identifier' (W3C DIDs [44]); the same paragraph and the next one use it that way ('cryptographically verifiable identi… |
| 2.4.3 | punctuation | participant attributes.Reviews of blockchain-based | participant attributes. Reviews of blockchain-based | Missing space after the full stop between two sentences. |
| 2.4.4 | punctuation | governance processes [19].A decentralised trust framework | governance processes [19]. A decentralised trust framework | Missing space after the full stop following the citation. |
| 2.4.6 | consistency | studies on trusted computing and secure execution | studies on Trusted Computing and secure execution | 'Trusted Computing' is capitalised everywhere else in the chapter, including the heading of Section 2.4.6 and the sentence introducing this table. |
| 2.5 | cross-reference | by the research objectives of Chapter 3: RO1 (Req 1) | by the research objectives of Chapter 4: RO1 (Req 1) | Per INDEX.md, RO1-RO6 are defined in Chapter 4 (Research Objectives); Chapter 3 contains the research gap and questions. |
| 2.6 | cross-reference | research questions and objectives presented in the next chapter | research questions and objectives presented in Chapters 3 and 4 | The next chapter (3) presents the research questions; the objectives are presented in Chapter 4 per INDEX.md. |
| 2.3.4 | style | DID/VC-based privacy-preserving authentication [26] | privacy-preserving authentication based on decentralised identifiers and verifiable credential… | DID and VC are not introduced until Section 2.4.3; this is the first use of the abbreviation and it is unexplained. |
| 2.4.3 | style | identity management for the Internet of Things reach the same conclusion | identity management for the Internet of Things (IoT) reach the same conclusion | "IoT" is used later in the author's prose (Section 2.4.5) and in Tables 2.6 and 2.8 without the abbreviation ever being attached to its full form. |
| 2.3.3 | consistency |  Earlier foundational studies were retained when they provided critical contributions to the t… | (removed) | No study earlier than 2022 is retained in the review set any more (Section 2.3.4, Table 2.3); the sentence contradicts the method. |
| 2.3.4 | factual | One book chapter [18] was retained under the exception to exclusion criterion 3 because it pro… | (removed) | [18] Kyriakidou et al. 2023 is a journal article (Computer Networks and Communications, doi:10.37256/cnc.1220233048), as Table 2.1 says; no exception… |

## Chapter 3 (6)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 3.3.5 | punctuation | [*t*~s~*, t*~e~] | [*t*~s~, *t*~e~] | The italic markup wraps the comma and space (*, t*), so the comma renders in italics; only the two symbols should be italic. |
| 3.4 | style | establishing a robust Consent Representation, which directly fosters Participant Trust | establishing a consent representation, which directly fosters participant trust | 'robust' is filler, and the capitalised labels are used nowhere else in the chapter, which writes 'consent modelling' and 'participant trust' in lowe… |
| 3.4 | consistency | a framework for Collective Authorisation, providing the necessary foundation for systemic Poli… | a framework for collective authorisation, providing the necessary foundation for policy enforc… | Unexplained mid-sentence capitalisation; the same terms are lower case everywhere else in the chapter ('collective authorisation', 'policy enforcemen… |
| 3.4 | style | enables dynamic Temporal/Lifecycle Control over data and processes, culminating in comprehensi… | enables dynamic temporal and lifecycle control over data and processes, culminating in securit… | 'comprehensive' is filler, and the capitalised slash label does not match the chapter's own wording 'temporal and lifecycle control' and 'security as… |
| 3.4 | style |  By structuring the inquiries this way, the architecture creates a continuous logical pipeline… | (removed) | The sentence adds nothing to the paragraph and reads as machine-written ('continuous logical pipeline', 'user-facing trust' is a term used nowhere el… |
| 3.1 | consistency | the 28 shortlisted studies | the 33 shortlisted studies | Chapter 2 now shortlists 33 studies (Table 2.3, S1–S33). |

## Chapter 4 (7)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 4.7 | consistency | (continued: RQ4 current stage; RQ5--RQ6 CA3) | (continued: SRQ4 current stage; SRQ5--SRQ6 CA3) | The chapter and the table's own first column call the questions SRQ1–SRQ6; the caption alone switches to "RQ". |
| 4.7 | grammar | the planned next research on dynamic trust | the planned next-stage research on dynamic trust | "the planned next research" is missing a word; the author's term elsewhere is "next-stage research" (4.5, 4.6). |
| 4.7 | punctuation | the authorisation decision is given by Eq. (6), | the authorisation decision is given by Eq. (6). | The paragraph ends on a comma and the next paragraph starts with lowercase "where" (no displayed equation sits between them); close the sentence here… |
| 4.7 | grammar | where *V*~I~(*u*) represents the validity | In Eq. (6), *V*~I~(*u*) represents the validity | A new paragraph cannot begin with lowercase "where" continuing the previous paragraph's sentence; companion fix to the Eq. (6) sentence above. |
| 4.7 | punctuation | as given by Eq. (27), | as given by Eq. (27). | Same pattern as Eq. (6): the paragraph ends on a comma and the following paragraph starts with lowercase "where" with no equation between them. |
| 4.7 | grammar | where *V*~T~(*C, t*) represents temporal validity | In Eq. (27), *V*~T~(*C, t*) represents temporal validity | A new paragraph cannot begin with lowercase "where"; companion fix to the Eq. (27) sentence above. |
| 4.7 | punctuation | RO4 to Req 4 and RO5 to Req 5 | RO4 to Req 4, and RO5 to Req 5 | Every other list in the chapter uses the serial comma (e.g. "representation, verification, collective authorisation, and policy-enforcement"); this l… |

## Chapter 5 (14)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 5.1.3 | punctuation | can therefore be summarised as follows | can therefore be summarised as follows: | The sentence introduces the display equation that follows and needs a closing colon; as written it has no terminal punctuation. |
| 5.3 | grammar | If the requested data exceeds the authorised scope | If the requested data exceed the authorised scope | The author treats 'data' as plural everywhere else in the chapter ('data are', 'data that fall', 'data that were released'), so 'exceeds' breaks agre… |
| 5 | punctuation | *how stakeholders* *interact with it* | *how stakeholders interact with it* | One italic phrase has been split into two emphasis spans by the conversion; the parallel items '*what consent represents*' and '*how trust is enforce… |
| 5.1 | punctuation | the *View* *Layer*, the | the *View Layer*, the | Split emphasis span; the sibling terms '*Controller Layer*' and '*Model Layer*' in the same sentence are single spans. |
| 5.1.1 | punctuation | *Decision* *Engine* combines | *Decision Engine* combines | Split emphasis span; the other five function names in the paragraph ('*Identity Verification*', '*Approval Aggregation*', etc.) are single spans. |
| 5.1.1 | punctuation | Finally, *Audit* *Coordination* records | Finally, *Audit Coordination* records | Split emphasis span; the function name should be one italic term like the others in the paragraph. |
| 5.4 | punctuation | an *input to the* *authorisation process* | an *input to the authorisation process* | One italic phrase has been split into two emphasis spans by the conversion. |
| 5.7 | punctuation | between *approval* *validity* and | between *approval validity* and | Split emphasis span; the contrasting term '*access scope validity*' in the same sentence is a single span. |
| 5.5 | terminology | contribute to the authorisation evidence set *A*~v~ | contribute to the verified approval set *A*~v~ | A_v is defined (5.2, Eq. (45), 5.6) as the verified approval set; the evidence component of the consent object is E, so calling A_v the "authorisatio… |
| 5.10 | factual | As shown in Table 5.2, the View provides the operational environment | This mapping is summarised in Table 5.2. The View provides the operational environment | Table 5.2 maps research objectives to MVC components (the View appears only in the RO6 row); it does not show that the View provides the operational … |
| 5.3 | punctuation | (Eq. (7)), | (Eq. (7)). | The sentence ends here; the next paragraph starts a new sentence (see companion fix). |
| 5.3 | grammar | where *I* represents identity-related information | In Eq. (7), *I* represents identity-related information | A new paragraph cannot begin with a lower-case 'where' continuing the previous sentence; same treatment as in Sections 4.7 and 6.1. |
| 5.9 | terminology | the architecture provides *collective authorisation integrity* | the architecture provides *multi-party authorisation integrity* | Table 5.1, which summarises these properties, names it 'Multi-party authorisation integrity'. |
| 5.9 | terminology | the architecture provides *decision accountability* | the architecture provides *authorisation evidence* | Table 5.1 and the title of Section 5.8 name this property 'Authorisation evidence'. |

## Chapter 6 (25)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 6.1.1 | punctuation | workflow(Figure 6.1) | workflow (Figure 6.1) | Missing space before the opening bracket. |
| 6.1.2 | punctuation | *t*~e~ *\> t*~s~ | *t*~e~ \> *t*~s~ | The '>' operator is inside the italic markup while the symbols t_s and t_e are meant to be italic; matches the equation form t_e > t_s used in Algori… |
| 6.1.2 | punctuation | *C* → *E.* This sequence | *C* → *E*. This sequence | The full stop is italicised together with the symbol E; it belongs outside the italics. |
| 6.3.2 | grammar | Formally, for the valid approval set *A*~v~ that | Formally, for the valid approval set *A*~v~, | 'for the valid approval set A_v that u ∉ A_v' does not parse; the stray 'that' leaves the sentence without a main clause. |
| 6.4.2 | grammar | where ⊨ denotes that the requested purpose | Here, ⊨ denotes that the requested purpose | The preceding display equation ends with a full stop, so the lower-case 'where ...' clause is a sentence fragment; starting a new sentence fixes it w… |
| 6.5 | consistency | The current stage model evaluates | The current-stage model evaluates | Compound modifier is hyphenated everywhere else in the chapter ('current-stage authorisation model', 'current-stage decision process'). |
| 6.5.2 | consistency | The state transition condition can be represented as | The state-transition condition can be represented as | Same section hyphenates the compound modifier ('state-transition rules', 'state-transition event'). |
| 6.5.2 | grammar | is a function of both time and lifecycle state that | is a function of both time and lifecycle state: | 'a function of both time and lifecycle state that Validity(C) = f(...)' does not parse; a colon introduces the display equation as the author does el… |
| 6.6.2 | consistency | authorisation properties P that the framework | authorisation properties *P* that the framework | Symbol P is not italicised, unlike F, s and the other symbols in the same procedure. |
| 6.6.2 | consistency | valid scenarios S~valid~, | valid scenarios *S*~valid~, | Set symbol S is not italicised, unlike *S*~C~, *S*~R~ and *A*~v~ elsewhere in the chapter. |
| 6.6.2 | consistency | negative scenarios S~negative~, | negative scenarios *S*~negative~, | Set symbol S is not italicised, unlike the other subscripted symbols in prose. |
| 6.6.2 | consistency | adversarial scenarios S~adv~, | adversarial scenarios *S*~adv~, | Set symbol S is not italicised, unlike the other subscripted symbols in prose. |
| 6.6.2 | punctuation | Each scenario *s* ∈S is associated | Each scenario *s* ∈ *S* is associated | Missing space after the ∈ operator, and the set symbol S is not italicised like s. |
| 6.7 | grammar | in which current stage establishes | in which the current stage establishes | Missing definite article before 'current stage'. |
| 6.7 | consistency | For the current stage implementation, | For the current-stage implementation, | Compound modifier is hyphenated everywhere else in the chapter ('current-stage authorisation decision'). |
| 6.3.1 | consistency | the Guardian workflow (Figure 7.2, Section 7.3) | the guardian workflow (Figure 7.2, Section 7.3) | Role names are lower-case everywhere else in the chapter and in the Figure 7.x captions ('patient interface', 'guardian subsystem', 'auditor interfac… |
| 6.4.1 | consistency | The Doctor interface retrieves a consent | The doctor interface retrieves a consent | Role names are lower-case elsewhere in the chapter ('patient interface', 'auditor interface') and in the Figure 7.3/7.4 captions ('doctor subsystem'). |
| 6.4.1 | consistency | the Doctor interface offers only modules | the doctor interface offers only modules | Same capitalisation inconsistency as above; 'patient interface' and 'auditor interface' are lower-case in this chapter. |
| 6.1 | punctuation | (Eq. (7)), | (Eq. (7)). | The sentence ends here; the next paragraph starts a new sentence (see companion fix). |
| 6.1 | grammar | where *I* represents patient and participant identity information | In Eq. (7), *I* represents patient and participant identity information | A new paragraph cannot begin with a lower-case 'where' continuing the previous sentence. |
| 6.2 | punctuation | The identity verification condition is given by Eq. (8), | The identity verification condition is given by Eq. (8). | The sentence ends here; the next paragraph starts a new sentence (see companion fix). |
| 6.2 | grammar | where *u* is the requesting participant. | In Eq. (8), *u* is the requesting participant. | A new paragraph cannot begin with a lower-case 'where' continuing the previous sentence. |
| 6.4.1 | cross-reference | will make the implemented gate identical to Eq. (6). | will make the implemented gate identical to Eq. (27). | The full decision matrix (V_I, V_A, V_P, V_T, V_L) is the extended decision of Eq. (27); Eq. (6) is the three-predicate current-stage decision. |
| 6.1.3 | consistency | ### 6.1.3 Algorithm 1: Trust-Aware Consent Creation | (moved above Algorithm block) | In 6.2–6.5 the algorithm sits under its 'Algorithm n' heading; in 6.1 and 6.6 the heading came after the block, leaving the subsection without its al… |
| 6.6.3 | consistency | ### 6.6.3 Algorithm 6: Formal and Empirical Authorisation Validation | (moved above Algorithm block) | In 6.2–6.5 the algorithm sits under its 'Algorithm n' heading; in 6.1 and 6.6 the heading came after the block, leaving the subsection without its al… |

## Chapter 7 (8)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 7.3 | grammar | As shown in the figure below, operationalises | As shown in the figure below, it operationalises | The sentence has no subject: 'As shown in the figure below, operationalises the multi-party authorisation component' does not parse. |
| 7.4 | grammar | demonstrates the transition from **consent verification** | This demonstrates the transition from **consent verification** | The paragraph starts in lower case with no subject ('demonstrates the transition ...'); it is a sentence fragment left after the preceding line was s… |
| 7.4 | grammar | Instead, it goes the flow as below | Instead, the flow goes as below | 'it goes the flow as below' is ungrammatical; the clause introduces the display equation that follows. |
| 7.5 | punctuation | with the result: $GRANTED$ | with the result: $GRANTED$. | The sentence 'Finally, the doctor generates DATA_ACCESS with the result GRANTED' ends here without a full stop before the next paragraph 'This produc… |
| 7.8 | consistency | Multi-party Consent | Multi-Party Consent | Every other entry in the first column of Table 7.1 is in title case (e.g. 'Consent-State Management'), and the report elsewhere writes 'Multi-Party' … |
| 7 | style | implemented by the implementation | of the implementation | 'The overall workflow implemented by the implementation' repeats the same word stem back to back; the smallest fix removes the duplication without ch… |
| 7.6 | style | **CA 3 Discussion** | (removed) | Stand-alone bold line with no content between 7.6 and 7.7; a leftover editorial marker. |
| 7.9 | factual |  | C → MS → SBT → StateCheck → AccessDecision → EMR → Audit | The paragraph 'where C denotes consent creation, MS multi-signature approval, ...' explains an equation that was missing; restored from its own descr… |

## Chapters 8–10 (15)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| 8.5 | grammar | a major component of next stage | a major component of the next stage | Missing definite article before 'next stage'; the author writes 'the next stage' elsewhere (e.g. Section 10.2, first sentence). |
| 8.6 | grammar | will be conducted in next stage | will be conducted in the next stage | Missing definite article before 'next stage'. |
| 9 | consistency | SRQ1-RQ4 | SRQ1--SRQ4 | 'RQ4' is not a label used in the report (the sub-questions are SRQ1-SRQ6); Section 8.6 writes the same range as 'SRQ1--SRQ4'. |
| 9 | punctuation | (Chapters 3-4) | (Chapters 3--4) | Ranges elsewhere in the report use the en dash ('RO1--RO4', 'Figures 7.3--7.4'); a single hyphen is inconsistent. |
| 10 | grammar | corresponding to current and next stage | corresponding to the current and next stages | Missing article and the noun should be plural after 'two major stages corresponding to ...'. |
| 10.2 | grammar | While current stage focuses on | While the current stage focuses on | Missing definite article; the preceding sentence in the same paragraph writes 'during the current stage'. |
| 10.2 | grammar | trustworthy authorisation decision, next stage will investigate | trustworthy authorisation decision, the next stage will investigate | Missing definite article; the same paragraph opens with 'The next stage will build upon'. |
| 10.2 | grammar | The first major focus of next stage is | The first major focus of the next stage is | Missing definite article before 'next stage'. |
| 10.2 | grammar | Next stage will therefore extend | The next stage will therefore extend | Missing definite article; Section 10.2 also writes 'The next stage will investigate'. |
| 10.2 | grammar | Next stage will extend the current prototype-based evaluation | The next stage will extend the current prototype-based evaluation | Missing definite article before 'next stage'. |
| 10.2 | grammar | An important analytical objective of next stage is | An important analytical objective of the next stage is | Missing definite article before 'next stage'. |
| 10.2 | grammar | developed across current stage and next stage will | developed across the current stage and the next stage will | Missing definite articles before 'current stage' and 'next stage'. |
| 10.2 | grammar | By the completion of next stage, | By the completion of the next stage, | Missing definite article before 'next stage'. |
| 10.2 | grammar | Consequently, next stage will complete | Consequently, the next stage will complete | Missing definite article before 'next stage'. |
| 10.2 | grammar | established in current stage to | established in the current stage to | Missing definite article before 'current stage'; Section 8.6 writes 'At the current stage'. |

## References (4)

| Section | Type | Was | Now | Why |
|---|---|---|---|---|
| References | punctuation | 27(6):3641--3671,2025 | 27(6):3641--3671, 2025 | Missing space after the comma before the year; every other entry has "pages, year". |
| References | consistency | *ACM Transactions on Management Information Systems (TMIS)* | *ACM Transactions on Management Information Systems* | No other venue in the list carries a bracketed abbreviation (cf. "*ACM Computing Surveys*" in [25]). |
| References | spelling | Roland Hohmann, and Glann Parry | Roland Hohmann, and Glenn Parry | Typo in an author name; the Strategic Change article (doi:10.1002/jsc.2558) is by Glenn Parry. |
| References | spelling | secure live-stock data sharing | secure livestock data sharing | Line-break hyphen left inside a word; the Cryptography 9(3):52 title has 'Livestock'. |

## Points left for you to decide (not changed)

- **3.4 / 6.x** – Eq. (27) in Section 3.4 (the integrated decision) writes Decision(C, R, t) while Sections 3.3.6 and 6.x write Decision(C, R); the maths was not touched. Add t to the earlier form or drop it from the later one.
- **3.4** – Eq. (27) ends with a full stop but the sentence continues with 'where …'; inside the maths, so left to you (change the full stop to a comma).
- **6.3.2** – A_v is defined as the set of valid approvals, but Step 6 tests u ∉ A_v and the threshold condition quantifies over participants u_i ∈ A_v. Changing the Step 7 update to A_v ∪ {u} (in the maths) would make A_v consistently the set of approving participants.
- **6.5.2** – Lifecycle validity is introduced as V_L(C) but Algorithm 5 returns V_L(C, t, q), which also folds in the time check V_T(C, t). One sentence saying that the procedure's combined predicate equals V_T ∧ V_L ∧ the transition check would remove the ambiguity.
- **7.12** – Table 7.2 names contracts/ConsentSBTv3.sol and test T5 covers 'v3 contract routing', but Section 7.12 says the Sepolia tokens in Table 7.4 were anchored by ConsentSBTv2. A half-sentence explaining that the on-chain evidence predates the v3 deployment would remove the apparent contradiction.
- **10.2 / Table 10.1** – Sections 8.2 and 8.4 defer W3C VC verification and purpose binding (P_R ⊨ P_C) to Stage 2, but the next-stage plan lists only temporal/lifecycle trust, formal assurance, empirical validation and integrated evaluation. Consider adding the two deferred items to 10.2 or Table 10.1.
- **2.3.3** – The search day (15 August 2026) and the per-database counts are still the assumed values from the previous round.
- **References [33]** – One reviewer suggested the third author of the Welzel et al. 2025 npj Digital Medicine paper is 'Hannah Louise Smith' rather than 'H. Jeff Smith'. The bibliographic database I can reach (OpenAlex via Paperguide) lists 'H. Jeff Smith', so the entry was left unchanged; check the journal page if you have access.
