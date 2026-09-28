# CA2 Report – Word Red-line: Change Log

| File | What it is |
|---|---|
| `Yasir_CA2_Report_WORD_original.docx` | Faithful Word conversion of the PDF (v33_1_3) – no content changes |
| `Yasir_CA2_Report_REDLINE.docx` | Every change visible: red strikethrough = delete, red = add, red italic on yellow = instruction to you |
| `Yasir_CA2_Report_CLEAN.docx` | All changes applied, notes removed, figures (1–17) and equations (1–35) renumbered |

Open in Microsoft Word. On first open Word asks to update fields – choose Yes to build the table of contents. Equations are native Word equations (editable).

## Summary of changes

- **HALAH implementation integrated** as new **Chapter 7 – HALAH System and Workflow**, placed between the Proposed Solution (Ch. 6) and Current Progress (now Ch. 8). Sections 7.1–7.9 reproduce the HALAH document word for word (only section numbers, figure/table captions, line breaks in long equations and spaces after symbols were added). Sections 7.10–7.13 add the source-code mapping, automated test results (16 passed, 2 skipped, 0 failed), Sepolia on-chain evidence and limitations. Old Chapters 7–9 → 8–10; Tables 7–8 → 11–12.
- **Each RO in Chapter 6 now points to the prototype** (Sections 7.2–7.5, Figures 13–17 in the red-line) with accurate claims: EIP-712 guardian signatures (not VC verification), N = |G|, purpose whitelist, lifecycle checks already implemented, VL vs VJ naming.
- **Progress statuses corrected**: RO2 prototype level, RO4 completed, RO5 partially completed, RO6 covers SRQ1–SRQ4.
- **Removed**: editing residue in §2.2, duplicated §2.3 opening, TEE digression, the unprovable 'no execution path' claim, Figure 4, and 46 repeated equations (each replaced by a reference to the original equation).
- **Added**: Australian regulatory context (Privacy Act 1988, My Health Records Act 2012, Healthcare Identifiers Act 2010), PRISMA 2020 statement, justification of out-of-domain studies, §2.2.8 Quality Assessment, references [34]–[42].
- **Moved**: temporal/lifecycle procedure §6.4.2 → §6.5.2 (RO5); the policy procedure §6.4.4 → §6.4.2 so Algorithm 4 follows it.
- **Consistency & language**: Australian spelling (authorisation, decentralised, organised, summarises, program); RQ → SRQ throughout; missing articles and colons; 'as follows'; journal-name capitalisation; lost title capitals (FutureDID, IoT, TEE, UCON, DP-DID, Xinjiang, Byzantine); [31] corrected to *Pediatrics* 144(1), 2019.

- **Figures 1–6 kept in their original colour design**. Figure 1 is unchanged. Figures 2, 3, 5 and 6 (red-line numbering) were re-drawn with the same tool (Mermaid), colours and font (Trebuchet MS), with only these fixes:
  - Figure 2 (PRISMA): 'decentralized' → 'decentralised'.
  - Figure 3 (MVC): arranged as three labelled columns so every label is readable and the 'MODEL LAYER' title is no longer covered.
  - Figure 5 (predicate flow): 'V_I(u)' etc. written as real subscripts.
  - Figure 6 (end-to-end workflow): 'Authorization' → 'Authorisation'.
  - Sources are in `figures_colour/`.
- **Flowcharts 7–12 in black and white**, re-drawn at 300 dpi with unchanged content (`figures_bw/`). HALAH screenshots (Figures 13–17) are unchanged.
- **New Figure 18 (§7.10)**: black-and-white flowchart of the HALAH prototype workflow (Patient → Guardian → Doctor, with the audit log), built only from Sections 7.2–7.5.
- **Tables**: all tables are black and white, with a light-grey header row that repeats on every page. Rows no longer split across pages, and cell padding is slightly larger. Table 2's citation lists are now in ascending order (IEEE style; shown in the red-line). Table 9's column widths have been rebalanced.

## Needs YOUR input (yellow notes in the red-line)

1. Exact search date in §2.2.4 and records per database in §2.2.8 (must sum to 125); keep §2.2.8 only if the quality scoring was really done.
2. Verify reference [21] (McCall, IEEE JBHI) – no record could be found.
3. Target journal and submission month in Table 11.
4. ~~Edit the Figure 6 and PRISMA images~~: done, both diagrams have been redrawn.
5. Retake the HALAH screenshots from prototype v1.1.
6. In the HALAH document (kept unchanged): the 'CA 3 Discussion' label, the subject-less line after 'Access Granted.', and the missing formula before 'where C denotes…'.
7. Cover date changed to September 2026 because the evidence is dated September – reject that change if the report must stay 'August 2026'.

## All edits in document order

