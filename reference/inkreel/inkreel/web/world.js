/* Inkreel world: backgrounds, props, FX, speech bubbles, captions. */
(function (g) {
'use strict';
const NS = g.Inkreel;
const { VW, VH, TAU, D2R, clamp, lerp, ease, smooth, EASE, h1, vn, wob, shade, alpha, mixHex, blob, poly, line, curve, chain, smoothPath, wobblyPoly, inkStroke, strHash } = NS;

// ---------------------------------------------------------------- palettes
const PAL = {
  day:    { skyTop: '#86c5e6', skyBot: '#f7ead0', sun: '#fff2b8', far: '#8fb3c0', mid: '#5f9a6e', ground: '#e0c892', ground2: '#c9aa72', water: '#46a3b8', water2: '#8ad3d9', stone: '#b9b1a2', wall: '#e9d9b5', ink: '#2a2320', tint: null },
  dawn:   { skyTop: '#7a8fc4', skyBot: '#f9cfa0', sun: '#ffe2a8', far: '#8d9bbd', mid: '#6c8a78', ground: '#d8bd90', ground2: '#bd9d72', water: '#5a8fb0', water2: '#f0b790', stone: '#aaa395', wall: '#ddc9a6', ink: '#2a2320', tint: 'rgba(255,200,160,0.16)' },
  dusk:   { skyTop: '#4a3f7e', skyBot: '#f2985a', sun: '#ffcf76', far: '#6a5788', mid: '#4a4a66', ground: '#b88a62', ground2: '#9a6f4c', water: '#47689a', water2: '#e0885f', stone: '#8e8294', wall: '#c9a784', ink: '#241a1e', tint: 'rgba(255,150,100,0.2)' },
  night:  { skyTop: '#0a1030', skyBot: '#27396a', sun: '#eef2ff', far: '#1d2a56', mid: '#17203f', ground: '#4a5070', ground2: '#383d5a', water: '#12305a', water2: '#2a5f90', stone: '#555a78', wall: '#4a4a66', ink: '#14111c', tint: 'rgba(50,70,160,0.4)', stars: true, lit: true },
  storm:  { skyTop: '#4b5663', skyBot: '#939ea6', sun: null, far: '#69767f', mid: '#4d6258', ground: '#a69a82', ground2: '#8b8068', water: '#3d6577', water2: '#7ba0ac', stone: '#8c8f94', wall: '#a39c8c', ink: '#1f1d1f', tint: 'rgba(70,90,110,0.32)', rain: true },
  golden: { skyTop: '#f0b866', skyBot: '#fff0c4', sun: '#fffbe0', far: '#d39a5c', mid: '#8f9a58', ground: '#e4bf80', ground2: '#c99c5c', water: '#58a6a8', water2: '#f2d79a', stone: '#c7ad88', wall: '#efd49e', ink: '#2e2018', tint: 'rgba(255,190,90,0.18)' },
};
function palette(bg) {
  const base = PAL[bg.time || 'day'] || PAL.day;
  const o = Object.assign({}, base);
  if (bg.palette) for (const k of Object.keys(bg.palette)) o[k] = bg.palette[k];
  return o;
}

// ---------------------------------------------------------------- helpers
function rnd(i, k) { return h1(i * 12.9898 + (k || 0) * 78.233); }
function SB(pal, seed) { return { seed: seed || 11.1, amp: 1.4, ink: pal.ink, lw: 3 }; }

function layer(ctx, R, f, fn) { ctx.save(); ctx.translate((1 - f) * R.cam.x, (1 - f) * R.cam.y * 0.25); fn(); ctx.restore(); }

function gradRect(ctx, x0, y0, x1, y1, c0, c1) { const gr = ctx.createLinearGradient(0, y0, 0, y1); gr.addColorStop(0, c0); gr.addColorStop(1, c1); ctx.fillStyle = gr; ctx.fillRect(x0, y0, x1 - x0, y1 - y0); }

function hatch(ctx, x0, y0, x1, y1, col, al, seed, gap, ang) {
  ctx.save(); ctx.beginPath(); ctx.rect(x0, y0, x1 - x0, y1 - y0); ctx.clip();
  ctx.strokeStyle = alpha(col, al); ctx.lineWidth = 1.6; ctx.lineCap = 'round';
  const w = x1 - x0, h = y1 - y0, len = Math.hypot(w, h), dx = Math.cos(ang), dy = Math.sin(ang);
  ctx.beginPath();
  for (let d = -len; d < len; d += gap) {
    const j = (rnd(Math.floor(d / gap) + seed) - 0.5) * gap * 0.6;
    const cx = x0 + w / 2 + (-dy) * (d + j), cy = y0 + h / 2 + dx * (d + j);
    ctx.moveTo(cx - dx * len, cy - dy * len); ctx.lineTo(cx + dx * len, cy + dy * len);
  }
  ctx.stroke(); ctx.restore();
}

function stipple(ctx, x0, y0, x1, y1, col, al, n, seed, rmax) {
  ctx.fillStyle = alpha(col, al);
  for (let i = 0; i < n; i++) { const x = lerp(x0, x1, rnd(i, seed)), y = lerp(y0, y1, rnd(i, seed + 3.3)), r = 0.8 + rnd(i, seed + 9) * (rmax || 2); ctx.beginPath(); ctx.arc(x, y, r, 0, TAU); ctx.fill(); }
}

function disc(ctx, x, y, r, fill, S, rays) {
  if (rays) { ctx.strokeStyle = alpha(fill, 0.55); ctx.lineWidth = 3; ctx.lineCap = 'round'; for (let i = 0; i < 16; i++) { const a = (i / 16) * TAU; ctx.beginPath(); ctx.moveTo(x + Math.cos(a) * r * 1.25, y + Math.sin(a) * r * 1.25); ctx.lineTo(x + Math.cos(a) * r * (1.5 + 0.25 * rnd(i, 4)), y + Math.sin(a) * r * (1.5 + 0.25 * rnd(i, 4))); ctx.stroke(); } }
  blob(ctx, x, y, r, r, fill, S, { n: 12 });
}

function cloud(ctx, x, y, s, fill, S) {
  const parts = [[0, 0, 60], [-55, 12, 42], [55, 14, 46], [100, 22, 32], [-95, 24, 30]];
  ctx.save(); ctx.translate(x, y); ctx.scale(s, s);
  for (const [px, py, r] of parts) blob(ctx, px, py, r, r * 0.72, fill, S, { n: 9, stroke: false });
  for (const [px, py, r] of parts) { /* outline top only */ }
  ctx.restore();
}

function stars(ctx, R, x0, x1, y0, y1) {
  for (let i = 0; i < 90; i++) {
    const x = lerp(x0, x1, rnd(i, 1)), y = lerp(y0, y1, rnd(i, 2)), tw = 0.55 + 0.45 * Math.sin(R.t * (1 + rnd(i, 3) * 2) + i);
    ctx.fillStyle = `rgba(255,255,235,${0.5 * tw + 0.3})`; ctx.beginPath(); ctx.arc(x, y, 0.8 + rnd(i, 4) * 1.8, 0, TAU); ctx.fill();
  }
}

function flame(ctx, x, y, h, t, seed) {
  const fl = vn(t * 9 + seed) * 0.3 + 0.85, sw = (vn(t * 5 + seed * 2) - 0.5) * h * 0.25;
  const cols = ['#e2531f', '#f7a12a', '#ffe07a'];
  for (let i = 0; i < 3; i++) {
    const k = 1 - i * 0.28, hh = h * fl * k, w = h * 0.32 * k;
    ctx.fillStyle = cols[i]; ctx.beginPath();
    ctx.moveTo(x - w, y); ctx.quadraticCurveTo(x - w * 1.1, y - hh * 0.5, x + sw * k, y - hh); ctx.quadraticCurveTo(x + w * 1.1, y - hh * 0.5, x + w, y); ctx.quadraticCurveTo(x, y + w * 0.4, x - w, y); ctx.fill();
  }
}
function glow(ctx, x, y, r, col, a) { const gr = ctx.createRadialGradient(x, y, 0, x, y, r); gr.addColorStop(0, alpha(col, a)); gr.addColorStop(1, alpha(col, 0)); ctx.fillStyle = gr; ctx.fillRect(x - r, y - r, r * 2, r * 2); }

function ground(ctx, pal, gy, x0, x1, topOff, S, grass) {
  const top = gy + topOff;
  gradRect(ctx, x0, top, x1, 1400, pal.ground, pal.ground2);
  const pts = []; for (let x = x0; x <= x1; x += 90) pts.push([x, top]);
  smoothPath(ctx, pts, S.seed + 2, 4, false); inkStroke(ctx, S, 3);
  stipple(ctx, x0, top + 10, x1, 900, pal.ink, 0.22, Math.floor((x1 - x0) / 9), 5, 2);
  if (grass) for (let x = x0; x < x1; x += 46) { const gx = x + rnd(x, 1) * 30, gyy = top + 20 + rnd(x, 2) * 260; ctx.strokeStyle = alpha(grass, 0.8); ctx.lineWidth = 2.2; ctx.lineCap = 'round'; ctx.beginPath(); for (let k = -1; k <= 1; k++) { ctx.moveTo(gx + k * 5, gyy); ctx.lineTo(gx + k * 9, gyy - 14 - rnd(x, k + 5) * 10); } ctx.stroke(); }
}

// ---------------------------------------------------------------- backgrounds
const BG = {};

BG.beach = (ctx, R, pal, gy) => {
  const x0 = -1600, x1 = R.W + 1600, hz = gy - 235, S = SB(pal, 11.1);
  layer(ctx, R, 0.05, () => {
    gradRect(ctx, x0, -800, x1, hz + 4, pal.skyTop, pal.skyBot);
    if (pal.stars) stars(ctx, R, x0, x1, -300, hz - 40);
    if (pal.sun) disc(ctx, R.W * 0.72, hz - 150, 58, pal.sun, S, !pal.stars);
    hatch(ctx, x0, -300, x1, hz, '#ffffff', 0.18, 3, 34, -0.5);
  });
  layer(ctx, R, 0.12, () => { if (!pal.stars) for (let i = 0; i < 6; i++) cloud(ctx, 200 + i * 520 + (R.t * 6) % 3120 - 1560 * 0, hz - 150 - rnd(i, 1) * 90, 0.9 + rnd(i, 2) * 0.6, alpha('#ffffff', pal.stars ? 0.1 : 0.9), S); });
  layer(ctx, R, 0.25, () => {
    gradRect(ctx, x0, hz, x1, gy - 105, pal.water2, pal.water);
    for (let r = 0; r < 9; r++) {
      const y = hz + 10 + r * 13 + r * r * 0.6;
      ctx.strokeStyle = alpha('#ffffff', 0.22 + r * 0.03); ctx.lineWidth = 1.6 + r * 0.2; ctx.lineCap = 'round';
      for (let k = 0; k < 26; k++) { const x = x0 + (k * 190 + rnd(r * 31 + k, 3) * 150 + Math.sin(R.t * 0.8 + r + k) * 8); ctx.beginPath(); ctx.moveTo(x, y); ctx.quadraticCurveTo(x + 16, y - 5, x + 34 + r * 3, y); ctx.stroke(); }
    }
    ctx.fillStyle = alpha(pal.far, 0.9); const isl = [[R.W * 0.2, 150], [R.W * 0.78, 110]];
    for (const [ix, iw] of isl) { ctx.beginPath(); ctx.moveTo(ix - iw, hz + 4); ctx.quadraticCurveTo(ix - iw * 0.3, hz - 36, ix, hz - 40); ctx.quadraticCurveTo(ix + iw * 0.4, hz - 30, ix + iw, hz + 4); ctx.closePath(); ctx.fill(); }
  });
  layer(ctx, R, 1, () => {
    ground(ctx, pal, gy, x0, x1, -105, S, null);
    // foam
    const sh = Math.sin(R.t * 0.9) * 7, fy = gy - 112 + sh;
    ctx.fillStyle = alpha('#ffffff', 0.85); ctx.beginPath(); ctx.moveTo(x0, fy + 8);
    for (let x = x0; x < x1; x += 60) { const w = Math.sin(x * 0.05 + R.t * 1.5) * 3; ctx.quadraticCurveTo(x + 30, fy - 13 + w, x + 60, fy + 6 + w * 0.5); }
    ctx.lineTo(x1, fy + 20); ctx.lineTo(x0, fy + 20); ctx.closePath(); ctx.fill();
    gradRect(ctx, x0, gy - 106, x1, gy - 60, alpha(pal.water, 0.25), alpha(pal.water, 0));
  });
};

BG.forest = (ctx, R, pal, gy) => {
  const x0 = -1600, x1 = R.W + 1600, S = SB(pal, 21.3);
  layer(ctx, R, 0.05, () => { gradRect(ctx, x0, -800, x1, gy, pal.skyTop, pal.skyBot); if (pal.stars) stars(ctx, R, x0, x1, -300, 200); });
  const treeRow = (f, base, col, hmin, hmax, step, seed) => layer(ctx, R, f, () => {
    for (let x = x0; x < x1; x += step) {
      const hh = hmin + rnd(x, seed) * (hmax - hmin), w = 38 + rnd(x, seed + 1) * 20, tx = x + rnd(x, seed + 2) * step * 0.5;
      ctx.fillStyle = shade(col, -0.25); ctx.fillRect(tx - w * 0.18, base - hh, w * 0.36, hh);
      for (let k = 0; k < 4; k++) { const cx = tx + (rnd(x, k + seed) - 0.5) * 90, cy = base - hh - 20 + (rnd(x, k + 7) - 0.5) * 100; blob(ctx, cx, cy, 70 + rnd(x, k + 9) * 40, 60 + rnd(x, k + 11) * 36, col, S, { n: 9, stroke: f > 0.4, lw: 2.5 }); }
    }
  });
  treeRow(0.2, gy - 120, mixHex(pal.far, pal.skyBot, 0.35), 260, 380, 230, 3);
  treeRow(0.5, gy - 70, pal.far, 320, 460, 340, 6);
  layer(ctx, R, 0.5, () => { // light rays
    if (pal.stars) return;
    for (let i = 0; i < 5; i++) { const x = 100 + i * 330 + Math.sin(R.t * 0.3 + i) * 20; ctx.fillStyle = `rgba(255,248,200,${0.1 + 0.04 * Math.sin(R.t + i)})`; ctx.beginPath(); ctx.moveTo(x, -200); ctx.lineTo(x + 70, -200); ctx.lineTo(x + 330, gy); ctx.lineTo(x + 180, gy); ctx.closePath(); ctx.fill(); }
  });
  layer(ctx, R, 1, () => ground(ctx, pal, gy, x0, x1, -95, S, shade(pal.mid, -0.1)));
};

BG.plains = (ctx, R, pal, gy) => {
  const x0 = -1600, x1 = R.W + 1600, S = SB(pal, 31.7);
  layer(ctx, R, 0.05, () => { gradRect(ctx, x0, -800, x1, gy - 150, pal.skyTop, pal.skyBot); if (pal.stars) stars(ctx, R, x0, x1, -300, 200); if (pal.sun) disc(ctx, R.W * 0.3, gy - 380, 64, pal.sun, S, !pal.stars); });
  layer(ctx, R, 0.15, () => { if (!pal.stars) for (let i = 0; i < 5; i++) cloud(ctx, 150 + i * 470, gy - 480 + rnd(i, 3) * 80, 1.1, alpha('#ffffff', 0.85), S); });
  layer(ctx, R, 0.2, () => { ctx.fillStyle = shade(pal.far, 0); for (let x = x0; x < x1; x += 420) { const hh = 140 + rnd(x, 1) * 120; ctx.beginPath(); ctx.moveTo(x, gy - 150); ctx.lineTo(x + 200, gy - 150 - hh); ctx.lineTo(x + 420, gy - 150); ctx.closePath(); ctx.fill(); } });
  layer(ctx, R, 0.4, () => { ctx.fillStyle = pal.mid; ctx.beginPath(); ctx.moveTo(x0, gy - 90); for (let x = x0; x <= x1; x += 120) ctx.lineTo(x, gy - 130 - Math.sin(x * 0.004) * 40 - rnd(x, 2) * 24); ctx.lineTo(x1, gy - 90); ctx.closePath(); ctx.fill(); });
  layer(ctx, R, 1, () => ground(ctx, pal, gy, x0, x1, -90, S, shade(pal.mid, -0.15)));
};

BG.fortress = (ctx, R, pal, gy) => {
  const x0 = -1600, x1 = R.W + 1600, S = SB(pal, 41.9), top = gy - 520;
  layer(ctx, R, 0.05, () => { gradRect(ctx, x0, -800, x1, gy, pal.skyTop, pal.skyBot); if (pal.stars) stars(ctx, R, x0, x1, -300, top); });
  layer(ctx, R, 0.85, () => {
    ctx.fillStyle = pal.stone; ctx.fillRect(x0, top, x1 - x0, gy);
    // battlements
    for (let x = x0; x < x1; x += 120) { poly(ctx, [[x, top], [x + 70, top], [x + 70, top - 60], [x, top - 60]], pal.stone, S); }
    // bricks
    ctx.strokeStyle = alpha(pal.ink, 0.35); ctx.lineWidth = 2;
    for (let row = 0; top + row * 46 < gy; row++) {
      const y = top + row * 46; ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke();
      for (let x = x0 + (row % 2) * 55; x < x1; x += 110) { ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x, y + 46); ctx.stroke(); }
    }
    hatch(ctx, x0, top, x1, gy, pal.ink, 0.07, 9, 14, 0.7);
    // arrow slits
    for (let x = x0 + 150; x < x1; x += 420) { poly(ctx, [[x, top + 110], [x + 20, top + 110], [x + 20, top + 200], [x, top + 200]], shade(pal.ink, 0.2), S); }
    // torches
    for (let x = x0 + 300; x < x1; x += 420) {
      const fy = top + 200; glow(ctx, x + 10, fy - 30, 190, '#ffb050', 0.38 + 0.08 * Math.sin(R.t * 9 + x));
      line(ctx, [x + 10, fy], [x + 10, fy + 60], S, 8, '#4a3020'); flame(ctx, x + 10, fy, 55, R.t, x * 0.01);
    }
  });
  layer(ctx, R, 1, () => { ground(ctx, pal, gy, x0, x1, -70, S, null); ctx.strokeStyle = alpha(pal.ink, 0.28); ctx.lineWidth = 2; for (let x = x0; x < x1; x += 160) { ctx.beginPath(); ctx.moveTo(x, gy - 70); ctx.lineTo(x - 70, gy + 300); ctx.stroke(); } for (let y = gy - 20; y < gy + 300; y += 70) { ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke(); } });
};

BG.street = (ctx, R, pal, gy) => {
  const x0 = -1600, x1 = R.W + 1600, S = SB(pal, 51.3);
  layer(ctx, R, 0.05, () => { gradRect(ctx, x0, -800, x1, gy, pal.skyTop, pal.skyBot); if (pal.stars) stars(ctx, R, x0, x1, -300, 200); if (pal.sun) disc(ctx, R.W * 0.8, 150, 50, pal.sun, S, !pal.stars); });
  const row = (f, base, col, hmin, hmax, wmin, wmax, seed, wins) => layer(ctx, R, f, () => {
    let x = x0;
    while (x < x1) {
      const w = wmin + rnd(x, seed) * (wmax - wmin), h = hmin + rnd(x, seed + 1) * (hmax - hmin), c = shade(col, (rnd(x, seed + 2) - 0.5) * 0.18);
      poly(ctx, [[x, base], [x, base - h], [x + w, base - h], [x + w, base]], c, S);
      poly(ctx, [[x - 8, base - h], [x + w + 8, base - h], [x + w + 8, base - h - 18], [x - 8, base - h - 18]], shade(c, -0.18), S);
      if (wins) for (let wy = base - h + 40; wy < base - 70; wy += 70) for (let wx = x + 22; wx < x + w - 40; wx += 56) {
        const lit = pal.lit && rnd(wx, wy) > 0.45;
        poly(ctx, [[wx, wy], [wx + 30, wy], [wx + 30, wy + 42], [wx, wy + 42]], lit ? '#ffd57a' : shade(pal.far, 0.25), S, { lw: 2.2 });
      }
      x += w + 6;
    }
  });
  row(0.35, gy - 70, mixHex(pal.far, pal.skyBot, 0.3), 200, 340, 120, 200, 5, false);
  row(0.7, gy - 40, pal.mid, 260, 420, 170, 260, 8, true);
  layer(ctx, R, 1, () => {
    gradRect(ctx, x0, gy - 55, x1, gy + 20, shade(pal.stone, 0.1), pal.stone);
    gradRect(ctx, x0, gy + 20, x1, 1400, shade(pal.stone, -0.25), shade(pal.stone, -0.4));
    line(ctx, [x0, gy + 20], [x1, gy + 20], S, 4);
    ctx.strokeStyle = alpha('#f3e6a8', 0.8); ctx.lineWidth = 5; ctx.setLineDash([60, 50]); ctx.beginPath(); ctx.moveTo(x0, gy + 120); ctx.lineTo(x1, gy + 120); ctx.stroke(); ctx.setLineDash([]);
  });
};

BG.interior = (ctx, R, pal, gy) => {
  const x0 = -1600, x1 = R.W + 1600, S = SB(pal, 61.1), top = -800;
  layer(ctx, R, 1, () => {
    gradRect(ctx, x0, top, x1, gy - 60, shade(pal.wall, 0.06), pal.wall);
    hatch(ctx, x0, -200, x1, gy - 60, pal.ink, 0.05, 4, 16, 0.9);
    gradRect(ctx, x0, gy - 190, x1, gy - 60, shade(pal.wall, -0.18), shade(pal.wall, -0.26));
    line(ctx, [x0, gy - 190], [x1, gy - 190], S, 4);
    line(ctx, [x0, gy - 62], [x1, gy - 62], S, 5);
    for (let x = R.W * 0.12; x < x1; x += 640) {
      const wx = x, wy = gy - 470;
      poly(ctx, [[wx, wy], [wx + 190, wy], [wx + 190, wy + 250], [wx, wy + 250]], pal.stars ? '#1b2a55' : '#bfe4f3', S, { lw: 5 });
      line(ctx, [wx + 95, wy], [wx + 95, wy + 250], S, 4); line(ctx, [wx, wy + 125], [wx + 190, wy + 125], S, 4);
      if (!pal.stars) { ctx.fillStyle = 'rgba(255,248,210,0.16)'; ctx.beginPath(); ctx.moveTo(wx, wy + 250); ctx.lineTo(wx + 190, wy + 250); ctx.lineTo(wx + 330, gy + 150); ctx.lineTo(wx - 40, gy + 150); ctx.closePath(); ctx.fill(); }
      poly(ctx, [[wx - 22, wy - 14], [wx + 8, wy - 14], [wx + 22, wy + 260], [wx - 22, wy + 260]], mixHex(pal.wall, '#a33', 0.5), S, { lw: 3 });
      poly(ctx, [[wx + 168, wy - 14], [wx + 212, wy - 14], [wx + 212, wy + 260], [wx + 178, wy + 260]], mixHex(pal.wall, '#a33', 0.5), S, { lw: 3 });
    }
    gradRect(ctx, x0, gy - 60, x1, 1400, shade(pal.ground, -0.12), shade(pal.ground2, -0.25));
    ctx.strokeStyle = alpha(pal.ink, 0.3); ctx.lineWidth = 2;
    for (let y = gy - 20; y < gy + 360; y += 46 + (y - gy) * 0.05) { ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke(); }
    for (let x = x0; x < x1; x += 130) { ctx.beginPath(); ctx.moveTo(x, gy - 60); ctx.lineTo(x - 40, gy + 360); ctx.stroke(); }
  });
};

BG.void = (ctx, R, pal, gy) => {
  const x0 = -1600, x1 = R.W + 1600, S = SB(pal, 71.1);
  gradRect(ctx, x0, -800, x1, 1400, pal.skyBot, mixHex(pal.skyBot, pal.ground, 0.5));
  hatch(ctx, x0, gy, x1, 1400, pal.ink, 0.08, 2, 18, -0.4);
  line(ctx, [x0, gy + 6], [x1, gy + 6], S, 3);
};

function drawBackground(ctx, R) {
  const bg = R.scene.background || {}, pal = palette(bg), gy = R.scene.groundY || 570;
  R.pal = pal;
  (BG[bg.preset] || BG.beach)(ctx, R, pal, gy);
}

// ---------------------------------------------------------------- props
const PROP = {};
PROP.palm = (ctx, R, p, pal, S, s) => {
  const lean = (p.lean === undefined ? 0.18 : p.lean) * 330 * s, hh = 330 * s;
  const sway = Math.sin(R.t * 1.1 + p.x * 0.01) * 6 * s;
  const pts = [[0, 0], [lean * 0.3, -hh * 0.35], [lean * 0.7, -hh * 0.7], [lean + sway * 0.4, -hh]];
  chain(ctx, pts, [26 * s, 20 * s, 15 * s], ['#8a6038', '#7b5430', '#6d4a2a'], S);
  for (let r = 1; r < 8; r++) { const t = r / 8; line(ctx, [lean * t * 0.9 - 12 * s, -hh * t], [lean * t * 0.9 + 12 * s, -hh * t + 6 * s], S, 2, alpha(pal.ink, 0.5)); }
  const tx = lean + sway * 0.4, ty = -hh;
  for (let i = 0; i < 8; i++) {
    const a = (-170 + i * 24) * D2R + Math.sin(R.t * 1.4 + i) * 0.05, L = (130 + 26 * (i % 2)) * s, dr = 34 * s;
    const ex = tx + Math.cos(a) * L, ey = ty + Math.sin(a) * L * 0.6 + dr * Math.abs(Math.cos(a));
    const mx = tx + Math.cos(a) * L * 0.5, my = ty + Math.sin(a) * L * 0.5 - 22 * s;
    const nx = -Math.sin(a), ny = Math.cos(a), wd = 22 * s;
    ctx.beginPath(); ctx.moveTo(tx, ty); ctx.quadraticCurveTo(mx + nx * wd, my + ny * wd, ex, ey); ctx.quadraticCurveTo(mx - nx * wd * 0.7, my - ny * wd * 0.7, tx, ty); ctx.closePath();
    ctx.fillStyle = i % 2 ? '#3f8a4a' : '#4c9d54'; ctx.fill(); inkStroke(ctx, S, 2.5);
    line(ctx, [tx, ty], [mx, my + 2 * s], S, 1.8, alpha(pal.ink, 0.5));
  }
  blob(ctx, tx, ty + 8 * s, 14 * s, 14 * s, '#6a4a28', S, { n: 7 });
};
PROP.tree = (ctx, R, p, pal, S, s) => {
  const hh = 300 * s;
  poly(ctx, [[-20 * s, 0], [-12 * s, -hh * 0.6], [-8 * s, -hh], [10 * s, -hh], [14 * s, -hh * 0.6], [24 * s, 0]], '#7b5430', S);
  const sway = Math.sin(R.t * 0.9 + p.x) * 3 * s;
  for (const [cx, cy, r] of [[-60, -hh - 10, 80], [50, -hh - 20, 90], [0, -hh - 90, 85], [-20, -hh + 20, 70], [70, -hh + 20, 60]]) blob(ctx, cx * s + sway, cy * s, r * s, r * 0.82 * s, pal.mid, S, { n: 10 });
};
PROP.bush = (ctx, R, p, pal, S, s) => { for (const [cx, cy, r] of [[-36, -26, 40], [10, -34, 46], [50, -20, 34]]) blob(ctx, cx * s, cy * s, r * s, r * 0.8 * s, shade(pal.mid, -0.05), S, { n: 8 }); };
PROP.rock = (ctx, R, p, pal, S, s) => { poly(ctx, [[-70, 0], [-80, -50], [-40, -100], [20, -118], [70, -70], [86, 0]].map(q => [q[0] * s, q[1] * s]), pal.stone, S); hatch(ctx, -80 * s, -118 * s, 86 * s, 0, pal.ink, 0.12, 3, 12, 0.8); line(ctx, [-30 * s, -90 * s], [10 * s, -40 * s], S, 2, alpha(pal.ink, 0.5)); };
PROP.crate = (ctx, R, p, pal, S, s) => { const w = 90 * s; poly(ctx, [[-w / 2, 0], [-w / 2, -w], [w / 2, -w], [w / 2, 0]], '#b58a52', S); line(ctx, [-w / 2, -w], [w / 2, 0], S, 3, alpha(pal.ink, 0.6)); line(ctx, [w / 2, -w], [-w / 2, 0], S, 3, alpha(pal.ink, 0.6)); line(ctx, [-w / 2, -w / 2], [w / 2, -w / 2], S, 2, alpha(pal.ink, 0.4)); };
PROP.barrel = (ctx, R, p, pal, S, s) => { const w = 70 * s, h = 96 * s; poly(ctx, [[-w / 2, 0], [-w * 0.6, -h / 2], [-w / 2, -h], [w / 2, -h], [w * 0.6, -h / 2], [w / 2, 0]], '#9a6a3a', S); line(ctx, [-w * 0.58, -h * 0.28], [w * 0.58, -h * 0.28], S, 5, '#4a4a4a'); line(ctx, [-w * 0.58, -h * 0.72], [w * 0.58, -h * 0.72], S, 5, '#4a4a4a'); };
PROP.torch = (ctx, R, p, pal, S, s) => { line(ctx, [0, 0], [0, -150 * s], S, 9 * s, '#5a3a22'); glow(ctx, 0, -175 * s, 130 * s, '#ffb050', 0.4); flame(ctx, 0, -150 * s, 52 * s, R.t, p.x * 0.01); };
PROP.campfire = (ctx, R, p, pal, S, s) => { glow(ctx, 0, -40 * s, 200 * s, '#ff9a40', 0.45 + 0.08 * Math.sin(R.t * 10)); for (const a of [-20, 20, 0]) { ctx.save(); ctx.rotate(a * D2R); line(ctx, [-45 * s, -6], [45 * s, -6], S, 14 * s, '#6a4526'); ctx.restore(); } flame(ctx, 0, -10 * s, 90 * s, R.t, p.x * 0.01); };
PROP.hut = (ctx, R, p, pal, S, s) => { const w = 200 * s, h = 120 * s; poly(ctx, [[-w / 2, 0], [-w / 2, -h], [w / 2, -h], [w / 2, 0]], '#c9a06a', S); hatch(ctx, -w / 2, -h, w / 2, 0, pal.ink, 0.12, 5, 12, 0.5); poly(ctx, [[-w * 0.62, -h + 8], [0, -h - 120 * s], [w * 0.62, -h + 8]], '#a98a46', S); for (let i = 0; i < 6; i++) line(ctx, [-w * 0.5 + i * w * 0.18, -h + 6], [-w * 0.05 + i * w * 0.02, -h - 100 * s], S, 1.6, alpha(pal.ink, 0.4)); poly(ctx, [[-24 * s, 0], [-24 * s, -70 * s], [24 * s, -70 * s], [24 * s, 0]], shade(pal.ink, 0.25), S); };
PROP.boat = (ctx, R, p, pal, S, s) => { poly(ctx, [[-150 * s, -60 * s], [-110 * s, 0], [110 * s, 0], [160 * s, -70 * s], [0, -48 * s]], '#7a5030', S); line(ctx, [-120 * s, -42 * s], [130 * s, -50 * s], S, 3, alpha(pal.ink, 0.5)); line(ctx, [0, -48 * s], [0, -260 * s], S, 8 * s, '#5a3a22'); poly(ctx, [[6 * s, -250 * s], [6 * s, -100 * s], [110 * s, -110 * s]], '#f1e6c8', S); };
PROP.lamp = (ctx, R, p, pal, S, s) => { line(ctx, [0, 0], [0, -280 * s], S, 10 * s, '#2f3238'); poly(ctx, [[-22 * s, -280 * s], [22 * s, -280 * s], [16 * s, -320 * s], [-16 * s, -320 * s]], pal.lit ? '#ffe08a' : '#d9d2b0', S); if (pal.lit) glow(ctx, 0, -300 * s, 220 * s, '#ffd36a', 0.5); };
PROP.pillar = (ctx, R, p, pal, S, s) => { poly(ctx, [[-34 * s, 0], [-30 * s, -360 * s], [30 * s, -360 * s], [34 * s, 0]], pal.stone, S); poly(ctx, [[-46 * s, -360 * s], [46 * s, -360 * s], [46 * s, -388 * s], [-46 * s, -388 * s]], shade(pal.stone, 0.1), S); poly(ctx, [[-46 * s, 0], [46 * s, 0], [46 * s, -22 * s], [-46 * s, -22 * s]], shade(pal.stone, 0.1), S); hatch(ctx, -30 * s, -360 * s, 30 * s, 0, pal.ink, 0.12, 2, 9, 1.2); };
PROP.banner = (ctx, R, p, pal, S, s) => { line(ctx, [0, 0], [0, -330 * s], S, 8 * s, '#3a2a20'); const f = Math.sin(R.t * 2.4 + p.x) * 14 * s; poly(ctx, [[4 * s, -320 * s], [100 * s + f, -310 * s], [96 * s + f * 1.4, -200 * s], [52 * s + f, -170 * s], [4 * s, -200 * s]], p.color || '#b5402f', S); };
PROP.fence = (ctx, R, p, pal, S, s) => { for (let i = 0; i < 5; i++) poly(ctx, [[i * 50 * s - 8, 0], [i * 50 * s - 8, -80 * s], [i * 50 * s, -92 * s], [i * 50 * s + 8, -80 * s], [i * 50 * s + 8, 0]], '#a07a4a', S, { lw: 2.5 }); line(ctx, [-10 * s, -60 * s], [210 * s, -60 * s], S, 7 * s, '#8a6438'); };
PROP.sign = (ctx, R, p, pal, S, s) => { line(ctx, [0, 0], [0, -150 * s], S, 8 * s, '#6a4a2a'); poly(ctx, [[-60 * s, -150 * s], [60 * s, -150 * s], [60 * s, -105 * s], [-60 * s, -105 * s]], '#b88e58', S); };
PROP.grass = (ctx, R, p, pal, S, s) => { ctx.strokeStyle = shade(pal.mid, -0.15); ctx.lineWidth = 3 * s; ctx.lineCap = 'round'; for (let i = -6; i <= 6; i++) { const sw = Math.sin(R.t * 1.8 + i + p.x) * 3 * s; ctx.beginPath(); ctx.moveTo(i * 9 * s, 0); ctx.quadraticCurveTo(i * 9 * s + sw, -24 * s, i * 12 * s + sw * 1.5, -44 * s - rnd(i, 3) * 20 * s); ctx.stroke(); } };
PROP.monster_silhouette = (ctx, R, p, pal, S, s) => { ctx.fillStyle = alpha(pal.ink, 0.8); ctx.beginPath(); ctx.moveTo(-200 * s, 0); ctx.quadraticCurveTo(-120 * s, -240 * s, -30 * s, -200 * s); ctx.lineTo(-10 * s, -330 * s); ctx.lineTo(40 * s, -210 * s); ctx.quadraticCurveTo(160 * s, -240 * s, 230 * s, 0); ctx.closePath(); ctx.fill(); };

function drawProp(ctx, R, p) {
  const fn = PROP[p.kind]; if (!fn) return;
  const gy = R.scene.groundY || 570, s = p.scale || 1, pal = R.pal;
  ctx.save(); ctx.translate(p.x, gy + (p.y || 0)); if (p.flip) ctx.scale(-1, 1);
  const S = { seed: 5.5 + strHash(p.kind) + (p.x || 0) * 0.01, amp: 1.4, ink: pal.ink, lw: 3 };
  fn(ctx, R, p, pal, S, s);
  ctx.restore();
}

// ---------------------------------------------------------------- FX
function fxPos(R, f, now) {
  let x = f.x, y = f.y;
  if (f.at_char && R.scene.actors[f.at_char]) { const p = NS.anchorPos(R.scene, R.chars, f.at_char, f.part || 'chest', f.follow ? now : f.t, R.proj); if (p) { x = p[0]; y = p[1]; } }
  if (x === undefined) x = R.cam.x; if (y === undefined) y = R.cam.y;
  return [x + (f.ox || 0), y + (f.oy || 0)];
}
const toScreen = (R, x, y) => [(x - R.cam.x) * R.cam.zoom + VW / 2, (y - R.cam.y) * R.cam.zoom + VH / 2];

function starburst(ctx, x, y, r, spikes, fill, S, seed, inner) {
  const pts = [];
  for (let i = 0; i < spikes * 2; i++) { const a = (i / (spikes * 2)) * TAU + seed, rr = i % 2 === 0 ? r * (0.85 + 0.3 * rnd(i, seed)) : r * (inner || 0.5); pts.push([x + Math.cos(a) * rr, y + Math.sin(a) * rr]); }
  ctx.beginPath(); pts.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); ctx.closePath();
  ctx.fillStyle = fill; ctx.fill(); inkStroke(ctx, S, S.lw * 1.4);
}

