/* Inkreel traced characters: vector parts cut from a picture (see server/inkreel/trace.py), moved by the same skeleton as every other character.
   Each part belongs to a bone; its shapes are stored relative to the bone's joint in the picture's rest pose. At draw time the part is placed on the
   solved joint and turned by (current bone angle - rest angle), so walk cycles, actions, pose keys and lip-sync all drive it. */
(function (g) {
'use strict';
const NS = g.Inkreel;
const { D2R, shade, wob } = NS;

const UP_BONES = { torso: 1, head: 1 };
const shadeCache = {};
const dark = (hex, a) => { const k = hex + a; return shadeCache[k] || (shadeCache[k] = shade(hex, a)); };

function frames(P, pose) {
  const r = pose.rot;
  return {
    armB_up: [P.sh, pose.aB + r], armB_lo: [P.elB, pose.aB + pose.eB + r],
    legB_up: [P.hip, pose.tB + r], legB_lo: [P.knB, pose.tB + pose.kB + r], footB: [P.anB, pose.tB + pose.kB + 90 + r],
    torso: [P.hip, P.torsoAngle],
    legF_up: [P.hip, pose.tF + r], legF_lo: [P.knF, pose.tF + pose.kF + r], footF: [P.anF, pose.tF + pose.kF + 90 + r],
    head: [P.hd, P.headAngle],
    armF_up: [P.sh, pose.aF + r], armF_lo: [P.elF, pose.aF + pose.eF + r],
  };
}

function tracePath(ctx, rings, jit, seed, amp) {
  ctx.beginPath();
  let n = 0;
  for (const ring of rings) {
    for (let i = 0; i < ring.length; i++) {
      const x = ring[i][0] + (jit ? wob(seed, n) * amp : 0), y = ring[i][1] + (jit ? wob(seed + 5.1, n) * amp : 0); n++;
      if (i) ctx.lineTo(x, y); else ctx.moveTo(x, y);
    }
    ctx.closePath();
  }
}

function drawTraced(ctx, st, t, S0) {
  const ch = st.ch, rig = ch.rig || {}, rest = rig.rest || {}, P = NS.solve(st.pose, ch);
  const H = ch.height || 300, F = frames(P, st.pose);
  const amp = H * 0.0016 * (S0.wobble === undefined ? 1 : S0.wobble), seed = S0.seed + NS.strHash(st.id) * 3.31;
  ctx.save();
  ctx.translate(st.x, st.y);
  ctx.scale(st.facing, 1);
  const Z = z => { if (S0.zHook) S0.zHook(ctx, z); };
  const volume = !!S0.volume;
  const order = ch.parts || [];
  let lastZ = null;
  for (const part of order) {
    const f = F[part.bone]; if (!f) continue;
    const [o, a] = f;
    const delta = a - (rest[part.bone] || 0);
    const rot = (UP_BONES[part.bone] ? delta : -delta) * D2R;
    const z = part.z * H;
    if (volume) {   // thickness: a few darker copies behind the face of the part, so it reads as a slab when you orbit
      for (let k = 3; k >= 1; k--) {
        Z(z - k * 0.011 * H);
        ctx.save(); ctx.translate(o[0], o[1]); ctx.rotate(rot);
        for (const sh of part.shapes) { tracePath(ctx, sh.rings, false, 0, 0); ctx.fillStyle = dark(sh.fill, -0.18 - 0.1 * k); ctx.fill('evenodd'); }
        ctx.restore();
      }
    }
    if (z !== lastZ || volume) { Z(z); lastZ = z; }
    ctx.save(); ctx.translate(o[0], o[1]); ctx.rotate(rot);
    for (const sh of part.shapes) { tracePath(ctx, sh.rings, amp > 0, seed + part.z * 17, amp); ctx.fillStyle = sh.fill; ctx.fill('evenodd'); }
    // lip-sync: while speaking, a mouth shape opens over the head at the face anchor, following the voice (or the letters of the line)
    if (part.bone === 'head' && rig.face && st.mouth > 0.06) {
      const fc = rig.face, mw = fc.w, mh = mw * (0.12 + 0.62 * st.mouth);
      ctx.beginPath(); ctx.ellipse(fc.x, fc.y, mw / 2, mh / 2, 0, 0, 6.2832);
      ctx.fillStyle = '#35090f'; ctx.fill(); ctx.lineWidth = Math.max(1.5, H * 0.004); ctx.strokeStyle = '#1b0508'; ctx.stroke();
    }
    ctx.restore();
  }
  ctx.restore();
}

NS.drawTraced = drawTraced;
})(typeof window !== 'undefined' ? window : globalThis);
