/* Inkreel draw: hand-drawn line primitives, character renderer, weapons, trails. */
(function (g) {
'use strict';
const NS = g.Inkreel;
const { clamp, lerp, wob, shade, alpha, mixHex, solve, dirv, D2R, TAU, strHash, vn } = NS;

// ---------------------------------------------------------------- primitives
function sub(a, b, n) { const o = []; for (let i = 0; i <= n; i++) o.push([lerp(a[0], b[0], i / n), lerp(a[1], b[1], i / n)]); return o; }

function smoothPath(ctx, pts, seed, amp, close) {
  const p = pts.map((q, i) => [q[0] + wob(seed, i * 2) * amp, q[1] + wob(seed, i * 2 + 1) * amp]);
  ctx.beginPath();
  if (close) {
    const n = p.length;
    ctx.moveTo((p[n - 1][0] + p[0][0]) / 2, (p[n - 1][1] + p[0][1]) / 2);
    for (let i = 0; i < n; i++) { const a = p[i], b = p[(i + 1) % n]; ctx.quadraticCurveTo(a[0], a[1], (a[0] + b[0]) / 2, (a[1] + b[1]) / 2); }
    ctx.closePath();
  } else {
    ctx.moveTo(p[0][0], p[0][1]);
    for (let i = 1; i < p.length - 1; i++) { const a = p[i], b = p[i + 1]; ctx.quadraticCurveTo(a[0], a[1], (a[0] + b[0]) / 2, (a[1] + b[1]) / 2); }
    ctx.lineTo(p[p.length - 1][0], p[p.length - 1][1]);
  }
}

// straight-edged polygon with wobbly edges (for buildings, bricks, blades)
function wobblyPoly(ctx, pts, seed, amp) {
  ctx.beginPath();
  let k = 0, first = true;
  for (let i = 0; i < pts.length; i++) {
    const a = pts[i], b = pts[(i + 1) % pts.length];
    const n = Math.max(1, Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]) / 55));
    for (let j = 0; j < n; j++) {
      const x = lerp(a[0], b[0], j / n) + wob(seed, k * 2) * amp, y = lerp(a[1], b[1], j / n) + wob(seed, k * 2 + 1) * amp; k++;
      if (first) { ctx.moveTo(x, y); first = false; } else ctx.lineTo(x, y);
    }
  }
  ctx.closePath();
}

function inkStroke(ctx, S, w, col) {
  const lw = w || S.lw; ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  ctx.lineWidth = lw; ctx.strokeStyle = col || S.ink; ctx.stroke();
  if (S.sketch !== false && !col && lw > 1.6) { // second, thinner pencil pass slightly off the first: hand-inked double line
    ctx.save(); ctx.translate(wob(S.seed, 91) * lw * 0.5, wob(S.seed, 92) * lw * 0.5);
    ctx.globalAlpha = 0.45; ctx.lineWidth = lw * 0.38; ctx.stroke(); ctx.restore();
  }
}
function fillOff(ctx, S) { const m = (S.amp || 1) * 1.5; ctx.translate(wob(S.seed, 77) * m + m * 0.6, wob(S.seed, 78) * m + m * 0.6); }

function poly(ctx, pts, fill, S, o) {
  o = o || {};
  wobblyPoly(ctx, pts, S.seed, S.amp);
  if (fill) { ctx.save(); fillOff(ctx, S); ctx.fillStyle = fill; ctx.fill(); ctx.restore(); }
  if (o.stroke !== false) inkStroke(ctx, S, o.lw);
}
function blob(ctx, cx, cy, rx, ry, fill, S, o) {
  o = o || {};
  const n = o.n || 11, pts = [];
  for (let i = 0; i < n; i++) { const a = (i / n) * TAU; pts.push([cx + Math.cos(a) * rx, cy + Math.sin(a) * ry]); }
  smoothPath(ctx, pts, S.seed + (o.sd || 0), S.amp * (o.ja || 1), true);
  if (fill) { ctx.save(); fillOff(ctx, S); ctx.fillStyle = fill; ctx.fill(); ctx.restore(); }
  if (o.stroke !== false) inkStroke(ctx, S, o.lw);
}
function line(ctx, a, b, S, w, col) {
  const n = Math.max(2, Math.round(Math.hypot(b[0] - a[0], b[1] - a[1]) / 40));
  smoothPath(ctx, sub(a, b, n), S.seed, S.amp, false);
  inkStroke(ctx, S, w, col);
}
function curve(ctx, pts, S, w, col, amp) { smoothPath(ctx, pts, S.seed, amp === undefined ? S.amp * 0.5 : amp, false); inkStroke(ctx, S, w, col); }

