# Figures 41 to 43 (Section 6.8.13)

- `eval_data.js` is generated from the measured facts (five anchored Sepolia transactions, submit-to-confirmation times, and the timing runs of 1 October 2026 in `docs/final_check/metrics.json`).
- `attacks.js` is generated from Table 18 of the report (scenario, targeted component, outcome before and after the hardening).
- `gen_eval.html` draws the three charts as SVG. `render_eval.js` renders each chart to PNG with headless Chromium at twice the CSS resolution.

Colours: mint blue `#2a78d6`, revocation orange `#eb6834`; status icons use green `#0ca30c` (refused) and red `#d03b3b` (accepted), always with a text label.
Each chart is sized so that, placed at the 6.25-inch text width, labels print at about 7 to 8 pt.