const FXW = {
  impact(ctx, R, f, u, now, i) {
    const [x, y] = fxPos(R, f, now), sz = (f.size || 90) * (f.intensity || 1), S = { seed: R.frame * 3.1, amp: 2, ink: R.pal.ink, lw: 4 };
    const grow = EASE.snap(clamp(u * 3)), fade = u > 0.55 ? 1 - (u - 0.55) / 0.45 : 1;
    ctx.save(); ctx.globalAlpha = fade;
    const col = f.color || '#ffd23f', seed = i * 2.7 + Math.floor(R.t * 12) * 0.2;
    starburst(ctx, x, y, sz * (0.35 + 0.65 * grow), 10, col, S, seed, 0.46);
    starburst(ctx, x, y, sz * 0.55 * (0.35 + 0.65 * grow), 8, '#fffbe8', Object.assign({}, S, { lw: 2.5 }), seed + 0.5, 0.5);
    ctx.strokeStyle = S.ink; ctx.lineWidth = 3.5; ctx.lineCap = 'round';
    for (let k = 0; k < 8; k++) { const a = (k / 8) * TAU + seed, r0 = sz * (0.8 + 0.5 * grow), r1 = r0 + sz * 0.28 * (1 - u * 0.5); ctx.beginPath(); ctx.moveTo(x + Math.cos(a) * r0, y + Math.sin(a) * r0); ctx.lineTo(x + Math.cos(a) * r1, y + Math.sin(a) * r1); ctx.stroke(); }
    ctx.restore();
  },
  slash(ctx, R, f, u, now) {
    const [x, y] = fxPos(R, f, now), r = (f.size || 180) * (f.intensity || 1), a0 = (f.angle0 === undefined ? -70 : f.angle0) * D2R, a1 = (f.angle1 === undefined ? 70 : f.angle1) * D2R;
    const sweep = EASE.out(clamp(u * 1.8)), fade = u > 0.5 ? 1 - (u - 0.5) / 0.5 : 1, flip = f.flip ? -1 : 1;
    const N = 18, outer = [], inner = [];
    for (let i = 0; i <= N; i++) { const t = i / N, a = a0 + (a1 - a0) * t * sweep, th = Math.sin(t * Math.PI) * r * 0.16; outer.push([x + flip * Math.cos(a) * (r + th * 0.4), y + Math.sin(a) * (r + th * 0.4)]); inner.push([x + flip * Math.cos(a) * (r - th), y + Math.sin(a) * (r - th)]); }
    ctx.save(); ctx.globalAlpha = fade * 0.95; ctx.beginPath(); outer.forEach((p, i) => (i ? ctx.lineTo(p[0], p[1]) : ctx.moveTo(p[0], p[1]))); for (let i = N; i >= 0; i--) ctx.lineTo(inner[i][0], inner[i][1]); ctx.closePath();
    ctx.fillStyle = f.color || '#ffffff'; ctx.fill(); ctx.strokeStyle = alpha(R.pal.ink, 0.8); ctx.lineWidth = 2.5; ctx.stroke(); ctx.restore();
  },
  dust(ctx, R, f, u, now) {
    const [x, y] = fxPos(R, f, now), n = f.count || 7, sz = (f.size || 40) * (f.intensity || 1), col = f.color || shade(R.pal.ground, 0.25);
    ctx.save(); const S = { seed: 3.3, amp: 1.2, ink: alpha(R.pal.ink, 0.6), lw: 2.2 };
    for (let k = 0; k < n; k++) {
      const dir = (k / (n - 1) - 0.5) * 2 * (f.spread || 1), e = EASE.out(u), r = sz * (0.5 + 0.7 * rnd(k, 2)) * (0.4 + 0.9 * e);
      ctx.globalAlpha = (1 - u) * 0.9; blob(ctx, x + dir * sz * 3.4 * e, y - r * 0.4 - e * sz * (0.7 + rnd(k, 3)), r, r * 0.85, col, S, { n: 8, sd: k });
    }
    ctx.restore();
  },
  ring(ctx, R, f, u, now) {
    const [x, y] = fxPos(R, f, now), r = (f.size || 160) * (f.intensity || 1) * EASE.out(u);
    ctx.save(); ctx.globalAlpha = 1 - u; ctx.strokeStyle = f.color || '#ffffff'; ctx.lineWidth = 10 * (1 - u) + 2; ctx.beginPath(); ctx.ellipse(x, y, r, f.ground ? r * 0.28 : r, 0, 0, TAU); ctx.stroke();
    ctx.strokeStyle = alpha(R.pal.ink, 0.7); ctx.lineWidth = 2.5; ctx.beginPath(); ctx.ellipse(x, y, r * 1.04, f.ground ? r * 0.29 : r * 1.04, 0, 0, TAU); ctx.stroke(); ctx.restore();
  },
  sparks(ctx, R, f, u, now) {
    const [x, y] = fxPos(R, f, now), n = f.count || 14, sz = (f.size || 120) * (f.intensity || 1);
    ctx.save(); ctx.lineCap = 'round';
    for (let k = 0; k < n; k++) { const a = rnd(k, 1) * TAU, sp = sz * (0.5 + rnd(k, 2)), tt = EASE.out(u), px = x + Math.cos(a) * sp * tt, py = y + Math.sin(a) * sp * tt + 90 * u * u; const l = 16 * (1 - u); ctx.strokeStyle = alpha(f.color || '#ffe27a', 1 - u); ctx.lineWidth = 3.5 * (1 - u) + 0.8; ctx.beginPath(); ctx.moveTo(px, py); ctx.lineTo(px - Math.cos(a) * l, py - Math.sin(a) * l); ctx.stroke(); }
    ctx.restore();
  },
  sfx_text(ctx, R, f, u, now) {
    let [x, y] = fxPos(R, f, now); const sz = (f.size || 1) * 78 * (f.intensity || 1), txt = (f.text || 'WHAM!').toUpperCase();
    { // keep lettering fully inside the frame
      const hw = Math.min(VW / 2 - 20, sz * 0.32 * txt.length + 16), hh = sz * 0.6 + 14;
      let [sx, sy] = toScreen(R, x, y); sx = clamp(sx, hw + 12, VW - hw - 12); sy = clamp(sy, hh + 52, VH - hh - 52);
      x = (sx - VW / 2) / R.cam.zoom + R.cam.x; y = (sy - VH / 2) / R.cam.zoom + R.cam.y;
    }
    const pop = u < 0.12 ? EASE.back(u / 0.12) : 1, fade = u > 0.75 ? 1 - (u - 0.75) / 0.25 : 1, jx = (vn(R.t * 40) - 0.5) * 5 * (1 - u), jy = (vn(R.t * 40 + 9) - 0.5) * 5 * (1 - u);
    ctx.save(); ctx.translate(x + jx, y + jy); ctx.rotate((f.angle === undefined ? -8 : f.angle) * D2R); ctx.scale(pop / R.cam.zoom, pop / R.cam.zoom); ctx.globalAlpha = fade;
    ctx.font = `${sz}px Bangers, Impact, "Arial Black", sans-serif`; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.lineJoin = 'round';
    ctx.lineWidth = sz * 0.2; ctx.strokeStyle = R.pal.ink; ctx.strokeText(txt, 4, 5); ctx.strokeText(txt, 0, 0);
    ctx.fillStyle = f.color || '#ff4d2e'; ctx.fillText(txt, 0, 0); ctx.restore();
  },
};