// limb chain: outlines first so joints don't show seams, then fills
function chain(ctx, pts, widths, fills, S) {
  const segs = [];
  for (let i = 0; i < pts.length - 1; i++) segs.push(sub(pts[i], pts[i + 1], 2));
  ctx.lineCap = 'round'; ctx.lineJoin = 'round';
  for (let i = 0; i < segs.length; i++) { smoothPath(ctx, segs[i], S.seed + i * 5, S.amp * 0.6, false); ctx.lineWidth = widths[i] + S.lw * 2; ctx.strokeStyle = S.ink; ctx.stroke(); }
  for (let i = 0; i < segs.length; i++) { smoothPath(ctx, segs[i], S.seed + i * 5, S.amp * 0.6, false); ctx.lineWidth = widths[i]; ctx.strokeStyle = fills[i]; ctx.stroke(); }
}

// ---------------------------------------------------------------- character
function drawShadow(ctx, st, S) {
  const ch = st.ch, H = ch.height || 300, pose = st.pose;
  const P = solve(pose, ch);
  const lying = Math.abs(pose.rot) > 45;
  const air = clamp(-pose.ry * 1.3, 0, 0.7);
  const w = (lying ? 0.62 : 0.34) * H * (1 - air * 0.6);
  const cx = st.x + st.facing * (lying ? (P.hip[0] + P.hd[0]) / 2 : (P.anF[0] + P.anB[0]) / 2 * 0.8);
  ctx.save();
  ctx.fillStyle = alpha(S.shadow || '#1a1210', 0.22 * (1 - air * 0.5));
  ctx.beginPath(); ctx.ellipse(cx, st.y + 4, w / 2, H * 0.028 * (1 - air * 0.3), 0, 0, TAU); ctx.fill();
  ctx.restore();
}

