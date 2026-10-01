// usage: node render_eval.js f41 f42 f43   (needs playwright-core and a Chromium build; set CHROMIUM to its path)
const path = require('path');
const { chromium } = require('playwright-core');
(async () => {
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM || '/opt/pw-browsers/chromium', args: ['--no-sandbox'] });
  const p = await b.newPage({ deviceScaleFactor: 2 });
  await p.goto('file://' + path.join(__dirname, 'gen_eval.html'));
  for (const id of process.argv.slice(2)) { const el = await p.$('#' + id); await el.screenshot({ path: path.join(__dirname, id + '.png') }); console.log('ok', id); }
  await b.close();
})();
