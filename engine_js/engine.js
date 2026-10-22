/* Inkreel engine: composes a full frame (background, props, actors, fx, bubbles, grain). */
(function (g) {
'use strict';
const NS = g.Inkreel;
const { VW, VH, clamp } = NS;

const DEFCHAR = { height: 300, skin: '#8a5a3b', hair: '#1b1210', hair_style: 'short', top: '#c8553d', bottom: '#2f3a4f', accent: '#e2b04a', outfit: 'tee', legs: 'pants', build: 'average', weapon: 'none' };
const CHARS = new WeakMap();
function resolveChars(project) {
  let c = CHARS.get(project);
  if (c) return c;
  c = {};
  for (const id of Object.keys(project.characters || {})) c[id] = Object.assign({}, DEFCHAR, project.characters[id], { id });
  for (const s of project.scenes || []) for (const id of Object.keys(s.actors || {})) if (!c[id]) c[id] = Object.assign({}, DEFCHAR, { id });
  CHARS.set(project, c);
  return c;
}

function locate(project, T) {
  const tl = NS.timeline(project);
  if (!tl.scenes.length) return null;
  T = clamp(T, 0, Math.max(0, tl.total - 1e-6));
  for (let i = 0; i < tl.scenes.length; i++) {
    const s = tl.scenes[i];
    if (T < s.start + s.duration || i === tl.scenes.length - 1) return { index: i, t: T - s.start, scene: project.scenes[i], info: s, total: tl.total };
  }
  return null;
}

let GRAIN = null;
// seeded PRNG (mulberry32): exports must be byte-identical run to run
let _seed = 0x1ee1;
function rng() { _seed = (_seed + 0x6D2B79F5) | 0; let t = Math.imul(_seed ^ (_seed >>> 15), 1 | _seed); t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t; return ((t ^ (t >>> 14)) >>> 0) / 4294967296; }
function grainTile(createCanvas) {
  if (GRAIN || !createCanvas) return GRAIN;
  const c = createCanvas(256, 256), x = c.getContext('2d'), img = x.createImageData(256, 256);
  for (let i = 0; i < 256 * 256; i++) { const v = rng() * 255; img.data[i * 4] = v; img.data[i * 4 + 1] = v; img.data[i * 4 + 2] = v; img.data[i * 4 + 3] = 255; }
  x.putImageData(img, 0, 0);
  GRAIN = c; return c;
}

function renderScene(ctx, project, scene, t, opts) {
  opts = opts || {};
  const chars = resolveChars(project);
  const cam = NS.camState(scene, chars, t, project);
  cam.zoom = clamp(cam.zoom, 0.3, 4);
  const [sx, sy] = NS.shakeAt(scene, t);
  const boil = opts.boilFps || 12, frame = Math.floor(t * boil);
  const R = { scene, chars, proj: project, t, cam, frame, W: scene.width || VW };
  const gy = scene.groundY || 570; R.gy = gy;

  ctx.save();
  ctx.fillStyle = '#efe6d2'; ctx.fillRect(0, 0, VW, VH);
  ctx.beginPath(); ctx.rect(0, 0, VW, VH); ctx.clip();
  ctx.translate(VW / 2, VH / 2); ctx.scale(cam.zoom, cam.zoom); const hh = opts.handheld === false ? 0 : 1.6 * (typeof opts.handheld === 'number' ? opts.handheld : 1); ctx.translate(-cam.x + sx + (NS.vn(t * 0.7 + 3.1) - 0.5) * hh, -cam.y + sy + (NS.vn(t * 0.6 + 9.4) - 0.5) * hh);

  NS.drawBackground(ctx, R);
  const props = (scene.props || []).slice().sort((a, b) => (a.y || 0) - (b.y || 0));
  for (const p of props) if (p.layer !== 'front') NS.drawProp(ctx, R, p);

  const ids = Object.keys(scene.actors || {});
  const DRAG = { head: 0.45, eF: 0.55, eB: 0.55, aF: 0.3, aB: 0.3, wpn: 0.6, torso: 0.2 };
  const states = ids.map(id => {
    const st = NS.sampleActor(scene, chars, id, t, project);
    if (opts.drag === false || t < 0.1) return st;
    const old = NS.sampleActor(scene, chars, id, t - 0.075, project), pose = Object.assign({}, st.pose);
    for (const k in DRAG) if (typeof pose[k] === 'number' && typeof old.pose[k] === 'number') pose[k] = pose[k] + (old.pose[k] - pose[k]) * DRAG[k];
    return Object.assign({}, st, { pose });
  }).sort((a, b) => a.y - b.y);
  const S0 = { seed: frame * 7.13, wobble: opts.wobble === undefined ? 1 : opts.wobble, t };
  for (const st of states) NS.drawShadow(ctx, st, { seed: 1 });
  for (const st of states) { NS.drawActor(ctx, st, t, S0); NS.drawTrail(ctx, R, st.id, t); }
  for (const p of props) if (p.layer === 'front') NS.drawProp(ctx, R, p);
  NS.drawFX(ctx, R, 'world');
  ctx.restore();

  ctx.save();
  if (R.pal && R.pal.tint) { ctx.globalCompositeOperation = 'multiply'; ctx.fillStyle = R.pal.tint; ctx.fillRect(0, 0, VW, VH); ctx.globalCompositeOperation = 'source-over'; }
  NS.drawFX(ctx, R, 'screen');
  NS.drawBubbles(ctx, R);
  NS.drawCaptions(ctx, R);
  if (scene.letterbox) { ctx.fillStyle = '#0b0908'; ctx.fillRect(0, 0, VW, scene.letterbox); ctx.fillRect(0, VH - scene.letterbox, VW, scene.letterbox); }

  // film grain + soft paper vignette
  const gt = opts.createCanvas ? grainTile(opts.createCanvas) : (opts.grainTile || null);
  if (opts.grain !== false && opts.grain !== 0 && gt) {
    const pat = ctx.createPattern(gt, 'repeat');
    if (pat) { ctx.save(); ctx.globalAlpha = opts.grain === undefined || opts.grain === true ? 0.05 : +opts.grain; ctx.globalCompositeOperation = 'overlay'; ctx.translate((frame * 53) % 256, (frame * 97) % 256); ctx.fillStyle = pat; ctx.fillRect(-256, -256, VW + 512, VH + 512); ctx.restore(); }
  }
  const vg = ctx.createRadialGradient(VW / 2, VH / 2, VH * 0.55, VW / 2, VH / 2, VH * 1.0); vg.addColorStop(0, 'rgba(40,20,10,0)'); vg.addColorStop(1, 'rgba(40,20,10,' + (opts.vignette === undefined ? 0.16 : +opts.vignette) + ')'); ctx.fillStyle = vg; ctx.fillRect(0, 0, VW, VH);

  // transitions
  const tr = scene.transition || {}, dur = NS.sceneDuration(scene);
  const col = tr.color === 'white' ? '#ffffff' : '#000000';
  const din = tr.in === 'fade' ? (tr.dur || 0.5) : 0, dout = tr.out === 'fade' ? (tr.dur || 0.5) : 0;
  let ov = 0;
  if (din && t < din) ov = Math.max(ov, 1 - t / din);
  if (dout && t > dur - dout) ov = Math.max(ov, (t - (dur - dout)) / dout);
  if (ov > 0) { ctx.globalAlpha = clamp(ov); ctx.fillStyle = col; ctx.fillRect(0, 0, VW, VH); }
  ctx.restore();
}

function renderProject(ctx, project, T, opts) {
  const loc = locate(project, T);
  if (!loc) { ctx.fillStyle = '#efe6d2'; ctx.fillRect(0, 0, VW, VH); return null; }
  renderScene(ctx, project, loc.scene, loc.t, opts);
  return loc;
}

Object.assign(NS, { renderScene, renderProject, locate, resolveChars, DEFCHAR });
})(typeof window !== 'undefined' ? window : globalThis);