function drawActor(ctx, st, t, S0) {
  if (st.ch.parts && NS.drawTraced) return NS.drawTraced(ctx, st, t, S0);   // character traced from a picture
  const ch = st.ch, P = solve(st.pose, ch), d = P.dims, H = d.H, b = d.b;
  const ink = ch.ink || '#1b1512';
  const S = { seed: S0.seed + strHash(st.id) * 3.31, amp: H * 0.0042 * (S0.wobble === undefined ? 1 : S0.wobble), ink, lw: Math.max(2.4, H * 0.0125) };
  const skin = ch.skin || '#8a5a3b', top = ch.top || '#c8553d', bottom = ch.bottom || '#2f3a4f', accent = ch.accent || '#e2b04a', hair = ch.hair || '#1b1210';
  const outfit = ch.outfit || 'tee', legs = ch.legs || 'pants';
  const bootCol = ch.barefoot ? skin : (ch.boots || accent);
  const upC = outfit === 'tank' || outfit === 'bare' ? skin : top, foreC = outfit === 'long' ? top : skin;
  const thC = bottom, shC = legs === 'shorts' ? skin : bottom;
  const wUp = 0.05 * H * b, wFo = 0.042 * H * b, wTh = 0.078 * H * b, wSh = 0.06 * H * b, wFt = 0.05 * H;

  ctx.save();
  ctx.translate(st.x, st.y);
  ctx.scale(st.facing, 1);
  // depth layers for the orbit view: S0.zHook(ctx, z) re-projects the following strokes at depth z (px along the character's facing-normal)
  const Z = z => { if (S0.zHook) S0.zHook(ctx, z); };
  Z(-0.09 * H);
  // back leg, back arm
  chain(ctx, [P.hip, P.knB, P.anB, P.toB], [wTh, wSh, wFt], [shade(thC, -0.14), shade(shC, -0.14), shade(bootCol, -0.14)], S);
  chain(ctx, [P.sh, P.elB, P.hnB], [wUp, wFo], [shade(upC, -0.14), shade(foreC, -0.14)], S);
  blob(ctx, P.hnB[0], P.hnB[1], 0.032 * H, 0.032 * H, shade(skin, -0.14), S, { n: 8 });

  // hair behind head
  const r = d.headR;
  ctx.save();
  ctx.translate(P.hd[0], P.hd[1]); ctx.rotate(P.headAngle * D2R);
  const hs = ch.hair_style || 'short';
  const sway = Math.sin(S0.t * 2.6 + strHash(st.id)) * 0.12 + Math.max(-0.5, Math.min(0.5, -st.speed * 0.0025));
  if (hs === 'afro') blob(ctx, -0.18 * r, -0.28 * r, 1.6 * r, 1.5 * r, hair, S, { n: 13, ja: 1.6 });
  if (hs === 'locs' || hs === 'braids') {
    const thin = hs === 'braids', cnt = thin ? 8 : 6;
    for (let i = 0; i < cnt; i++) {
      const a = (200 + i * (150 / cnt)) * D2R, sx = Math.cos(a) * r * 0.95, sy = Math.sin(a) * r * 1.0;
      const len = r * (thin ? 2.6 : 2.0) * (0.85 + 0.3 * wob(i * 3.3, 1) * 0.5);
      const ex = sx - r * (0.4 + 0.12 * i / cnt) + sway * r * 1.5, ey = sy + len;
      const mid = [(sx + ex) / 2 - r * 0.2, (sy + ey) / 2];
      chain(ctx, [[sx, sy], mid, [ex, ey]], [r * (thin ? 0.24 : 0.34), r * (thin ? 0.2 : 0.3)], [hair, hair], S);
      if (thin) blob(ctx, ex, ey, r * 0.12, r * 0.12, accent, S, { n: 6, lw: S.lw * 0.6 });
    }
  }
  ctx.restore();

  // torso
  Z(0);
  {
    const a = P.torsoAngle * D2R, u = [Math.sin(a), -Math.cos(a)], n = [Math.cos(a), Math.sin(a)];
    const ws = 0.12 * H * b, wm = 0.115 * H * b, wh = 0.1 * H * b;
    const sh = P.sh, hp = P.hip, md = [(sh[0] + hp[0]) / 2, (sh[1] + hp[1]) / 2];
    const pts = [
      [sh[0] + n[0] * ws / 2 + u[0] * ws * 0.25, sh[1] + n[1] * ws / 2 + u[1] * ws * 0.25],
      [sh[0] + n[0] * ws / 2, sh[1] + n[1] * ws / 2],
      [md[0] + n[0] * wm / 2, md[1] + n[1] * wm / 2],
      [hp[0] + n[0] * wh / 2, hp[1] + n[1] * wh / 2],
      [hp[0] - n[0] * wh / 2 - u[0] * 0.02 * H, hp[1] - n[1] * wh / 2 - u[1] * 0.02 * H],
      [md[0] - n[0] * wm / 2, md[1] - n[1] * wm / 2],
      [sh[0] - n[0] * ws / 2, sh[1] - n[1] * ws / 2],
      [sh[0] - n[0] * ws / 2 + u[0] * ws * 0.25, sh[1] - n[1] * ws / 2 + u[1] * ws * 0.25],
    ];
    // neck first
    chain(ctx, [sh, [sh[0] + u[0] * d.neck * 1.8, sh[1] + u[1] * d.neck * 1.8]], [0.05 * H], [shade(skin, -0.06)], S);
    smoothPath(ctx, pts, S.seed + 9, S.amp, true);
    ctx.fillStyle = outfit === 'bare' ? skin : top; ctx.fill(); inkStroke(ctx, S);
    // hem / belt
    const bl = [hp[0] + n[0] * wh / 2 - u[0] * 0.01 * H, hp[1] + n[1] * wh / 2 - u[1] * 0.01 * H], br = [hp[0] - n[0] * wh / 2, hp[1] - n[1] * wh / 2];
    line(ctx, bl, br, S, S.lw * 1.6, accent);
    // pelvis
    blob(ctx, hp[0], hp[1] + 0.012 * H, 0.062 * H * b, 0.05 * H, bottom, S, { n: 9, sd: 3 });
    line(ctx, [hp[0] + n[0] * wh / 2, hp[1] - u[1] * 0.0], [hp[0] - n[0] * wh / 2, hp[1]], S, S.lw * 1.3, accent);
    if (ch.scarf) {
      const nk = [sh[0] + u[0] * d.neck * 1.2, sh[1] + u[1] * d.neck * 1.2];
      const tail = [nk, [nk[0] - 0.08 * H + sway * 0.1 * H, nk[1] + 0.03 * H], [nk[0] - 0.17 * H + sway * 0.14 * H, nk[1] + 0.07 * H + Math.sin(S0.t * 5) * 0.01 * H]];
      chain(ctx, tail, [0.04 * H, 0.03 * H], [accent, accent], S);
      blob(ctx, nk[0], nk[1], 0.05 * H, 0.03 * H, accent, S, { n: 8 });
    }
  }

  // front leg
  Z(0.05 * H);
  chain(ctx, [P.hip, P.knF, P.anF, P.toF], [wTh, wSh, wFt], [thC, shC, bootCol], S);

  // head
  Z(0.025 * H);
  ctx.save();
  ctx.translate(P.hd[0], P.hd[1]); ctx.rotate(P.headAngle * D2R);
  blob(ctx, 0, 0, r, r * 1.05, skin, S, { n: 12, sd: 1 });
  blob(ctx, -0.12 * r, 0.08 * r, 0.2 * r, 0.26 * r, shade(skin, -0.08), S, { n: 7, lw: S.lw * 0.6, sd: 2 });
  // hair front
  const hairCap = () => {
    const pts = [];
    for (let a = 175; a <= 345; a += 17) { const rr = a < 200 ? 1.02 : 1.09; pts.push([Math.cos(a * D2R) * r * rr, Math.sin(a * D2R) * r * 1.12 * rr * 0.97]); }
    pts.push([0.9 * r, -0.36 * r], [0.35 * r, -0.54 * r], [-0.35 * r, -0.4 * r], [-0.85 * r, -0.05 * r]);
    smoothPath(ctx, pts, S.seed + 4, S.amp * 0.7, true);
    ctx.fillStyle = hair; ctx.fill(); inkStroke(ctx, S, S.lw * 0.9);
  };
  if (hs === 'short' || hs === 'locs' || hs === 'braids' || hs === 'afro') hairCap();
  if (hs === 'bun') { hairCap(); blob(ctx, -0.45 * r, -1.2 * r, 0.5 * r, 0.5 * r, hair, S, { n: 8 }); }
  if (hs === 'mohawk') { const pts = []; for (let i = 0; i <= 6; i++) { const a = (200 + i * 22) * D2R; pts.push([Math.cos(a) * r * 1.0, Math.sin(a) * r * 1.05]); } for (let i = 6; i >= 0; i--) { const a = (200 + i * 22) * D2R; pts.push([Math.cos(a) * r * 1.5, Math.sin(a) * r * 1.6]); } poly(ctx, pts, hair, S); }
  if (ch.headband) { line(ctx, [-0.98 * r, -0.28 * r], [0.96 * r, -0.5 * r], S, r * 0.22, accent); chain(ctx, [[-0.98 * r, -0.28 * r], [-1.5 * r, -0.05 * r + sway * r], [-2.1 * r, 0.25 * r + sway * r * 1.5]], [r * 0.16, r * 0.12], [accent, accent], S); }

  // face
  const e = (NS.getLibrary().emotions || {})[st.emotion] || { brow: 0, browY: 0, eye: 1, mouth: 'flat' };
  const eyeOpen = st.blink ? 0.08 : e.eye;
  const ex = [0.3 * r, 0.74 * r], ey = -0.1 * r;
  const fw = Math.max(1.6, r * 0.085);
  for (let i = 0; i < 2; i++) {
    const x = ex[i];
    if (e.mouth === 'grit' || eyeOpen < 0.15) {
      if (e.mouth === 'grit') { const s = i === 0 ? 1 : -1; curve(ctx, [[x - s * 0.1 * r, ey - 0.1 * r], [x + s * 0.08 * r, ey], [x - s * 0.1 * r, ey + 0.1 * r]], S, fw * 1.2, ink, 0); }
      else line(ctx, [x - 0.12 * r, ey], [x + 0.12 * r, ey], S, fw, ink);
    } else {
      blob(ctx, x, ey, 0.14 * r, 0.2 * r * Math.min(eyeOpen, 1.4), '#fffdf6', S, { n: 8, lw: fw * 0.8, ja: 0.3 });
      blob(ctx, x + 0.045 * r, ey + 0.01 * r, 0.075 * r, 0.1 * r * Math.min(1.2, eyeOpen + 0.1), ink, S, { n: 6, stroke: false, ja: 0.1 });
    }
    const outer = i === 0 ? -1 : 1, by = ey - 0.3 * r - e.browY * r;
    const yOut = by - 0.075 * r * e.brow, yIn = by + 0.075 * r * e.brow;
    line(ctx, [x + outer * 0.17 * r, yOut], [x - outer * 0.17 * r, yIn], S, fw * 1.15, hs === 'bald' ? shade(skin, -0.45) : (ch.brow || hair));
  }
  // nose
  curve(ctx, [[0.98 * r, -0.05 * r], [1.1 * r, 0.14 * r], [0.95 * r, 0.22 * r]], S, fw * 0.9, shade(skin, -0.45), 0);
  // mouth
  const mx = 0.58 * r, my = 0.52 * r;
  const talk = st.mouth;
  const dark = '#4a1518';
  if (talk > 0.08 && e.mouth !== 'laugh' && e.mouth !== 'shout') {
    blob(ctx, mx, my, 0.17 * r, (0.05 + 0.2 * talk) * r, dark, S, { n: 8, lw: fw * 0.9, ja: 0.2 });
  } else {
    switch (e.mouth) {
      case 'smile': curve(ctx, [[0.25 * r, 0.44 * r], [0.55 * r, 0.76 * r], [0.9 * r, 0.42 * r]], S, fw, ink, 0); break;
      case 'smirk': curve(ctx, [[0.28 * r, 0.56 * r], [0.6 * r, 0.6 * r], [0.9 * r, 0.36 * r]], S, fw, ink, 0); break;
      case 'frown': curve(ctx, [[0.28 * r, 0.62 * r], [0.58 * r, 0.4 * r], [0.88 * r, 0.62 * r]], S, fw, ink, 0); break;
      case 'o': blob(ctx, mx, my + 0.05 * r, 0.11 * r, 0.16 * r, dark, S, { n: 8, lw: fw * 0.8, ja: 0.2 }); break;
      case 'grit': poly(ctx, [[0.25 * r, 0.4 * r], [0.9 * r, 0.4 * r], [0.9 * r, 0.64 * r], [0.25 * r, 0.64 * r]], '#fffdf6', S, { lw: fw * 0.8 }); line(ctx, [0.45 * r, 0.4 * r], [0.45 * r, 0.64 * r], S, fw * 0.6); line(ctx, [0.65 * r, 0.4 * r], [0.65 * r, 0.64 * r], S, fw * 0.6); break;
      case 'laugh': { const o = 0.1 + 0.12 * Math.abs(Math.sin(S0.t * 14)); poly(ctx, [[0.22 * r, 0.38 * r], [0.95 * r, 0.38 * r], [0.82 * r, (0.62 + o) * r], [0.35 * r, (0.62 + o) * r]], dark, S, { lw: fw * 0.9 }); break; }
      case 'shout': { const o = 0.12 + 0.1 * Math.abs(Math.sin(S0.t * 20)); blob(ctx, mx, 0.55 * r, 0.3 * r, (0.2 + o) * r, dark, S, { n: 9, lw: fw, ja: 0.3 }); break; }
      case 'wobble': curve(ctx, [[0.26 * r, 0.56 * r], [0.4 * r, 0.64 * r], [0.54 * r, 0.52 * r], [0.7 * r, 0.64 * r], [0.88 * r, 0.54 * r]], S, fw, ink, 0); break;
      default: line(ctx, [0.32 * r, 0.54 * r], [0.84 * r, 0.54 * r], S, fw, ink);
    }
  }
  if (ch.beard) poly(ctx, [[0.05 * r, 0.5 * r], [0.95 * r, 0.3 * r], [1.0 * r, 0.75 * r], [0.7 * r, 1.12 * r], [0.15 * r, 1.0 * r]], hair, S, { lw: S.lw * 0.8 });
  if (ch.glasses) { blob(ctx, ex[0], ey, 0.2 * r, 0.22 * r, null, S, { n: 8, lw: fw * 0.8, ja: 0.2 }); blob(ctx, ex[1], ey, 0.2 * r, 0.22 * r, null, S, { n: 8, lw: fw * 0.8, ja: 0.2 }); }
  if (ch.scar) line(ctx, [0.55 * r, -0.55 * r], [0.85 * r, 0.3 * r], S, fw * 0.8, '#7a2c2c');
  ctx.restore();

  // front arm, weapon, hand
  Z(0.09 * H);
  chain(ctx, [P.sh, P.elF, P.hnF], [wUp, wFo], [upC, foreC], S);
  drawWeapon(ctx, ch, P, S, H);
  blob(ctx, P.hnF[0], P.hnF[1], 0.034 * H, 0.034 * H, skin, S, { n: 8 });

  ctx.restore();
}