const FXS = {
  flash(ctx, R, f, u) { ctx.save(); ctx.globalAlpha = Math.pow(1 - u, 2) * (f.intensity === undefined ? 0.9 : f.intensity); ctx.fillStyle = f.color || '#ffffff'; ctx.fillRect(0, 0, VW, VH); ctx.restore(); },
  vignette(ctx, R, f, u) {
    const env = u < 0.2 ? u / 0.2 : u > 0.8 ? (1 - u) / 0.2 : 1, a = (f.intensity === undefined ? 0.6 : f.intensity) * env;
    const gr = ctx.createRadialGradient(VW / 2, VH / 2, VH * 0.3, VW / 2, VH / 2, VH * 0.95); gr.addColorStop(0, alpha(f.color || '#000000', 0)); gr.addColorStop(1, alpha(f.color || '#000000', a)); ctx.fillStyle = gr; ctx.fillRect(0, 0, VW, VH);
  },
  tint(ctx, R, f, u) { const env = u < 0.15 ? u / 0.15 : u > 0.85 ? (1 - u) / 0.15 : 1; ctx.save(); ctx.globalAlpha = (f.intensity === undefined ? 0.35 : f.intensity) * env; ctx.fillStyle = f.color || '#ff0000'; ctx.fillRect(0, 0, VW, VH); ctx.restore(); },
  speedlines(ctx, R, f, u) {
    const n = Math.floor(34 * (f.intensity || 1)), fr = Math.floor(R.t * 14), col = f.color || R.pal.ink, env = u < 0.1 ? u / 0.1 : u > 0.85 ? (1 - u) / 0.15 : 1;
    ctx.save(); ctx.fillStyle = alpha(col, 0.72 * env);
    if (f.dir === 'left' || f.dir === 'right') {
      const sgn = f.dir === 'left' ? -1 : 1;
      for (let i = 0; i < n; i++) { const y = rnd(i + fr * 7, 1) * VH, len = 200 + rnd(i + fr, 2) * 500, x = ((rnd(i + fr * 3, 3) * (VW + 600)) + sgn * R.t * 900) % (VW + 600) - 300, th = 1.5 + rnd(i, 4) * 4; ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(x + sgn * len, y - th); ctx.lineTo(x + sgn * len, y + th); ctx.closePath(); ctx.fill(); }
    } else {
      for (let i = 0; i < n * 1.6; i++) { const a = rnd(i + fr * 5, 1) * TAU, r0 = VH * (0.38 + rnd(i + fr, 2) * 0.22), r1 = VH * (0.9 + rnd(i, 3) * 0.3), th = 0.012 + rnd(i, 4) * 0.025; ctx.beginPath(); ctx.moveTo(VW / 2 + Math.cos(a) * r0, VH / 2 + Math.sin(a) * r0); ctx.lineTo(VW / 2 + Math.cos(a - th) * r1, VH / 2 + Math.sin(a - th) * r1); ctx.lineTo(VW / 2 + Math.cos(a + th) * r1, VH / 2 + Math.sin(a + th) * r1); ctx.closePath(); ctx.fill(); }
    }
    ctx.restore();
  },
  rain(ctx, R, f, u) {
    const n = Math.floor(160 * (f.intensity || 1)), env = u < 0.1 ? u / 0.1 : u > 0.9 ? (1 - u) / 0.1 : 1;
    ctx.save(); ctx.strokeStyle = alpha(f.color || '#dff0ff', 0.5 * env); ctx.lineWidth = 1.8; ctx.lineCap = 'round'; ctx.beginPath();
    for (let i = 0; i < n; i++) { const x = (rnd(i, 1) * (VW + 300) - R.t * 380 * (0.6 + rnd(i, 3) * 0.4) * 0.35 + (R.t * 600 * (0.5 + rnd(i, 3) * 0.5)) * -0.25) % (VW + 300), y = ((rnd(i, 2) * VH + R.t * (900 + rnd(i, 3) * 500)) % (VH + 80)) - 40, l = 26 + rnd(i, 4) * 20; const xx = x < 0 ? x + VW + 300 : x; ctx.moveTo(xx - 120, y); ctx.lineTo(xx - 120 - l * 0.35, y + l); }
    ctx.stroke(); ctx.restore();
  },
};

