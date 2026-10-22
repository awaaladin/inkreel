(function () {
'use strict';
const NS = window.Inkreel;
const $ = id => document.getElementById(id);
const cv = $('cv'), ctx = cv.getContext('2d');
const S = { project: null, T: 0, playing: false, loop: false, speed: 1, last: 0, scene: null, lib: false, rec: null, version: -1 };

function esc(s) { return String(s).replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c])); }
function total() { return S.project && S.project.scenes.length ? NS.timeline(S.project).total : 0; }
function sceneStart(id) { const tl = NS.timeline(S.project); const i = S.project.scenes.findIndex(s => s.id === id); return i < 0 ? 0 : tl.scenes[i].start; }

async function load() {
  const r = await fetch('/api/project'); const j = await r.json();
  S.project = j.project; S.version = j.version;
  $('ptitle').textContent = S.project.meta.title;
  const tot = total(); if (S.T > tot) S.T = tot;
  $('empty').style.display = S.project.scenes.length ? 'none' : 'flex';
  tabs(); panels();
}

function tabs() {
  const box = $('scenetabs'); box.innerHTML = '';
  const all = document.createElement('button'); all.textContent = 'All scenes'; all.className = S.scene ? '' : 'on';
  all.onclick = () => { S.scene = null; S.T = 0; tabs(); }; box.appendChild(all);
  const tl = S.project.scenes.length ? NS.timeline(S.project) : { scenes: [] };
  S.project.scenes.forEach((s, i) => {
    const b = document.createElement('button'); b.textContent = `${i + 1}. ${s.name || s.id}`; b.dataset.id = s.id;
    b.className = S.scene === s.id ? 'on' : '';
    b.onclick = () => { S.scene = s.id; S.T = tl.scenes[i].start; tabs(); };
    box.appendChild(b);
  });
}

function range() {
  if (!S.project || !S.project.scenes.length) return [0, 0];
  if (!S.scene) return [0, total()];
  const i = S.project.scenes.findIndex(s => s.id === S.scene); if (i < 0) return [0, total()];
  const e = NS.timeline(S.project).scenes[i]; return [e.start, e.start + e.duration];
}

function panels() {
  const p = S.project, tl = p.scenes.length ? NS.timeline(p) : { scenes: [] };
  let h = '';
  p.scenes.forEach((s, i) => {
    h += `<h5>${i + 1}. ${esc(s.name || s.id)} <span class="dim">${esc(s.background.preset)} / ${esc(s.background.time || 'day')}</span></h5>`;
    const ev = [];
    for (const [cid, a] of Object.entries(s.actors || {})) {
      const nm = (p.characters[cid] || {}).name || cid;
      (a.says || []).forEach(x => ev.push([x.t, nm, `"${x.text}"`]));
      (a.actions || []).forEach(x => ev.push([x.t, nm, x.action]));
      (a.moves || []).forEach(x => ev.push([x.t, nm, `${x.style || 'walk'} to ${Math.round(x.x)}`]));
    }
    (s.captions || []).forEach(x => ev.push([x.t, 'caption', x.text]));
    (s.camera || []).filter(c => c.kind !== 'shake').forEach(c => ev.push([c.t, 'camera', c.kind + (c.zoom ? ' z' + (+c.zoom).toFixed(2) : '')]));
    ev.sort((a, b) => a[0] - b[0]);
    const st = tl.scenes[i] ? tl.scenes[i].start : 0;
    h += ev.map(e => `<div class="ev" data-t="${(st + e[0]).toFixed(2)}"><time>${e[0].toFixed(1)}s</time><b>${esc(e[1])}</b><span>${esc(e[2])}</span></div>`).join('') || '<div class="dim">no events yet</div>';
  });
  $('p-shots').innerHTML = h || '<div class="dim">No scenes yet.</div>';
  $('p-shots').querySelectorAll('.ev').forEach(el => el.onclick = () => { S.T = parseFloat(el.dataset.t); S.playing = false; sync(); });
  $('p-cast').innerHTML = Object.entries(p.characters).map(([id, c]) =>
    `<div class="card"><h4>${esc(c.name || id)}</h4><span class="sw" style="background:${c.skin}"></span><span class="sw" style="background:${c.top}"></span><span class="sw" style="background:${c.bottom}"></span><span class="sw" style="background:${c.hair}"></span>
    <div class="dim">${esc([c.hair_style, c.outfit, c.weapon, c.height && c.height + 'px'].filter(Boolean).join(' · '))}</div><div class="dim">id: ${esc(id)}</div></div>`).join('') || '<div class="dim">No characters yet.</div>';
  $('p-notes').innerHTML = (p.research || []).map(r => `<div class="card"><h4>${esc(r.topic || 'note')}</h4>${esc(r.notes || r.text || JSON.stringify(r))}</div>`).join('') || '<div class="dim">Research notes the director saves appear here.</div>';
}

