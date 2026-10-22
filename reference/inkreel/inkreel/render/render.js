#!/usr/bin/env node
// Headless Inkreel renderer.
//   node render.js project.json out.mp4 [--scene ID] [--fps 24] [--scale 1]
//   node render.js project.json out.png --still 2.5 [--scene ID]       (single frame; time is local to the scene if --scene given)
const fs = require('fs');
const path = require('path');
const { spawn } = require('child_process');
const { createCanvas, GlobalFonts } = require('@napi-rs/canvas');

const args = process.argv.slice(2);
const pos = args.filter(a => !a.startsWith('--') && !/^\d/.test(a) || a.endsWith('.json') || a.endsWith('.mp4') || a.endsWith('.png') || a.endsWith('.webm'));
function opt(name, def) { const i = args.indexOf('--' + name); return i >= 0 ? args[i + 1] : def; }
const projPath = args[0], outPath = args[1];
if (!projPath || !outPath) { console.error('usage: render.js project.json out.(mp4|png) [--scene ID] [--fps 24] [--scale 1] [--still T]'); process.exit(2); }

const web = path.join(__dirname, '..', 'web');
for (const [f, fam] of [['patrick-hand-latin-400-normal.woff2', 'Patrick Hand'], ['bangers-latin-400-normal.woff2', 'Bangers']]) {
  const p = path.join(web, 'fonts', f); if (fs.existsSync(p)) GlobalFonts.registerFromPath(p, fam);
}
for (const f of ['core', 'draw', 'world', 'engine']) require(path.join(web, f + '.js'));
const NS = globalThis.Inkreel;
NS.setLibrary(JSON.parse(fs.readFileSync(path.join(web, 'library.json'), 'utf8')));

const project = JSON.parse(fs.readFileSync(projPath, 'utf8'));
const fps = parseFloat(opt('fps', (project.meta && project.meta.fps) || 24));
const scale = parseFloat(opt('scale', '1'));
const only = opt('scene', null);
const still = opt('still', null);
const W = Math.round(NS.VW * scale), H = Math.round(NS.VH * scale);

let p = project;
if (only) { const sc = project.scenes.filter(s => s.id === only); if (!sc.length) { console.error('no such scene: ' + only); process.exit(3); } p = Object.assign({}, project, { scenes: sc }); }
const tl = NS.timeline(p);
if (!tl.scenes.length) { console.error('project has no scenes'); process.exit(4); }

const canvas = createCanvas(W, H), ctx = canvas.getContext('2d');
const opts = { createCanvas };
function frameAt(T) { ctx.save(); ctx.scale(scale, scale); NS.renderProject(ctx, p, T, opts); ctx.restore(); }

(async () => {
  if (still !== null) {
    frameAt(parseFloat(still));
    fs.writeFileSync(outPath, canvas.toBuffer('image/png'));
    console.log('wrote ' + outPath); return;
  }
  const n = Math.max(1, Math.ceil(tl.total * fps));
  const ff = spawn('ffmpeg', ['-y', '-loglevel', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgba', '-s', `${W}x${H}`, '-r', String(fps), '-i', '-', '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '20', '-preset', 'medium', '-movflags', '+faststart', outPath], { stdio: ['pipe', 'inherit', 'inherit'] });
  ff.on('error', e => { console.error('ffmpeg not found - install ffmpeg to export video (' + e.message + ')'); process.exit(5); });
  const done = new Promise(res => ff.on('close', res));
  for (let i = 0; i < n; i++) {
    frameAt(i / fps);
    const buf = canvas.data();
    if (!ff.stdin.write(buf)) await new Promise(r => ff.stdin.once('drain', r));
    if (i % 12 === 0 || i === n - 1) process.stdout.write(`frame ${i + 1}/${n}\n`);
  }
  ff.stdin.end();
  const code = await done;
  console.log(code === 0 ? 'wrote ' + outPath : 'ffmpeg failed');
  process.exit(code === 0 ? 0 : 6);
})();
