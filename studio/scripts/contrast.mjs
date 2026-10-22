// WCAG AA check for the text/background pairs we actually use (fails the build if any pair is below 4.5:1, large text 3:1).
import fs from 'node:fs';
const t = JSON.parse(fs.readFileSync('src/design/tokens.json', 'utf8'));
const lum = h => { const n = parseInt(h.slice(1), 16); return [n >> 16, (n >> 8) & 255, n & 255].map(v => { v /= 255; return v <= .03928 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4; }).reduce((a, v, i) => a + v * [.2126, .7152, .0722][i], 0); };
const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + .05) / (y + .05); };
const pairs = [['text', 'bg', 4.5], ['text', 'surface', 4.5], ['text', 'surface2', 4.5], ['textDim', 'bg', 4.5], ['textDim', 'surface', 4.5], ['textDim', 'surface2', 4.5],
  ['textFaint', 'surface', 4.5], ['accentText', 'accent', 4.5], ['accent', 'bg', 4.5], ['accent', 'surface', 4.5], ['teal', 'surface', 4.5], ['danger', 'surface', 4.5],
  ['ai', 'surface', 4.5], ['user', 'surface', 4.5], ['import', 'surface', 4.5], ['ok', 'surface', 4.5], ['warn', 'surface', 4.5], ['borderStrong', 'surface', 3]];
let bad = 0;
for (const th of ['dark', 'light']) for (const [f, b, min] of pairs) {
  const r = ratio(t.color[th][f], t.color[th][b]);
  if (r < min) { bad++; console.log(`FAIL ${th} ${f} on ${b}: ${r.toFixed(2)} < ${min}`); }
}
console.log(bad ? `${bad} contrast failures` : 'all pairs pass AA'); process.exit(bad ? 1 : 0);
