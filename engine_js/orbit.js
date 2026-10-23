/* Inkreel orbit view: renders a scene as stacked flat layers in 3D (orthographic), so you can orbit/tilt/zoom around 2D animation.
   Every layer (backdrop, props, each character's back limbs / torso / head / front limbs) is a flat drawing placed at a depth z.
   For a plane at depth z the projection is an exact affine map, so the normal 2D drawing code is reused unchanged.
   Not a 3D model: at 90 degrees you see the layers edge-on, with their real separation. */
(function (g) {
'use strict';
const NS = g.Inkreel;
const { VW, VH, clamp } = NS;

function planeMat(v, fx, fy, z) {
  const cy = Math.cos(v.yaw), sy = Math.sin(v.yaw), cp = Math.cos(v.pitch), sp = Math.sin(v.pitch), s = v.scale;
  return { a: s * cy, b: s * sy * sp, c: 0, d: s * cp, e: VW / 2 + v.panX + s * (-fx * cy + z * sy), f: VH / 2 + v.panY + s * (-fy * cp - fx * sy * sp - z * cy * sp) };
}
function project(v, fx, fy, x, y, z) {
  const cy = Math.cos(v.yaw), sy = Math.sin(v.yaw), cp = Math.cos(v.pitch), sp = Math.sin(v.pitch), s = v.scale;
  const X = (x - fx) * cy + z * sy, zr = -(x - fx) * sy + z * cy, Y = (y - fy) * cp - zr * sp;
  return [VW / 2 + v.panX + s * X, VH / 2 + v.panY + s * Y, zr];
}
const setM = (ctx, m) => ctx.setTransform(m.a, m.b, m.c, m.d, m.e, m.f);

// darker copy of a character's colours, for the thickness slices behind it (no canvas filters: those are very slow without a GPU)
const TINT = {};
function tinted(ch, k) {
  const key = [ch.id, ch.skin, ch.hair, ch.top, ch.bottom, ch.accent, ch.boots, ch.weaponColor, k.toFixed(2)].join('|'); if (TINT[key]) return TINT[key];
  const dk = hex => { const [r, g, b] = NS.hexToRgb(hex), h2 = n => Math.max(0, Math.min(255, Math.round(n * k))).toString(16).padStart(2, '0'); return '#' + h2(r) + h2(g) + h2(b); };
  const c = Object.assign({}, ch);
  for (const f of ['skin', 'hair', 'top', 'bottom', 'accent', 'boots', 'weaponColor', 'brow']) if (typeof c[f] === 'string' && c[f][0] === '#') c[f] = dk(c[f]);
  return (TINT[key] = c);
}

function renderOrbit(ctx, project_, T, opts) {
  opts = opts || {};
  const loc = NS.locate(project_, T);
  if (!loc) { ctx.fillStyle = '#e9e2d3'; ctx.fillRect(0, 0, VW, VH); return null; }
  const scene = loc.scene, t = loc.t, chars = NS.resolveChars(project_);
  const cam = NS.camState(scene, chars, t, project_); cam.zoom = clamp(cam.zoom, 0.3, 4);
  const [sx, sy_] = NS.shakeAt(scene, t);
  const hh = typeof opts.handheld === 'number' ? 1.6 * opts.handheld : 1.6;
  const fx = cam.x - sx - (NS.vn(t * 0.7 + 3.1) - 0.5) * hh, fy = cam.y - sy_ - (NS.vn(t * 0.6 + 9.4) - 0.5) * hh;
  const ov = opts.view || {};
  const v = { yaw: (ov.yaw || 0) * Math.PI / 180, pitch: (ov.pitch || 0) * Math.PI / 180, scale: cam.zoom * (ov.zoom || 1), panX: ov.panX || 0, panY: ov.panY || 0 };
  const gy = scene.groundY || 570, W = scene.width || VW;
  const frame = Math.floor(t * (opts.boilFps || 12));
  const R = { scene, chars, proj: project_, t, cam, frame, W, gy };
  const flat = Math.abs(v.yaw) < 1e-4 && Math.abs(v.pitch) < 1e-4;

  ctx.setTransform(1, 0, 0, 1, 0, 0);
  ctx.globalAlpha = 1;
  ctx.fillStyle = opts.surround || '#1b1820'; ctx.fillRect(0, 0, VW, VH);
  ctx.save();
  ctx.beginPath(); ctx.rect(0, 0, VW, VH); ctx.clip();

  // ---- backdrop card (sky, far hills, sea, painted ground) at the back
  const zBack = -520;
  ctx.save(); setM(ctx, planeMat(v, fx, fy, zBack));
  const backface = Math.cos(v.yaw) < 0;
  // extend sky beyond the scene width so the card has body when orbiting
  ctx.save(); NS.drawBackground(ctx, R); ctx.restore();
  if (backface) { ctx.fillStyle = 'rgba(10,8,14,.55)'; ctx.fillRect(-2000, -2000, W + 4000, 5000); }
  ctx.restore();

  // ---- ground slab: a real horizontal plane (only visible once you tilt or orbit)
  if (!flat) {
    const pal = R.pal || {};
    const corners = [[-200, zBack], [W + 200, zBack], [W + 200, 420], [-200, 420]].map(([x, z]) => project(v, fx, fy, x, gy, z));
    ctx.beginPath(); corners.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.closePath();
    ctx.fillStyle = pal.ground || '#d9c38f'; ctx.fill();
    ctx.strokeStyle = pal.ink || '#2a2320'; ctx.lineWidth = 2; ctx.stroke();
    // grid lines so depth reads
    ctx.strokeStyle = 'rgba(40,30,20,.18)'; ctx.lineWidth = 1;
    for (let z = zBack; z <= 420; z += 100) { const a = project(v, fx, fy, -200, gy, z), b = project(v, fx, fy, W + 200, gy, z); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); }
    for (let x = 0; x <= W; x += 160) { const a = project(v, fx, fy, x, gy, zBack), b = project(v, fx, fy, x, gy, 420); ctx.beginPath(); ctx.moveTo(a[0], a[1]); ctx.lineTo(b[0], b[1]); ctx.stroke(); }
  }

  // ---- depth-sorted props and characters
  const items = [];
  for (const p of scene.props || []) { const z = p.layer === 'front' ? 170 : (p.y || 0) * 1.5 - 60; items.push({ kind: 'prop', p, z, x: p.x }); }
  const DRAG = { head: 0.45, eF: 0.55, eB: 0.55, aF: 0.3, aB: 0.3, wpn: 0.6, torso: 0.2 };
  for (const id of Object.keys(scene.actors || {})) {
    let st = NS.sampleActor(scene, chars, id, t, project_);
    if (opts.drag !== false && t >= 0.1) {
      const old = NS.sampleActor(scene, chars, id, t - 0.075, project_), pose = Object.assign({}, st.pose);
      for (const k in DRAG) if (typeof pose[k] === 'number' && typeof old.pose[k] === 'number') pose[k] += (old.pose[k] - pose[k]) * DRAG[k];
      st = Object.assign({}, st, { pose });
    }
    items.push({ kind: 'actor', st, z: (st.y - gy) * 1.5, x: st.x });
  }
  const depth = it => project(v, fx, fy, it.x, gy, it.z)[2];
  items.sort((a, b) => depth(a) - depth(b));

  const S0 = { seed: frame * 7.13, wobble: opts.wobble === undefined ? 1 : opts.wobble, t, volume: !flat };
  for (const it of items) {
    if (it.kind === 'prop') {
      ctx.save(); setM(ctx, planeMat(v, fx, fy, it.z)); NS.drawProp(ctx, R, it.p); ctx.restore();
    } else {
      const st = it.st;
      // shadow lies on the ground plane
      ctx.save(); setM(ctx, planeMat(v, fx, fy, it.z)); NS.drawShadow(ctx, st, { seed: 1 }); ctx.restore();
      // thickness: when orbiting, draw a few darker copies behind the character so it reads as a solid slab, not a sliver.
      // (traced characters build their own thickness inside drawTraced)
      const H = (st.ch && st.ch.height) || 300;
      const passes = !flat && !st.ch.parts ? [-3, -2, -1, 0] : [0];
      for (const k of passes) {
        const shift = k * 0.012 * H, base = planeMat(v, fx, fy, it.z + shift);
        ctx.save();
        setM(ctx, base);
        S0.zHook = (c, z) => { const m = c.getTransform(), n = planeMat(v, fx, fy, it.z + shift + z); c.setTransform(m.a, m.b, m.c, m.d, m.e + (n.e - base.e), m.f + (n.f - base.f)); };
        NS.drawActor(ctx, k ? Object.assign({}, st, { ch: tinted(st.ch, 1 + k * 0.1) }) : st, t, S0);
        S0.zHook = null;
        ctx.restore();
      }
      ctx.save(); setM(ctx, planeMat(v, fx, fy, it.z)); NS.drawTrail(ctx, R, st.id, t); ctx.restore();
    }
  }

  // ---- world fx stand in front of everything, drawn on the character plane
  ctx.save(); setM(ctx, planeMat(v, fx, fy, 120)); NS.drawFX(ctx, R, 'world'); ctx.restore();

  // ---- hand drawings (cels): each is shown from its start time for its duration, like a drawn frame. They live in world space on a plane
  //      just in front of the characters, so they orbit with the scene.
  const cels = (scene.drawings || []).slice().sort((a, b) => a.t - b.t);
  const active = cels.filter(d => t >= d.t - 1e-6 && t < d.t + (d.dur || 1 / 12) - 1e-6);
  const onion = opts.onion && cels.filter(d => d.t < t - 1e-6).slice(-1);
  const paint = (d, alpha) => {
    ctx.save(); setM(ctx, planeMat(v, fx, fy, 150)); ctx.globalAlpha = alpha; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
    for (const s of d.strokes || []) {
      if (!s.pts || !s.pts.length) continue;
      ctx.strokeStyle = s.c || '#111'; ctx.fillStyle = s.c || '#111'; ctx.lineWidth = s.w || 4;
      if (s.pts.length === 1) { ctx.beginPath(); ctx.arc(s.pts[0][0], s.pts[0][1], (s.w || 4) / 2, 0, 6.2832); ctx.fill(); continue; }
      ctx.beginPath(); ctx.moveTo(s.pts[0][0], s.pts[0][1]);
      for (let i = 1; i < s.pts.length - 1; i++) { const mx = (s.pts[i][0] + s.pts[i + 1][0]) / 2, my = (s.pts[i][1] + s.pts[i + 1][1]) / 2; ctx.quadraticCurveTo(s.pts[i][0], s.pts[i][1], mx, my); }
      const l = s.pts[s.pts.length - 1]; ctx.lineTo(l[0], l[1]); ctx.stroke();
    }
    ctx.restore();
  };
  if (onion) for (const d of onion) paint(d, 0.3);
  for (const d of active) paint(d, 1);
  ctx.restore();
  NS.lastFrame = { fx, fy, scale: v.scale, panX: v.panX, panY: v.panY, flat, scene: scene.id, t };

  // ---- screen-space finishing (same as the flat renderer)
  ctx.save(); ctx.setTransform(1, 0, 0, 1, 0, 0);
  if (R.pal && R.pal.tint) { ctx.globalCompositeOperation = 'multiply'; ctx.fillStyle = R.pal.tint; ctx.fillRect(0, 0, VW, VH); ctx.globalCompositeOperation = 'source-over'; }
  NS.drawFX(ctx, R, 'screen');
  if (flat && opts.bubbles !== false) NS.drawBubbles(ctx, R);
  NS.drawCaptions(ctx, R);
  if (scene.letterbox && opts.letterbox !== false) { ctx.fillStyle = '#0b0908'; ctx.fillRect(0, 0, VW, scene.letterbox); ctx.fillRect(0, VH - scene.letterbox, VW, scene.letterbox); }
  const vg = ctx.createRadialGradient(VW / 2, VH / 2, VH * 0.55, VW / 2, VH / 2, VH); vg.addColorStop(0, 'rgba(40,20,10,0)'); vg.addColorStop(1, 'rgba(40,20,10,' + (opts.vignette === undefined ? 0.16 : +opts.vignette) + ')');
  ctx.fillStyle = vg; ctx.fillRect(0, 0, VW, VH);
  const tr = scene.transition || {}, dur = NS.sceneDuration(scene), col = tr.color === 'white' ? '#fff' : '#000';
  const din = tr.in === 'fade' ? (tr.dur || 0.5) : 0, dout = tr.out === 'fade' ? (tr.dur || 0.5) : 0;
  let fade = 0; if (din && t < din) fade = Math.max(fade, 1 - t / din); if (dout && t > dur - dout) fade = Math.max(fade, (t - (dur - dout)) / dout);
  if (fade > 0) { ctx.globalAlpha = clamp(fade); ctx.fillStyle = col; ctx.fillRect(0, 0, VW, VH); }
  ctx.restore();
  return loc;
}

NS.renderOrbit = renderOrbit;
NS.projectPoint = project;
})(typeof window !== 'undefined' ? window : globalThis);