function drawFX(ctx, R, mode) {
  const list = R.scene.fx || [];
  list.forEach((f, i) => {
    const dur = f.dur || 0.5, now = R.t;
    if (now < f.t || now > f.t + dur) return;
    const u = clamp((now - f.t) / dur);
    if (mode === 'world' && FXW[f.kind]) FXW[f.kind](ctx, R, f, u, now, i);
    if (mode === 'screen' && FXS[f.kind]) FXS[f.kind](ctx, R, f, u, now, i);
  });
  if (mode === 'screen' && (R.pal.rain || (R.scene.background || {}).weather === 'rain') && !(R.scene.fx || []).some(f => f.kind === 'rain')) FXS.rain(ctx, R, { intensity: 1 }, 0.5);
}

// ---------------------------------------------------------------- bubbles & captions
const FONT = '"Patrick Hand", "Comic Sans MS", "Chalkboard SE", "Segoe Print", sans-serif';
function wrapText(ctx, text, maxW) {
  const words = String(text).split(/\s+/), lines = []; let cur = '';
  for (const w of words) { const test = cur ? cur + ' ' + w : w; if (ctx.measureText(test).width > maxW && cur) { lines.push(cur); cur = w; } else cur = test; }
  if (cur) lines.push(cur); return lines;
}
function roundedPts(x, y, w, h, r) { return [[x + r, y], [x + w - r, y], [x + w, y + r], [x + w, y + h - r], [x + w - r, y + h], [x + r, y + h], [x, y + h - r], [x, y + r]]; }