function log(text, warn) {
  const d = document.createElement('div'); d.className = 'logline' + (warn ? ' warn' : ''); d.textContent = text;
  const box = $('p-log'); box.prepend(d); while (box.children.length > 200) box.lastChild.remove();
}

function sync() {
  const [a, b] = range(); const len = b - a;
  $('scrub').value = len ? Math.round(1000 * (S.T - a) / len) : 0;
  $('clock').textContent = `${Math.max(0, S.T - a).toFixed(1)} / ${len.toFixed(1)}`;
  $('bPlay').textContent = S.playing ? 'Pause' : 'Play';
}

function frame(now) {
  requestAnimationFrame(frame);
  if (!S.lib) return;
  const dt = Math.min(0.1, (now - S.last) / 1000); S.last = now;
  if (S.project && S.project.scenes.length) {
    const [a, b] = range();
    if (S.playing) {
      S.T += dt * S.speed;
      if (S.T >= b) { if (S.loop) S.T = a; else { S.T = b - 1e-3; S.playing = false; } }
    }
    ctx.save(); ctx.scale(1.5, 1.5);
    try { NS.renderProject(ctx, S.project, S.T, {}); } catch (e) { console.error(e); }
    ctx.restore();
    sync();
  } else { ctx.fillStyle = '#271d2b'; ctx.fillRect(0, 0, cv.width, cv.height); }
}

function play(sceneId) {
  if (sceneId !== undefined) { S.scene = sceneId || null; tabs(); }
  const [a] = range(); S.T = a; S.playing = true;
}

$('bPlay').onclick = () => { const [a, b] = range(); if (!S.playing && S.T >= b - 0.05) S.T = a; S.playing = !S.playing; };
$('bLoop').onclick = e => { S.loop = !S.loop; e.currentTarget.setAttribute('aria-pressed', S.loop); };
$('scrub').oninput = e => { const [a, b] = range(); S.T = a + (b - a) * e.target.value / 1000; S.playing = false; };
$('speed').onchange = e => { S.speed = parseFloat(e.target.value); };
document.addEventListener('keydown', e => {
  if (e.target.tagName === 'SELECT') return;
  if (e.code === 'Space') { e.preventDefault(); $('bPlay').click(); }
  if (e.key === 'l') $('bLoop').click();
});
$('stabs').onclick = e => {
  const b = e.target.closest('button'); if (!b) return;
  document.querySelectorAll('.stabs button,.panel').forEach(x => x.classList.remove('on'));
  b.classList.add('on'); $('p-' + b.dataset.p).classList.add('on');
};

$('bRec').onclick = () => {
  const btn = $('bRec');
  if (S.rec) { S.rec.stop(); return; }
  if (!window.MediaRecorder) { log('This browser cannot record. Use /export in the terminal.', true); return; }
  const stream = cv.captureStream(30), chunks = [];
  const mime = ['video/webm;codecs=vp9', 'video/webm'].find(m => MediaRecorder.isTypeSupported(m));
  const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 8e6 });
  rec.ondataavailable = e => e.data.size && chunks.push(e.data);
  rec.onstop = async () => {
    S.rec = null; btn.classList.remove('on'); btn.textContent = 'Record'; S.playing = false;
    const blob = new Blob(chunks, { type: 'video/webm' });
    await fetch('/api/upload?name=recording-' + Date.now() + '.webm', { method: 'POST', body: blob });
  };
  S.rec = rec; rec.start(); btn.classList.add('on'); btn.textContent = 'Stop';
  play(S.scene);
  const check = setInterval(() => { if (!S.playing && S.rec) { clearInterval(check); S.rec && S.rec.stop(); } if (!S.rec) clearInterval(check); }, 300);
};

function connect() {
  const es = new EventSource('/api/events');
  const st = $('status');
  es.onopen = () => { st.dataset.on = 1; st.lastChild.textContent = 'live'; };
  es.onerror = () => { st.dataset.on = 0; st.lastChild.textContent = 'reconnecting'; };
  es.onmessage = async m => {
    const ev = JSON.parse(m.data);
    if (ev.type === 'project') { if (ev.version !== S.version) await load(); }
    else if (ev.type === 'touched') {
      await load();
      if (S.project.scenes.some(s => s.id === ev.scene) && !S.playing && !S.rec) { S.scene = ev.scene; tabs(); play(ev.scene); }
    }
    else if (ev.type === 'log') log(ev.text, ev.warn);
    else if (ev.type === 'busy') $('busy').classList.toggle('on', ev.on);
    else if (ev.type === 'cmd' && ev.action === 'play') play(ev.scene || null);
  };
}

(async function init() {
  const lib = await (await fetch('/web/library.json')).json(); NS.setLibrary(lib);
  try { await Promise.all([document.fonts.load('20px "Patrick Hand"'), document.fonts.load('20px Bangers')]); } catch (e) {}
  S.lib = true;
  await load(); connect(); requestAnimationFrame(frame);
})();
})();