1. legend
2. §1.1 Australian regulatory context
3. insert after: obtain information outside the purpose or data sco
4. replace: The subsequent next stage research -> The next-stage (CA3) research
5. replace: next stage will also investigate -> The next stage will also investigate
6. replace: research. current research is concerned -> research. The current research is concerned
7. §2.2 editing residue (2 paragraphs)
8. §2.2 replacement opening
9. insert after: and a quality assessment procedure.
10. replace: performed on **August 2026** -> performed in **[dd] August 2026**
11. §2.2.5 justification of out-of-domain studies
12. insert after: Figure 2 presents the PRISMA flow diagram for this
13. §2.2.8 Quality Assessment
14. note: Author action: replace [dd] with the exact day of the final 
15. note: Also correct the image itself: 'decentralized identity' → 'd
16. §2.3 opening duplicates §2.1
17. §2.3 short opening
18. replace: observations and medications, -> medications and procedures,
19. Eq. (3) aligned with prototype scope
20. replace: then a request for observations, medications, and procedures -> then a request for medications, procedures, and observations
21. Eq. (4) aligned with prototype scope
22. §2.3.6 TEE detail outside the RQs
23. §2.3.6 TEE future-work paragraph
24. §2.3.6 one-sentence replacement
25. §3.3.2 repeated Eq. (1) + missing space
26. Eq. (7) extension to C=(I,A,P,T,L,E)
27. §3.3.4 repeated scope example (12)-(14)
28. delete repeated equation (12)
29. delete repeated equation (13)
30. delete repeated equation (14)
31. §3.3.4 cite canonical example
32. insert after: derived from the Synthea dataset
33. delete repeated equation (28)
34. delete: seamlessly 
35. replace: 4)Temporal -> 4) Temporal
36. missing space after 'Formally,'
37. replace: next stageresearch -> next-stage research
38. replace: Table 3 and Table 3 -> Table 3 and Table 4
39. replace: Thesis Chapters for CA3 -> Thesis Chapters (continued: RQ4 current stage; RQ5–RQ6 CA3)
40. delete repeated equation (29)
41. delete repeated equation (30)
42. insert after: the prevention of direct security decisions at the
43. delete: Figure 4 presents this decomposition. 
44. Figure 4 (duplicates Figure 3; unreadable labels)
45. note Figure 4
46. Figure 6 caption spelling
47. note: Also edit the diagram itself: the node 'Authorization Decisi
48. delete repeated equation (31)
49. delete repeated equation (32)
50. delete repeated equation (33)
51. §5.2 repeated scope example
52. delete repeated equation (34)
53. delete repeated equation (35)
54. replace: For the current current stage scope -> For the current stage scope
55. delete repeated equation (36)
56. delete repeated equation (37)
57. replace: For the current current stage implementation -> For the current stage implementation
58. delete repeated equation (39)
59. delete repeated equation (40)
60. delete repeated equation (41)
61. delete repeated equation (42)
62. Eq. (43) restates Eq. (6)
63. delete repeated equation (43)
64. §5.7 repeated scope example (46)-(49)
65. delete repeated equation (46)
66. delete repeated equation (47)
67. delete repeated equation (48)
68. delete repeated equation (49)
69. §5.7 cite canonical example
70. delete repeated equation (51)
71. replace: while next stagewill investigate -> while the next stage will investigate
72. insert after: Observation, Medication, Condition, and Procedure.
73. §6.1.2 prototype status of Steps 1–6
74. delete repeated equation (52)
75. delete repeated equation (53)
76. §6.2.1 overclaims VC verification
77. §6.2.1 accurate prototype description
78. insert after: If any of these conditions fails, the verification
79. delete repeated equation (54)
80. §6.3.1 prototype description (VC claim)
81. §6.3.1 accurate prototype description
82. insert after: before the authorisation becomes active.
83. delete repeated equation (59)
84. insert after: before returning data.
85. §6.4.1 repeated scope example (60)-(62)
86. delete repeated equation (60)
87. delete repeated equation (61)
88. delete repeated equation (62)
89. replace: and the request must be denied. This rule prevents -> For example, the request in Eq. (4) must be denied. This rul
90. §6.4.1 prototype status of VP
91. moved §6.4.2 procedure to §6.5.2; Algorithm 4 after its procedure
92. §6.4 Step 5 unprovable 'no execution path' claim
93. replace: Consent Creation Identity Verification Multi-Party Auth Poli -> Consent Creation → Identity Verification → Multi-Party Autho
94. delete repeated equation (63)
95. delete repeated equation (64)
96. delete repeated equation (65)
97. §6.5.1 out of date
98. §6.5.1 implemented lifecycle checks + VL/VJ note
99. delete repeated equation (66)
100. insert after: state checks, and data-access events.
101. Algorithm 6: S\*valid -> subscript
102. Algorithm 6: S\*negative -> subscript
103. Algorithm 6: S\*adv -> subscript
104. Algorithm 6: S\*valid ∪ S\*negative ∪ S\*adv -> subscript
105. delete repeated equation (69)
106. delete repeated equation (70)
107. inserted Chapter 7 (HALAH implementation) + 7.10–7.13
108. renumber chapter 7 -> 8
109. renumber 7.1 -> 8.1
110. renumber 7.2 -> 8.2
111. renumber 7.3 -> 8.3
112. renumber 7.4 -> 8.4
113. renumber 7.5 -> 8.5
114. renumber 7.6 -> 8.6
115. renumber 8 -> 9
116. renumber 9 -> 10
117. renumber 9.1
118. renumber 9.2
119. delete repeated equation (71)
120. insert after: The current result demonstrates that consent can b
121. replace: **Status: Completed** -> **Status: Completed (prototype level; W3C VC verification in
122. delete repeated equation (72)
123. delete repeated equation (73)
124. insert after: from the question of whether that participant is a
125. delete repeated equation (74)
126. delete repeated equation (75)
127. §8.3 repeated Eq. (76)-(77)
128. delete repeated equation (76)
129. delete repeated equation (77)
130. §8.3 replacement
131. replace: **Status: In Progress** -> **Status: Completed (prototype level)**
132. §8.4 out of date
133. delete repeated equation (78)
134. §8.4 replacement
135. replace: **Status: In Progress** -> **Status: Partially completed (prototype; formal lifecycle a
136. replace: RO5 is reserved primarily for next stage. -> A first version of RO5 is already operational in the HALAH p
137. delete repeated equation (79)
138. §8.5 repeated lifecycle chain (Eq. (17))
139. insert after: controlled transitions such as
140. replace: **Status: Partially Completed (RQ1-RQ3)** -> **Status: Partially completed (SRQ1–SRQ4; 16 automated tests
141. replace: The current validation focuses primarily on RQ1, RQ2, and RQ -> The current validation covers SRQ1–SRQ4 and the first SRQ5 c
142. delete repeated equation (80)
143. renumber Table 7 -> 11
144. replace: Elsevier/IEEE -> [name the target journal]
145. replace: Almost Ready -> Draft complete; submission planned [month] 2026
146. replace: *Decentralised implementation and performance evaluation* -> *Decentralised implementation and functional security evalua
147. replace: (Chapter 6). -> (Chapter 5).
148. renumber Table 8 -> 12
149. replace: summarised in Table 8. -> summarised in Table 12.
150. §10.1 out of date
151. §10.1 replacement
152. replace: next stageis -> next stage is
153. replace: policy enforcement. next stage will investigate -> policy enforcement. The next stage will investigate
154. replace: Consequently, next stagewill -> Consequently, next stage will
155. replace all (3): during current stage -> during the current stage
156. replace all (1): Whereas current stage -> Whereas the current stage
157. replace all (1): as part of next stage works -> as part of the next-stage work
158. replace all (1): Current stage establishes -> The current stage establishes
159. replace all (1): whereas next stage investigates -> whereas the next stage investigates
160. replace all (2): For current stage, -> For the current stage,
161. replace all (1): Next stage will build upon -> The next stage will build upon
162. replace all (1): guided by the following questions -> guided by the following questions:
163. replace all (1): satisfied the following criteria -> satisfied the following criteria:
164. replace all (1): of the following conditions -> of the following conditions:
165. replace all (1): summarised as following -> summarised as follows
166. replace all (1): The subsequent next research -> The next-stage research
167. replace all (1): establishment process that *I*~p~ -> establishment process: *I*~p~
168. replace all (1): extends the foundational current stage works on authorisation model -> extends the foundational current-stage authorisation model
169. replace all (1): extends the current stage works on decision process -> extends the current-stage decision process
170. replace all (1): 1) Identity Trust Authority Trust -> 1) Identity and Authority Trust
171. replace all (1): research and thus proposed framework -> research and the proposed framework
172. replace all (1): satisfying the authorised scope *S*~R~ -> within the requested scope *S*~R~ ⊆ *S*~C~
173. replace all (1): A future consent validity interval will be represented as -> The consent validity interval is represented as
174. cover date -> September 2026
175. reference capitalisation: Futuredid: -> FutureDID:
176. reference capitalisation: A xinjiang case study -> A Xinjiang case study
177. reference capitalisation: Risk and ucon-based -> Risk and UCON-based
178. reference capitalisation: secure iot: -> secure IoT:
179. reference capitalisation: healthcare iot: -> healthcare IoT:
180. reference capitalisation: with tee-enabled sensing and byzantine-resilient -> with TEE-enabled sensing and Byzantine-resilient
181. reference capitalisation: Dp-did: -> DP-DID:
182. colon after fourth SRQ
183. colon after fifth SRQ
184. colon after sixth SRQ
185. lead-in for Eq. (21)
186. delete: where *S*~R~ represents the requested data scope and *S*~C~ represents
187. note: Chapter numbers in Tables 3, 4 and 11 refer to the planned t
188. reference: *IEEE communications surveys & tutorials
189. reference: *BMC nursing*
190. reference: *IEEe Access*
191. reference: *Digital health*
192. reference: *European journal of health law*
193. reference: *Journal of systems architecture*
194. reference: with pediatric patients and their guardi
195. Australian spelling: 47 words
196. naming RQ -> SRQ: 21 occurrences
