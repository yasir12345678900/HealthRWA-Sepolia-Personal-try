# CA2 presentation: notes

`Yasir_Alyoubi_CA2_Presentation.pptx` is a 43-slide deck built from the CA2 report. It covers the whole report in the order of the chapters. Every slide has speaker notes. The PDF next to it is a LibreOffice export for quick viewing only. Open the .pptx in PowerPoint for the real layout and fonts (Cambria and Calibri).

## Structure

| Part | Slides | Chapters | Content |
|---|---|---|---|
| Title and agenda | 1–2 | – | Title, five parts of the talk |
| A. Background and literature | 3–13 | 1–2 | Context, core problem, scope (Table 1.1), SLR method and search string, PRISMA flow, five requirements, study categories, requirement coverage, gaps, Table 2.10 |
| B. Research design | 14–17 | 3–4 | Research gap and main question, SRQ–RO mapping, Eq. 6, Eq. 7 and Eq. 24 |
| C. Architecture and solution | 18–28 | 5–6 | MVC architecture (Figure 5.1), trust predicates (Figure 5.3), end-to-end workflow (Figure 5.4), RO1–RO6 workflows (Figures 6.1–6.6), the six algorithms |
| D. HALAH prototype and evidence | 29–37 | 7 | Prototype workflow (Figure 7.6), patient, guardian, doctor and auditor subsystems (Figures 7.1–7.5), Table 7.2, tests (Table 7.3), Sepolia tokens (Table 7.4), limitations |
| E. Progress and research plan | 38–43 | 8–10 | Progress per RO, publication plan (Table 9.1), next-stage plan (Table 10.1), contributions, close |

## What differs from the report figures

- The flowcharts on slides 7, 19–27 and 30 are redrawn as native PowerPoint shapes, so the text can be read when projected and can be edited. The boxes, decisions and labels follow the report figures.
- The screenshots on slides 31 and 32 are cropped to the subsystem panels, with gold labels that point to the evidence (scope, validity window, 2/2 signatures, SBT, ACTIVE state, access granted). The captions say "(cropped)".
- Slide 33 shows the six event blocks of Figure 7.5 arranged in time order and numbered 1 to 6. The caption says so.
- The report is not changed.

## Timing

The speaker notes are about 5,500 words in total. Read in full, that is roughly 40 minutes. For a 20-minute slot, speak to the slide titles and the key point in each note, and skip the detail on slides 13, 28 and 34.

## Rebuilding the deck

The `source` folder holds the generator. `content.json` has the slide text and notes, `plan.json` the slide order and layouts, `build.js` the layouts, `diagrams.js` the native flowcharts, and `apply_qa.py` the review edits applied to the first draft.

```
cd source
npm install
node build.js content.json ../Yasir_Alyoubi_CA2_Presentation.pptx
```

The build reports any text box whose text may not fit, sets the proofing language to English (Australia) and writes schema-valid slide XML.