// ---------------------------------------------------------------- weapons
function bladePoly(base, tip, w0, w1, curve) {
  const dx = tip[0] - base[0], dy = tip[1] - base[1], L = Math.hypot(dx, dy) || 1, nx = -dy / L, ny = dx / L;
  const pts = [], N = 5;
  for (let i = 0; i <= N; i++) { const t = i / N, c = Math.sin(t * Math.PI) * curve; pts.push([base[0] + dx * t + nx * (w0 / 2 * (1 - t) + w1 / 2 * t + c), base[1] + dy * t + ny * (w0 / 2 * (1 - t) + w1 / 2 * t + c)]); }
  for (let i = N; i >= 0; i--) { const t = i / N, c = Math.sin(t * Math.PI) * curve; pts.push([base[0] + dx * t - nx * (w0 / 2 * (1 - t) + w1 / 2 * t - c), base[1] + dy * t - ny * (w0 / 2 * (1 - t) + w1 / 2 * t - c)]); }
  return pts;
}

function drawWeapon(ctx, ch, P, S, H) {
  const kind = ch.weapon || 'none';
  if (kind === 'none') return;
  const a = P.wBase, b = P.wTip, hand = P.hnF;
  const dv = [b[0] - a[0], b[1] - a[1]], L = Math.hypot(dv[0], dv[1]) || 1, u = [dv[0] / L, dv[1] / L], n = [-u[1], u[0]];
  const steel = ch.weaponColor || '#d4dbe0', wood = ch.weaponColor || '#8a5a2b';
  const at = (p, k) => [p[0] + u[0] * k, p[1] + u[1] * k];
  if (kind === 'sword' || kind === 'katana' || kind === 'dagger') {
    const guard = at(hand, 0.02 * H), curveAmt = kind === 'katana' ? -0.018 * H : 0;
    line(ctx, at(hand, -0.07 * H), at(hand, 0.02 * H), S, 0.03 * H, '#3a2a22');
    poly(ctx, bladePoly(guard, b, 0.05 * H, 0.016 * H, curveAmt), steel, S);
    line(ctx, [guard[0] + n[0] * 0.04 * H, guard[1] + n[1] * 0.04 * H], [guard[0] - n[0] * 0.04 * H, guard[1] - n[1] * 0.04 * H], S, 0.016 * H, ch.accent || '#e2b04a');
    line(ctx, at(guard, 0.06 * H), at(b, -0.05 * H), S, S.lw * 0.5, '#ffffff');
  } else if (kind === 'greatblade') {
    const guard = at(hand, 0.025 * H);
    line(ctx, at(hand, -0.09 * H), at(hand, 0.025 * H), S, 0.034 * H, '#3a2a22');
    const pts = bladePoly(guard, at(b, -0.05 * H), 0.075 * H, 0.085 * H, 0.0);
    poly(ctx, pts, ch.weaponColor || '#efe7d2', S);
    blob(ctx, b[0] - u[0] * 0.05 * H, b[1] - u[1] * 0.05 * H, 0.043 * H, 0.043 * H, ch.weaponColor || '#efe7d2', S, { n: 9, ja: 0.4 });
    line(ctx, at(guard, 0.05 * H), at(b, -0.08 * H), S, 0.016 * H, ch.accent || '#2d8f85');
    line(ctx, [guard[0] + n[0] * 0.05 * H, guard[1] + n[1] * 0.05 * H], [guard[0] - n[0] * 0.05 * H, guard[1] - n[1] * 0.05 * H], S, 0.018 * H, '#3a2a22');
  } else if (kind === 'staff') {
    line(ctx, a, b, S, 0.03 * H, wood);
    blob(ctx, a[0], a[1], 0.022 * H, 0.022 * H, '#555', S, { n: 6, lw: S.lw * 0.7 }); blob(ctx, b[0], b[1], 0.024 * H, 0.024 * H, '#555', S, { n: 6, lw: S.lw * 0.7 });
  } else if (kind === 'spear') {
    line(ctx, a, at(b, -0.1 * H), S, 0.026 * H, wood);
    poly(ctx, bladePoly(at(b, -0.14 * H), b, 0.06 * H, 0.004 * H, 0.0), steel, S);
  } else if (kind === 'club') {
    poly(ctx, bladePoly(at(hand, -0.04 * H), b, 0.03 * H, 0.085 * H, 0), wood, S);
  }
}