function drawBubbles(ctx, R) {
  const placed = [];
  const S = { seed: 17.7, amp: 1.1, ink: '#1b1512', lw: 3 };
  for (const id of Object.keys(R.scene.actors)) {
    const q = NS.prep(R.scene, R.proj).actors[id];
    for (const s of q.says) {
      if (R.t < s.t || R.t > s.t + s.dur + 0.2) continue;
      const st = NS.sampleActor(R.scene, R.chars, id, R.t, R.proj), P = NS.solve(st.pose, st.ch);
      const style = s.style || 'say', shout = style === 'shout';
      const head = NS.toWorld(st, [P.hd[0], P.hd[1] - P.dims.headR * 1.5]);
      let [ax, ay] = toScreen(R, head[0], head[1]);
      ax = clamp(ax, 60, VW - 60); ay = clamp(ay, 90, VH - 20);
      const fs = shout ? 40 : style === 'whisper' ? 22 : 28, text = shout ? String(s.text).toUpperCase() : String(s.text);
      ctx.save();
      ctx.font = shout ? `${fs}px Bangers, Impact, sans-serif` : `${fs}px ${FONT}`;
      const lines = wrapText(ctx, text, shout ? 420 : 380), lh = fs * 1.2;
      const wMax = Math.max(...lines.map(l => ctx.measureText(l).width)), pad = 18;
      const bw = wMax + pad * 2, bh = lines.length * lh + pad * 1.4;
      let bx = clamp(ax - bw / 2, 24, VW - 24 - bw), by = ay - bh - 40;
      for (let k = 0; k < 6; k++) { const hit = placed.find(p => bx < p.x + p.w + 10 && bx + bw + 10 > p.x && by < p.y + p.h + 10 && by + bh + 10 > p.y); if (!hit) break; by = hit.y - bh - 14; }
      by = Math.max(18, by); placed.push({ x: bx, y: by, w: bw, h: bh });
      const fade = R.t > s.t + s.dur ? 1 - (R.t - s.t - s.dur) / 0.2 : 1, pop = R.t - s.t < 0.12 ? EASE.back((R.t - s.t) / 0.12) : 1;
      ctx.globalAlpha = fade; ctx.translate(bx + bw / 2, by + bh); ctx.scale(pop, pop); ctx.translate(-(bx + bw / 2), -(by + bh));
      const tx = clamp(ax, bx + 26, bx + bw - 26), fill = shout ? '#fff2a8' : style === 'think' ? '#f4f7ff' : '#fffdf6';
      // tail
      if (style === 'think') { for (let k = 0; k < 3; k++) blob(ctx, lerp(tx, ax, (k + 1) / 4), lerp(by + bh + 4, ay - 6, (k + 1) / 4), 9 - k * 2.2, 9 - k * 2.2, fill, S, { n: 7, lw: 2.4 }); }
      else { ctx.beginPath(); ctx.moveTo(tx - 16, by + bh - 4); ctx.lineTo(ax + (ax - tx) * 0.1, ay - 8); ctx.lineTo(tx + 16, by + bh - 4); ctx.closePath(); ctx.fillStyle = fill; ctx.fill(); inkStroke(ctx, S, 3); }
      // body
      if (shout) {
        const pts = [], cx = bx + bw / 2, cy = by + bh / 2, N = 22;
        for (let k = 0; k < N; k++) { const a = (k / N) * TAU, rr = (k % 2 ? 0.0 : 12); const ex = Math.cos(a) * (bw / 2 + 8 + rr) * 1.0, ey = Math.sin(a) * (bh / 2 + 8 + rr) * 1.0; pts.push([cx + ex, cy + ey]); }
        poly(ctx, pts, fill, S, { lw: 3.5 });
      } else if (style === 'think') blob(ctx, bx + bw / 2, by + bh / 2, bw / 2 + 6, bh / 2 + 4, fill, S, { n: 14, ja: 0.9 });
      else { smoothPath(ctx, roundedPts(bx, by, bw, bh, 16), S.seed + id.length, 1.1, true); ctx.fillStyle = fill; ctx.fill(); if (style === 'whisper') ctx.setLineDash([7, 6]); inkStroke(ctx, S, 3); ctx.setLineDash([]); }
      // text typewriter
      const total = text.length, shown = Math.floor(total * clamp((R.t - s.t) / (s.dur * 0.72)));
      ctx.fillStyle = '#1b1512'; ctx.textAlign = 'left'; ctx.textBaseline = 'top';
      let left = shown, yy = by + pad * 0.7;
      for (const l of lines) { const part = l.slice(0, Math.max(0, left)); ctx.fillText(part, bx + pad, yy); left -= l.length + 1; yy += lh; }
      ctx.restore();
    }
  }
}

