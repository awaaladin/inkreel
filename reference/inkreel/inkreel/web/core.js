/* Inkreel core: math, library, timeline sampling, skeleton solver, camera.
   Runs in the browser (window.Inkreel) and Node (globalThis.Inkreel). */
(function (g) {
'use strict';
const NS = g.Inkreel = g.Inkreel || {};
const VW = 1280, VH = 720, TAU = Math.PI * 2, D2R = Math.PI / 180;

const clamp = (v, a = 0, b = 1) => Math.max(a, Math.min(b, v));
const lerp = (a, b, t) => a + (b - a) * t;
const sgn = v => (v < 0 ? -1 : 1);
const smooth = t => t * t * (3 - 2 * t);

const EASE = {
  linear: t => t,
  in: t => t * t,
  out: t => 1 - (1 - t) * (1 - t),
  inOut: t => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2),
  smooth: smooth,
  snap: t => 1 - Math.pow(1 - t, 4),
  back: t => { const c1 = 1.70158, c3 = c1 + 1; return 1 + c3 * Math.pow(t - 1, 3) + c1 * Math.pow(t - 1, 2); },
  hold: t => (t < 1 ? 0 : 1),
  elastic: t => (t === 0 || t === 1 ? t : Math.pow(2, -10 * t) * Math.sin((t * 10 - 0.75) * (TAU / 3)) + 1),
};
const ease = (name, t) => (EASE[name] || EASE.smooth)(clamp(t));

// noise
function h1(n) { const s = Math.sin(n * 127.1 + 311.7) * 43758.5453; return s - Math.floor(s); }
function vn(x) { const i = Math.floor(x), f = x - i, u = f * f * (3 - 2 * f); return lerp(h1(i), h1(i + 1), u); }
const wob = (seed, i) => (vn(seed + i * 1.37) - 0.5) * 2;
function strHash(s) { let h = 7; for (let i = 0; i < s.length; i++) h = (h * 31 + s.charCodeAt(i)) % 100003; return h; }

// colour helpers (hex only)
function hexToRgb(h) {
  if (typeof h !== 'string') return [128, 128, 128];
  h = h.trim().replace('#', '');
  if (!/^[0-9a-fA-F]{3}([0-9a-fA-F]{3})?$/.test(h)) return [128, 128, 128];
  if (h.length === 3) h = h.split('').map(c => c + c).join('');
  const n = parseInt(h, 16);
  return [(n >> 16) & 255, (n >> 8) & 255, n & 255];
}
const rgbStr = (r, g, b, a = 1) => (a >= 1 ? `rgb(${r | 0},${g | 0},${b | 0})` : `rgba(${r | 0},${g | 0},${b | 0},${a})`);
function shade(hex, amt) {
  const [r, g, b] = hexToRgb(hex);
  return amt >= 0 ? rgbStr(lerp(r, 255, amt), lerp(g, 255, amt), lerp(b, 255, amt)) : rgbStr(r * (1 + amt), g * (1 + amt), b * (1 + amt));
}
function alpha(hex, a) { const [r, g, b] = hexToRgb(hex); return rgbStr(r, g, b, a); }
function mixHex(a, b, t) { const A = hexToRgb(a), B = hexToRgb(b); return rgbStr(lerp(A[0], B[0], t), lerp(A[1], B[1], t), lerp(A[2], B[2], t)); }

// ---------------------------------------------------------------- library
const JOINTS = ['torso', 'head', 'aF', 'eF', 'aB', 'eB', 'tF', 'kF', 'tB', 'kB', 'wpn', 'rx', 'ry', 'rot'];
const UPPER = ['torso', 'head', 'aF', 'eF', 'aB', 'eB', 'wpn'];
let LIB = { stances: { idle: { torso: 2, head: 0, aF: 7, eF: 16, aB: -7, eB: 14, tF: 6, kF: -4, tB: -6, kB: -4, wpn: 8, rx: 0, ry: 0, rot: 0 } }, actions: {}, emotions: { neutral: { brow: 0, browY: 0, eye: 1, mouth: 'flat' } } };
function setLibrary(l) { LIB = l; }
const getLibrary = () => LIB;

const WEAPONS = {
  none: { len: 0 }, sword: { len: 0.44, grip: 0.0 }, katana: { len: 0.55, grip: 0.0 },
  staff: { len: 1.0, grip: 0.3 }, spear: { len: 1.1, grip: 0.3 }, club: { len: 0.42, grip: 0.0 },
  greatblade: { len: 0.8, grip: 0.0 }, dagger: { len: 0.24, grip: 0.0 },
};
const REST = { greatblade: { aF: 40, eF: 110, wpn: 45 }, club: { aF: 40, eF: 110, wpn: 45 }, staff: { wpn: 157 }, spear: { wpn: 157 } };
const BUILD = { slim: 0.82, average: 1, strong: 1.25, heavy: 1.5, child: 0.9 };

function mixPose(a, b, t) { const o = {}; for (const j of JOINTS) o[j] = lerp(a[j] || 0, b[j] || 0, t); return o; }
function fullPose(p) { const o = {}; for (const j of JOINTS) o[j] = p && p[j] !== undefined ? p[j] : 0; return o; }

// ---------------------------------------------------------------- prep
const PREP = new WeakMap();
function resolveKeys(keys) {
  const out = (keys || []).map(k => {
    let pose = k.pose;
    if (typeof pose === 'string') pose = LIB.stances[pose] || {};
    return { t: k.t, pose: pose || {}, ease: k.ease || 'smooth' };
  }).sort((a, b) => a.t - b.t);
  if (!out.length || out[0].t > 0) out.unshift({ t: 0, pose: {}, ease: 'smooth' });
  if (out[out.length - 1].t < 1) out.push({ t: 1, pose: {}, ease: 'smooth' });
  return out;
}

function prep(scene, proj) {
  let p = PREP.get(scene);
  if (p) return p;
  p = { actors: {} };
  PREP.set(scene, p);
  const custom = (proj && proj.actions) || {};
  for (const id of Object.keys(scene.actors || {})) {
    const A = scene.actors[id], q = {};
    let cx = A.x || 0, cy = A.y || 0, dist = 0;
    q.moves = (A.moves || []).slice().sort((a, b) => a.t - b.t).map(m => {
      const tx = m.x !== undefined && m.x !== null ? m.x : cx, ty = m.y !== undefined && m.y !== null ? m.y : cy;
      const len = Math.hypot(tx - cx, ty - cy);
      const o = Object.assign({}, m, { fx: cx, fy: cy, tx, ty, len, d0: dist, dur: Math.max(0.05, m.dur || 1) });
      cx = tx; cy = ty; dist += len; return o;
    });
    const fe = [];
    for (const f of A.faces || []) fe.push({ t: f.t, dir: f.dir, target: f.target });
    for (const m of q.moves) if (m.autoFace !== false && m.style !== 'backstep' && Math.abs(m.tx - m.fx) > 1) fe.push({ t: m.t, dir: sgn(m.tx - m.fx) });
    q.actions = [];
    const st = [];
    for (const s of A.stances || []) st.push({ t: s.t, stance: s.stance, blend: s.blend === undefined ? 0.3 : s.blend });
    for (const a of A.actions || []) {
      const def = custom[a.action] || LIB.actions[a.action];
      if (!def) continue;
      const dur = Math.max(0.1, a.dur || def.dur || 0.8);
      q.actions.push({
        t: a.t, dur, keys: resolveKeys(def.keys), mask: def.mask || 'full', trail: def.trail, face: def.face,
        intensity: a.intensity === undefined ? 1 : a.intensity,
        dx: (a.dx !== undefined ? a.dx : def.dx) || 0, dxSpan: def.dxSpan || 0.8, name: a.action,
      });
      if (def.endStance) st.push({ t: a.t + dur, stance: def.endStance, blend: 0.02 });
      if (a.target) fe.push({ t: a.t, target: a.target });
    }
    q.actions.sort((a, b) => a.t - b.t);
    q.face = fe.sort((a, b) => a.t - b.t);
    q.stances = st.sort((a, b) => a.t - b.t);
    q.emotes = (A.emotes || []).slice().sort((a, b) => a.t - b.t);
    q.says = (A.says || []).slice().sort((a, b) => a.t - b.t);
    p.actors[id] = q;
  }
  return p;
}

// ---------------------------------------------------------------- sampling
function basePos(A, q, t) {
  let x = A.x || 0, y = A.y || 0, speed = 0, style = null, dist = 0, vdir = 1;
  for (const m of q.moves) {
    if (t < m.t) break;
    const p = clamp((t - m.t) / m.dur), e = ease(m.ease || 'smooth', p);
    x = m.fx + (m.tx - m.fx) * e; y = m.fy + (m.ty - m.fy) * e; dist = m.d0 + m.len * e;
    if (p < 1) {
      style = m.style || 'walk'; vdir = sgn(m.tx - m.fx);
      const e2 = ease(m.ease || 'smooth', clamp(p + 0.02 / m.dur));
      speed = m.len * (e2 - e) / 0.02;
    } else { style = null; speed = 0; }
  }
  return { x, y, speed: Math.abs(speed), style, dist, vdir };
}

function facingAt(scene, id, t) {
  const P = prep(scene), A = scene.actors[id], q = P.actors[id];
  let d = A.facing || 1;
  for (const f of q.face) {
    if (f.t > t) break;
    if (f.target) {
      const tq = P.actors[f.target], tA = scene.actors[f.target];
      if (tq) { const dx = basePos(tA, tq, t).x - basePos(A, q, t).x; if (Math.abs(dx) > 2) d = sgn(dx); }
    } else if (f.dir) d = f.dir;
  }
  return d;
}

function stancePoseAt(q, t) {
  let cur = fullPose(LIB.stances.idle);
  for (const ev of q.stances) {
    if (t < ev.t) break;
    const nx = fullPose(LIB.stances[ev.stance] || LIB.stances.idle);
    const p = ev.blend > 0 ? smooth(clamp((t - ev.t) / ev.blend)) : 1;
    if (p < 1) return mixPose(cur, nx, p);
    cur = nx;
  }
  return cur;
}

function actionPose(act, u, base) {
  const keys = act.keys;
  let i = 0;
  while (i < keys.length - 2 && u > keys[i + 1].t) i++;
  const k0 = keys[i], k1 = keys[i + 1];
  let p = clamp((u - k0.t) / ((k1.t - k0.t) || 1e-6));
  p = EASE[k1.ease || 'smooth'] ? EASE[k1.ease || 'smooth'](p) : smooth(p);
  const out = {};
  for (const j of JOINTS) {
    const v0 = k0.pose[j] !== undefined ? k0.pose[j] : base[j];
    const v1 = k1.pose[j] !== undefined ? k1.pose[j] : base[j];
    let v = lerp(v0, v1, p);
    if (act.intensity !== 1) v = base[j] + (v - base[j]) * act.intensity;
    out[j] = v;
  }
  return out;
}

const STRIDE = { walk: 0.62, sneak: 0.46, run: 0.98 };

function gaitPose(phase, style, base) {
  const run = style === 'run', sneak = style === 'sneak';
  const s = Math.sin(phase * TAU), c = Math.cos(phase * TAU);
  const A = run ? 58 : sneak ? 24 : 30, K = run ? 100 : sneak ? 60 : 50, AA = run ? 55 : 28;
  const o = {};
  o.tF = A * s; o.tB = -A * s;
  o.kF = -K * Math.max(0, c) - 4; o.kB = -K * Math.max(0, -c) - 4;
  o.aF = -AA * s + (run ? 20 : 4); o.aB = AA * s + (run ? 20 : -4);
  o.eF = run ? 85 + 25 * Math.max(0, -s) : 18 + 22 * Math.max(0, -s);
  o.eB = run ? 85 + 25 * Math.max(0, s) : 18 + 22 * Math.max(0, s);
  o.torso = run ? 15 : sneak ? 22 : 4;
  o.head = run ? -8 : 0;
  o.ry = run ? -0.05 * Math.max(0, Math.sin(2 * phase * TAU + 0.5)) : 0;
  return o;
}

function emotionAt(q, t, act) {
  let e = 'neutral';
  for (const em of q.emotes) { if (em.t > t) break; e = em.emotion; }
  for (const s of q.says) { if (t >= s.t && t < s.t + s.dur && s.emotion) e = s.emotion; }
  if (act && act.face) e = act.face;
  return e;
}

// returns everything needed to draw / anchor an actor at time t
function sampleActor(scene, chars, id, t, proj) {
  const P = prep(scene, proj), A = scene.actors[id], q = P.actors[id];
  const ch = chars[id] || {};
  const bp = basePos(A, q, t);
  const facing = facingAt(scene, id, t);
  let base = stancePoseAt(q, t);
  const ph = strHash(id) * 0.37;
  const downish = Math.abs(base.rot) > 45;

  // breathing
  const br = Math.sin(t * 2.3 + ph);
  base = Object.assign({}, base);
  const wk = ch.weapon && ch.weapon !== 'none' ? ch.weapon : null;
  if (wk && REST[wk] && Math.abs(base.wpn - 8) < 0.6 && !downish) Object.assign(base, REST[wk]);
  if (!downish) { base.ry += 0.003 * br; base.torso += 0.9 * br; base.aF += 1.5 * br; base.aB -= 1.2 * br; }
  else base.torso += 0.4 * br;

  // gait (blend by speed)
  let pose = Object.assign({}, base);
  if (bp.style && bp.style !== 'slide' && bp.style !== 'dash' && !downish) {
    const st = bp.style === 'backstep' ? 'walk' : bp.style;
    const strideLen = (STRIDE[st] || 0.62) * (ch.height || 300);
    const relSign = bp.style === 'backstep' ? -1 : (bp.vdir * facing >= 0 ? 1 : -1);
    const phase = (bp.dist / strideLen) * relSign;
    const w = smooth(clamp(bp.speed / (st === 'run' ? 140 : 55)));
    const gp = gaitPose(phase, st, base);
    for (const j of Object.keys(gp)) pose[j] = j === 'ry' ? base.ry + gp.ry * w : lerp(base[j], gp[j], w);
    if (wk) { // weapon hand stays steady while travelling
      const target = base.aF + base.eF + base.wpn;
      pose.aF = lerp(base.aF, gp.aF, w * 0.25); pose.eF = lerp(base.eF, gp.eF, w * 0.25);
      pose.wpn = target - (pose.aF + pose.eF);
    }
  }

  // speaking + gesture layer
  let say = null;
  for (const s of q.says) if (t >= s.t && t < s.t + s.dur) say = s;
  let active = null;
  for (const a of q.actions) if (t >= a.t && t < a.t + a.dur) active = a;
  if (say && !(active && active.mask === 'full') && !downish) {
    const gs = Math.sin(t * 3.1 + ph), nod = Math.sin(t * 7.3 + ph);
    pose.head += 2.2 * nod; pose.torso += 0.8 * gs;
    if (!(active && active.mask !== 'full')) { pose.aF += 16 * (0.5 + 0.5 * gs); pose.eF += 18 * (0.5 + 0.5 * gs); }
  }

  // actions
  if (active) {
    const u = (t - active.t) / active.dur;
    const ap = actionPose(active, u, pose);
    const keys = active.mask === 'full' ? JOINTS : UPPER;
    for (const j of keys) pose[j] = ap[j];
    // rx/ry always come from action for 'upper' too (e.g. hops)
    if (active.mask === 'upper') { pose.rx = ap.rx; pose.ry = ap.ry; }
  }

  // persistent displacement
  let dxSum = 0;
  for (const a of q.actions) {
    if (!a.dx || t < a.t) continue;
    const u = clamp((t - a.t) / (a.dur * a.dxSpan));
    const dir = facingAt(scene, id, a.t);
    dxSum += dir * a.dx * EASE.out(u);
  }

  // face
  const emo = emotionAt(q, t, active);
  let mouth = 0;
  if (say) { const prog = (t - say.t) / (say.dur * 0.75); if (prog < 1) mouth = 0.35 + 0.65 * Math.abs(Math.sin(t * 17 + ph)) * (0.6 + 0.4 * Math.sin(t * 5.1)); }
  const blink = ((t + ph) % 3.6) < 0.11;

  return { id, x: bp.x + dxSum, y: bp.y + (scene.groundY || 570), facing, pose, emotion: emo, mouth, blink, say, active, speed: bp.speed, ch };
}

// ---------------------------------------------------------------- skeleton
function dirv(a) { return [Math.sin(a * D2R), Math.cos(a * D2R)]; }
function upv(a) { return [Math.sin(a * D2R), -Math.cos(a * D2R)]; }
const add = (a, b) => [a[0] + b[0], a[1] + b[1]];
const mul = (a, k) => [a[0] * k, a[1] * k];

function dims(ch) {
  const H = ch.height || 300, hs = ch.headScale || 1;
  return { H, torso: 0.3 * H, neck: 0.03 * H, headR: 0.085 * H * hs, up: 0.165 * H, fore: 0.155 * H, thigh: 0.225 * H, shin: 0.215 * H, foot: 0.085 * H, b: BUILD[ch.build || 'average'] || 1 };
}

// local coordinates, facing +x, hip at origin, ground at y = 0 after solve
function solve(pose, ch) {
  const d = dims(ch), H = d.H;
  const P = {};
  P.hip = [0, 0];
  P.sh = add(P.hip, mul(upv(pose.torso), d.torso));
  P.hd = add(P.sh, mul(upv(pose.torso + pose.head), d.neck + d.headR * 0.95));
  P.elF = add(P.sh, mul(dirv(pose.aF), d.up));
  P.hnF = add(P.elF, mul(dirv(pose.aF + pose.eF), d.fore));
  P.elB = add(P.sh, mul(dirv(pose.aB), d.up));
  P.hnB = add(P.elB, mul(dirv(pose.aB + pose.eB), d.fore));
  P.knF = add(P.hip, mul(dirv(pose.tF), d.thigh));
  P.anF = add(P.knF, mul(dirv(pose.tF + pose.kF), d.shin));
  P.toF = add(P.anF, mul(dirv(pose.tF + pose.kF + 90), d.foot));
  P.knB = add(P.hip, mul(dirv(pose.tB), d.thigh));
  P.anB = add(P.knB, mul(dirv(pose.tB + pose.kB), d.shin));
  P.toB = add(P.anB, mul(dirv(pose.tB + pose.kB + 90), d.foot));
  // rotate about hip
  const r = pose.rot * D2R, cs = Math.cos(r), sn = Math.sin(r);
  for (const k of Object.keys(P)) { const [x, y] = P[k]; P[k] = [x * cs - y * sn, x * sn + y * cs]; }
  // ground contact
  const cand = [['anF', 0.035], ['anB', 0.035], ['toF', 0.03], ['toB', 0.03], ['knF', 0.04], ['knB', 0.04], ['hip', 0.06], ['sh', 0.06], ['hd', 0.085], ['elF', 0.03], ['elB', 0.03]];
  let maxY = -1e9;
  for (const [k, rr] of cand) maxY = Math.max(maxY, P[k][1] + rr * H);
  const dy = -maxY + pose.ry * H, dx = pose.rx * H;
  for (const k of Object.keys(P)) P[k] = [P[k][0] + dx, P[k][1] + dy];
  P.headAngle = pose.torso + pose.head + pose.rot;
  P.torsoAngle = pose.torso + pose.rot;
  P.foreAngle = pose.aF + pose.eF + pose.rot;
  P.wpnAngle = pose.aF + pose.eF + pose.wpn + pose.rot;
  P.dims = d;
  // weapon
  const w = WEAPONS[ch.weapon || 'none'] || WEAPONS.none;
  if (w.len) {
    const dv = dirv(P.wpnAngle), L = w.len * H;
    P.wBase = add(P.hnF, mul(dv, -w.grip * H));
    P.wTip = add(P.hnF, mul(dv, L - w.grip * H));
  } else { P.wBase = P.hnF; P.wTip = P.hnF; }
  return P;
}

function toWorld(st, p) { return [st.x + st.facing * p[0], st.y + p[1]]; }

function anchorPos(scene, chars, id, part, t, proj) {
  const A = scene.actors[id];
  if (!A) return null;
  const st = sampleActor(scene, chars, id, t, proj), P = solve(st.pose, st.ch);
  let p;
  switch (part) {
    case 'head': p = P.hd; break;
    case 'chest': p = [lerp(P.hip[0], P.sh[0], 0.75), lerp(P.hip[1], P.sh[1], 0.75)]; break;
    case 'hip': p = P.hip; break;
    case 'hand_front': p = P.hnF; break;
    case 'hand_back': p = P.hnB; break;
    case 'foot_front': p = P.toF; break;
    case 'foot_back': p = P.toB; break;
    case 'weapon_tip': p = P.wTip; break;
    case 'feet': p = [(P.anF[0] + P.anB[0]) / 2, 0]; break;
    default: p = [lerp(P.hip[0], P.hd[0], 0.5), lerp(P.hip[1], P.hd[1], 0.5)];
  }
  return toWorld(st, p);
}

// ---------------------------------------------------------------- timeline & camera
function sceneEnd(scene) {
  let m = 0;
  for (const A of Object.values(scene.actors || {})) {
    for (const mv of A.moves || []) m = Math.max(m, mv.t + (mv.dur || 1));
    for (const a of A.actions || []) m = Math.max(m, a.t + (a.dur || 0.8));
    for (const s of A.says || []) m = Math.max(m, s.t + (s.dur || 2));
  }
  for (const f of scene.fx || []) m = Math.max(m, f.t + (f.dur || 0.5));
  for (const c of scene.captions || []) m = Math.max(m, c.t + (c.dur || 2));
  for (const c of scene.camera || []) m = Math.max(m, c.t + (c.dur || 0));
  return m;
}
function sceneDuration(scene) { return scene.duration ? scene.duration : Math.max(2, sceneEnd(scene) + 0.6); }
function timeline(project) {
  let t = 0; const scenes = [];
  for (const s of project.scenes || []) { const d = sceneDuration(s); scenes.push({ id: s.id, name: s.name, start: t, duration: d }); t += d; }
  return { scenes, total: t };
}

function frameTarget(scene, chars, op, t, proj) {
  const ids = (op.chars && op.chars.length ? op.chars : Object.keys(scene.actors || {})).filter(i => scene.actors[i]);
  if (!ids.length) return { x: VW / 2, y: VH / 2, zoom: 1 };
  let minx = 1e9, maxx = -1e9, miny = 1e9, maxy = -1e9;
  for (const id of ids) {
    const st = sampleActor(scene, chars, id, t, proj), P = solve(st.pose, st.ch), H = st.ch.height || 300;
    const x = st.x + st.facing * P.hip[0];
    minx = Math.min(minx, x - 0.3 * H); maxx = Math.max(maxx, x + 0.3 * H);
    miny = Math.min(miny, st.y + P.hd[1] - 0.12 * H); maxy = Math.max(maxy, st.y + 0.05 * H);
  }
  const pad = op.pad !== undefined ? op.pad : 220;
  const w = (maxx - minx) + pad * 2, h = (maxy - miny) + pad * 0.7;
  const zoom = clamp(Math.min(VW / w, VH / h), op.minZoom || 0.6, op.maxZoom || 2.4);
  return { x: (minx + maxx) / 2, y: (miny + maxy) / 2 + (op.dy || 0), zoom };
}

function camState(scene, chars, t, proj) {
  const def = { x: scene.camStartX !== undefined ? scene.camStartX : VW / 2, y: VH / 2, zoom: 1 };
  const ops = (scene.camera || []).filter(o => o.kind !== 'shake').slice().sort((a, b) => a.t - b.t);
  if (!ops.length) return def;
  function stateAt(i, tt) {
    const op = ops[i];
    const from = i > 0 ? stateAt(i - 1, op.t) : def;
    const dur = Math.max(0.0001, op.dur || 0);
    if (op.kind === 'follow' || op.kind === 'frame') {
      const target = op.kind === 'follow'
        ? (() => { const pos = anchorPos(scene, chars, op.char, 'center', tt, proj) || [VW / 2, VH / 2]; return { x: pos[0] + (op.ox || 0), y: pos[1] + (op.oy || -20), zoom: op.zoom || 1.15 }; })()
        : frameTarget(scene, chars, op, tt, proj);
      const blend = Math.max(0.05, op.blend === undefined ? 0.6 : op.blend);
      const p = smooth(clamp((tt - op.t) / blend));
      return { x: lerp(from.x, target.x, p), y: lerp(from.y, target.y, p), zoom: lerp(from.zoom, target.zoom, p) };
    }
    const tg = { x: op.x !== undefined ? op.x : from.x, y: op.y !== undefined ? op.y : from.y, zoom: op.zoom !== undefined ? op.zoom : from.zoom };
    const p = op.kind === 'set' ? 1 : ease(op.ease || 'inOut', (tt - op.t) / dur);
    return { x: lerp(from.x, tg.x, p), y: lerp(from.y, tg.y, p), zoom: lerp(from.zoom, tg.zoom, p) };
  }
  let idx = -1;
  for (let i = 0; i < ops.length; i++) if (ops[i].t <= t) idx = i;
  return idx < 0 ? def : stateAt(idx, t);
}

function shakeAt(scene, t) {
  let sx = 0, sy = 0;
  for (const c of scene.camera || []) {
    if (c.kind !== 'shake') continue;
    const dur = c.dur || 0.4;
    if (t < c.t || t > c.t + dur) continue;
    const u = (t - c.t) / dur, decay = Math.pow(1 - u, 1.6), a = (c.amp || 14) * decay, f = c.freq || 28;
    sx += (vn(t * f) - 0.5) * 2 * a; sy += (vn(t * f + 77.7) - 0.5) * 2 * a;
  }
  return [sx, sy];
}

Object.assign(NS, {
  VW, VH, TAU, D2R, clamp, lerp, sgn, smooth, ease, EASE, h1, vn, wob, strHash, hexToRgb, rgbStr, shade, alpha, mixHex,
  JOINTS, setLibrary, getLibrary, WEAPONS, BUILD, prep, basePos, facingAt, sampleActor, solve, toWorld, anchorPos, dims,
  sceneEnd, sceneDuration, timeline, camState, shakeAt, dirv, upv,
});
})(typeof window !== 'undefined' ? window : globalThis);