// ---------------------------------------------------------------- motion trails
function drawTrail(ctx, R, id, t) {
  const { scene, chars, proj } = R;
  const P = NS.prep(scene, proj).actors[id];
  let act = null;
  for (const a of P.actions) if (a.trail && t >= a.t && t <= a.t + a.dur + 0.04) act = a;
  if (!act) return;
  const ch = chars[id] || {}, H = ch.height || 300;
  const N = 9, dt = 0.013;
  const pts = [];
  for (let i = 0; i < N; i++) {
    const tt = Math.max(act.t, t - i * dt);
    const st = NS.sampleActor(scene, chars, id, tt, proj), S2 = solve(st.pose, ch);
    if (act.trail === 'weapon' && ch.weapon && ch.weapon !== 'none') pts.push([NS.toWorld(st, [lerp(S2.wBase[0], S2.wTip[0], 0.6), lerp(S2.wBase[1], S2.wTip[1], 0.6)]), NS.toWorld(st, S2.wTip)]);
    else if (act.trail === 'foot') pts.push([NS.toWorld(st, S2.anF), NS.toWorld(st, S2.toF)]);
    else if (act.trail === 'weapon') pts.push([NS.toWorld(st, S2.hnF), NS.toWorld(st, S2.hnF)]);
    else pts.push([NS.toWorld(st, S2.hnF), NS.toWorld(st, S2.hnF)]);
  }
  const speed = Math.hypot(pts[0][1][0] - pts[1][1][0], pts[0][1][1] - pts[1][1][1]) / (0.05 * H);
  const sf = clamp(speed, 0, 1);
  if (sf < 0.12) return;
  ctx.save();
  const col = R.trailColor || '#ffffff';
  for (let i = 0; i < N - 1; i++) {
    const a = (1 - i / N), al = a * a * 0.42 * sf;
    const [b0, t0] = pts[i], [b1, t1] = pts[i + 1];
    if (act.trail === 'weapon' && ch.weapon && ch.weapon !== 'none') {
      ctx.fillStyle = alpha(col, al);
      ctx.beginPath(); ctx.moveTo(b0[0], b0[1]); ctx.lineTo(t0[0], t0[1]); ctx.lineTo(t1[0], t1[1]); ctx.lineTo(b1[0], b1[1]); ctx.closePath(); ctx.fill();
    } else {
      ctx.strokeStyle = alpha(col, al); ctx.lineCap = 'round';
      ctx.lineWidth = H * 0.06 * a * (act.trail === 'foot' ? 1.1 : 0.9);
      ctx.beginPath(); ctx.moveTo(t0[0], t0[1]); ctx.lineTo(t1[0], t1[1]); ctx.stroke();
    }
  }
  ctx.restore();
}

Object.assign(NS, { sub, smoothPath, wobblyPoly, inkStroke, poly, blob, line, curve, chain, drawShadow, drawActor, drawTrail, bladePoly });
})(typeof window !== 'undefined' ? window : globalThis);
