#!/usr/bin/env node
// Headless runner for the JS engine, behind the Python RenderBackend.
//   node run.js still <bundle.json> <out.png> --t SECONDS [--scale 1]
//   node run.js video <bundle.json> <out.mp4|dir> [--fps 24] [--scale 1] [--t0 0] [--t1 N] [--ffmpeg path] [--frames-dir dir]
// <bundle.json> = { meta, style, characters, scenes: [...], actions }  (compiled by server/inkreel/render.py)
// Times are bundle-global (scenes play back to back). Output is deterministic: no wall clock, seeded grain.
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { createCanvas, GlobalFonts } = require('@napi-rs/canvas');

const [cmd, bundlePath, outPath, ...rest] = process.argv.slice(2);
function opt(name, def) { const i = rest.indexOf('--' + name); return i >= 0 ? rest[i + 1] : def; }
if (!cmd || !bundlePath || !outPath) { console.error('usage: run.js still|video bundle.json out [--t T] [--fps N] [--scale S]'); process.exit(2); }

for (const [f, fam] of [['patrick-hand-latin-400-normal.woff2', 'Patrick Hand'], ['bangers-latin-400-normal.woff2', 'Bangers']]) {
  const p = path.join(__dirname, 'fonts', f); if (fs.existsSync(p)) GlobalFonts.registerFromPath(p, fam);
}
for (const f of ['core', 'draw', 'world', 'engine']) require(path.join(__dirname, f + '.js'));
const NS = globalThis.Inkreel;
const libDir = path.join(__dirname, '..', 'libraries');
const lib = { stances: JSON.parse(fs.readFileSync(path.join(libDir, 'stances.json'), 'utf8')), emotions: JSON.parse(fs.readFileSync(path.join(libDir, 'emotions.json'), 'utf8')), actions: {} };
for (const f of fs.readdirSync(path.join(libDir, 'actions'))) lib.actions[f.replace(/\.json$/, '')] = JSON.parse(fs.readFileSync(path.join(libDir, 'actions', f), 'utf8'));
NS.setLibrary(lib);

const bundle = JSON.parse(fs.readFileSync(bundlePath, 'utf8'));
const st = bundle.style || {};
const fps = parseFloat(opt('fps', (bundle.meta && bundle.meta.fps) || st.fps || 24));
const scale = parseFloat(opt('scale', '1'));
const W = Math.round(NS.VW * scale), H = Math.round(NS.VH * scale);
const tl = NS.timeline(bundle);
if (!tl.scenes.length) { console.error('bundle has no scenes'); process.exit(4); }
const canvas = createCanvas(W, H), ctx = canvas.getContext('2d');
const eopts = { createCanvas, boilFps: st.boil_fps || 12, wobble: st.wobble === undefined ? 1 : st.wobble, grain: st.grain === undefined ? 0.05 : st.grain,
  vignette: st.vignette === undefined ? 0.16 : st.vignette, handheld: st.handheld === undefined ? 1 : st.handheld };
const twos = st.animate_on === 'twos' ? (st.twos_fps || 12) : 0;
function frameAt(T) { if (twos) T = Math.floor(T * twos + 1e-6) / twos; ctx.save(); ctx.scale(scale, scale); NS.renderProject(ctx, bundle, T, eopts); ctx.restore(); }

(async () => {
  if (cmd === 'still') { frameAt(parseFloat(opt('t', '0'))); fs.writeFileSync(outPath, canvas.toBuffer('image/png')); console.log('wrote ' + outPath); return; }
  const t0 = parseFloat(opt('t0', '0')), t1 = parseFloat(opt('t1', String(tl.total)));
  const n = Math.max(1, Math.ceil((t1 - t0) * fps - 1e-6));
  const framesDir = opt('frames-dir', null);
  let ff = null, done = null;
  if (framesDir) fs.mkdirSync(framesDir, { recursive: true });
  else {
    ff = spawn(opt('ffmpeg', 'ffmpeg'), ['-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${W}x${H}`, '-r', String(fps), '-i', '-',
      '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'medium', '-movflags', '+faststart', outPath], { stdio: ['pipe', 'inherit', 'inherit'] });
    ff.on('error', e => { console.error('ffmpeg not found: ' + e.message); process.exit(5); });
    done = new Promise(res => ff.on('close', res));
  }
  for (let i = 0; i < n; i++) {
    frameAt(t0 + i / fps);
    if (framesDir) fs.writeFileSync(path.join(framesDir, 'f' + String(i).padStart(6, '0') + '.png'), canvas.toBuffer('image/png'));
    else if (!ff.stdin.write(canvas.data())) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 12 === 0 || i === n - 1) process.stdout.write(`frame ${i + 1}/${n}\n`);
  }
  if (ff) { ff.stdin.end(); const code = await done; console.log(code === 0 ? 'wrote ' + outPath : 'ffmpeg failed'); process.exit(code === 0 ? 0 : 6); }
  console.log('wrote frames to ' + framesDir);
})();