function drawCaptions(ctx, R) {
  for (const c of R.scene.captions || []) {
    if (R.t < c.t || R.t > c.t + c.dur) continue;
    const u = (R.t - c.t) / c.dur, env = clamp(Math.min(u / 0.1, (1 - u) / 0.12, 1)), style = c.style || 'narration';
    ctx.save(); ctx.globalAlpha = env; ctx.textBaseline = 'middle';
    if (style === 'title') {
      ctx.textAlign = 'center'; ctx.font = `96px Bangers, Impact, sans-serif`; ctx.lineJoin = 'round'; ctx.lineWidth = 14; ctx.strokeStyle = '#1b1512'; const sc = 0.94 + 0.06 * EASE.out(clamp(u * 4));
      ctx.translate(VW / 2, VH / 2); ctx.scale(sc, sc);
      const lines = wrapText(ctx, c.text.toUpperCase(), 1000); lines.forEach((l, i) => { const y = (i - (lines.length - 1) / 2) * 104; ctx.strokeText(l, 0, y); ctx.fillStyle = c.color || '#fff4d6'; ctx.fillText(l, 0, y); });
    } else if (style === 'location') {
      ctx.font = `30px ${FONT}`; const w = ctx.measureText(c.text).width + 40, S = { seed: 8.8, amp: 1, ink: '#1b1512', lw: 3 }, shown = Math.floor(c.text.length * clamp(u / 0.3));
      smoothPath(ctx, roundedPts(36, 36, w, 52, 10), 3, 1, true); ctx.fillStyle = '#f7e7b0'; ctx.fill(); inkStroke(ctx, S, 3);
      ctx.fillStyle = '#1b1512'; ctx.textAlign = 'left'; ctx.fillText(c.text.slice(0, shown), 56, 63);
    } else {
      ctx.font = `30px ${FONT}`; const lines = wrapText(ctx, c.text, 940), lh = 38, bw = Math.max(...lines.map(l => ctx.measureText(l).width)) + 50, bh = lines.length * lh + 26, bx = (VW - bw) / 2, by = VH - bh - 46 - (R.scene.letterbox || 0);
      const S = { seed: 4.4, amp: 1, ink: '#1b1512', lw: 3 };
      smoothPath(ctx, roundedPts(bx, by, bw, bh, 12), 5, 1, true); ctx.fillStyle = '#f4ead0'; ctx.fill(); inkStroke(ctx, S, 3);
      ctx.fillStyle = '#1b1512'; ctx.textAlign = 'center'; lines.forEach((l, i) => ctx.fillText(l, VW / 2, by + 13 + lh / 2 + i * lh));
    }
    ctx.restore();
  }
}

Object.assign(NS, { PALETTES: PAL, palette, drawBackground, drawProp, drawFX, drawBubbles, drawCaptions, PROP_KINDS: Object.keys(PROP), BG_PRESETS: Object.keys(BG), FX_KINDS: Object.keys(FXW).concat(Object.keys(FXS)) });
})(typeof window !== 'undefined' ? window : globalThis);
