import { useEffect, useMemo, useRef, useState } from 'react';
import { api, type Ev } from '../lib/api';
import { useClock, useStudio } from '../state';
import { Icon } from './Icon';

const JOINTS: { id: string; label: string; min: number; max: number; step?: number }[] = [
  { id: 'torso', label: 'Torso lean', min: -60, max: 60 }, { id: 'head', label: 'Head', min: -50, max: 50 },
  { id: 'aF', label: 'Front arm', min: -180, max: 180 }, { id: 'eF', label: 'Front elbow', min: -20, max: 150 },
  { id: 'aB', label: 'Back arm', min: -180, max: 180 }, { id: 'eB', label: 'Back elbow', min: -20, max: 150 },
  { id: 'tF', label: 'Front thigh', min: -90, max: 120 }, { id: 'kF', label: 'Front knee', min: -140, max: 10 },
  { id: 'tB', label: 'Back thigh', min: -90, max: 120 }, { id: 'kB', label: 'Back knee', min: -140, max: 10 },
  { id: 'wpn', label: 'Weapon', min: -180, max: 180 }, { id: 'rot', label: 'Body rotation', min: -100, max: 100 },
  { id: 'rx', label: 'Shift sideways', min: -1, max: 1, step: 0.01 }, { id: 'ry', label: 'Lift', min: -1, max: 0.5, step: 0.01 },
];

type Tab = 'pose' | 'draw' | 'voice';

/** Right panel: frame-by-frame posing, hand drawing, and voice. Every control writes a real op; nothing here is decorative. */
export function Inspector() {
  const [tab, setTab] = useState<Tab>('pose');
  return (
    <aside className="inspector" aria-label="Inspector">
      <div className="tabs" role="tablist">
        {(['pose', 'draw', 'voice'] as Tab[]).map(t => <button key={t} role="tab" aria-selected={tab === t} className={tab === t ? 'on' : ''} onClick={() => setTab(t)}>{{ pose: 'Pose & keys', draw: 'Draw', voice: 'Voice' }[t]}</button>)}
      </div>
      <div className="tab-body">{tab === 'pose' ? <PoseTab /> : tab === 'draw' ? <DrawTab /> : <VoiceTab />}</div>
    </aside>
  );
}

function useCurrent() {
  const { bundle, engine, clock } = useStudio();
  const { t } = useClock();
  return useMemo(() => {
    if (!bundle || !engine) return null;
    const loc = (engine as unknown as { locate(p: unknown, T: number): { scene: { id: string; actors: Record<string, { keys?: Ev[] }> }; t: number } | null }).locate(bundle, t);
    return loc ? { scene: loc.scene, t: loc.t, T: t, clock } : null;
  }, [bundle, engine, t, clock]);
}

// ---------------------------------------------------------------- pose + keys
function PoseTab() {
  const { bundle, engine, sid, toast, clock } = useStudio();
  const cur = useCurrent();
  const [cid, setCid] = useState<string>('');
  const cast = cur ? Object.keys(cur.scene.actors) : [];
  useEffect(() => { if (cast.length && !cast.includes(cid)) setCid(cast[0]); }, [cast.join(','), cid]);  // eslint-disable-line react-hooks/exhaustive-deps
  const [draft, setDraft] = useState<Record<string, number>>({});
  const timer = useRef<number>(0);
  const NS = engine as unknown as { sampleActor(s: unknown, c: unknown, id: string, t: number, p: unknown): { pose: Record<string, number> }; resolveChars(p: unknown): unknown; prepReset(s: unknown): void } | null;

  const sampled = useMemo(() => {
    if (!cur || !NS || !bundle || !cid || !cur.scene.actors[cid]) return null;
    try { return NS.sampleActor(cur.scene, NS.resolveChars(bundle), cid, cur.t, bundle).pose; } catch { return null; }
  }, [cur, NS, bundle, cid]);
  useEffect(() => { setDraft({}); }, [cur?.T, cid]);  // eslint-disable-line react-hooks/exhaustive-deps

  if (!cur || !sid) return <p className="empty">Pick a scene with characters.</p>;
  if (!cast.length) return <p className="empty">This scene has no characters yet. Ask Claude Code to place one.</p>;
  const keys = (cur.scene.actors[cid]?.keys ?? []).slice().sort((a, b) => a.t - b.t);
  const fps = 12, frame = Math.round(cur.t * fps);

  const apply = (joint: string, v: number) => {
    // live preview: edit the in-memory scene immediately, then save after a short pause
    const next = { ...draft, [joint]: v }; setDraft(next);
    const actor = cur.scene.actors[cid] as unknown as { keys?: Ev[] };
    const keysArr = (actor.keys ??= []);
    const near = keysArr.find(k => Math.abs(k.t - cur.t) < 1 / 48);
    if (near) (near as unknown as { pose: Record<string, number> }).pose = { ...(near as unknown as { pose: Record<string, number> }).pose, ...next };
    else keysArr.push({ id: 'tmp', t: cur.t, src: 'user', lock: false, pose: { ...(sampled ?? {}), ...next }, ease: 'smooth' } as unknown as Ev);
    keysArr.sort((a, b) => a.t - b.t); NS?.prepReset(cur.scene); clock.emit();
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => void save(next), 350);
  };
  const save = async (pose: Record<string, number>) => {
    try {
      const full = { ...(sampled ?? {}), ...pose };
      const r = await api.ops(sid, [{ name: 'pose_key', args: { scene: cur.scene.id, char: cid, t: Math.round(cur.t * 1000) / 1000, pose: full } }], `pose ${cid} f${frame}`);
      if (!r.results[0].ok) toast({ kind: 'error', text: r.results[0].message });
    } catch (e) { toast({ kind: 'error', text: (e as Error).message, hint: (e as { hint?: string }).hint }); }
  };
  const setKeyHere = () => { if (sampled) void save({ ...sampled }); };
  const del = async (k: Ev) => {
    try { await api.ops(sid, [{ name: 'delete_event', args: { scene: cur.scene.id, id: k.id } }], 'delete key'); } catch (e) { toast({ kind: 'error', text: (e as Error).message }); }
  };
  const jump = (dir: 1 | -1) => {
    const t = dir > 0 ? keys.find(k => k.t > cur.t + 1e-3) : [...keys].reverse().find(k => k.t < cur.t - 1e-3);
    if (t) { clock.t = cur.T - cur.t + t.t; clock.playing = false; clock.emit(); }
  };
  const step = (n: number) => { clock.t = Math.max(0, clock.t + n / fps); clock.playing = false; clock.emit(); };
  const onKeyHere = keys.some(k => Math.abs(k.t - cur.t) < 1 / 48);

  return (
    <div className="pose">
      <div className="row2">
        <select aria-label="Character" value={cid} onChange={e => setCid(e.target.value)}>{cast.map(c => <option key={c}>{c}</option>)}</select>
        <span className="dim num">frame {frame} · {cur.t.toFixed(2)}s</span>
      </div>
      <div className="row2 btns">
        <button className="tool icon" onClick={() => step(-1)} title="Previous frame">‹</button>
        <button className="tool icon" onClick={() => step(1)} title="Next frame">›</button>
        <button className="tool" onClick={() => jump(-1)} disabled={!keys.length}>◂ key</button>
        <button className="tool" onClick={() => jump(1)} disabled={!keys.length}>key ▸</button>
        <button className={`tool ${onKeyHere ? 'on' : ''}`} onClick={setKeyHere} title="Save the current pose as a key at this frame">Set key</button>
      </div>
      <div className="keystrip" aria-label="Keys of this character">
        {keys.length === 0 && <span className="dim">No keys yet. Move a slider or press Set key.</span>}
        {keys.map(k => <button key={k.id} className={`kpin ${Math.abs(k.t - cur.t) < 1 / 48 ? 'on' : ''}`} title={`${k.t.toFixed(2)}s`} onClick={() => { clock.t = cur.T - cur.t + k.t; clock.playing = false; clock.emit(); }} onContextMenu={e => { e.preventDefault(); void del(k); }} />)}
      </div>
      {keys.length > 0 && <p className="tiny dim">{keys.length} keys · click to jump · right-click to delete</p>}
      <div className="sliders">
        {JOINTS.map(j => {
          const v = draft[j.id] ?? sampled?.[j.id] ?? 0;
          return (
            <label key={j.id} className="slider"><span>{j.label}</span>
              <input type="range" min={j.min} max={j.max} step={j.step ?? 1} value={v} onChange={e => apply(j.id, Number(e.target.value))} />
              <output className="num">{Math.abs(v) < 2 && j.step ? v.toFixed(2) : Math.round(v * 100) / 100}</output>
            </label>
          );
        })}
      </div>
    </div>
  );
}

// ---------------------------------------------------------------- hand drawing
function DrawTab() {
  const { bundle, engine, sid, toast, clock, view } = useStudio();
  const cur = useCurrent();
  const [on, setOn] = useState(false);
  const [color, setColor] = useState('#1a1a1a');
  const [size, setSize] = useState(5);
  const [onion, setOnion] = useState(true);
  const [dur, setDur] = useState(1 / 12);
  const overlay = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    // drawing happens in the front view so screen pixels map straight to scene coordinates
    if (!on) { document.querySelector('.stage')?.classList.remove('drawing'); return; }
    view.glideTo({ yaw: 0, pitch: 0, zoom: 1, panX: 0, panY: 0 });
    const stage = document.querySelector('.stage') as HTMLElement | null; if (!stage) return;
    stage.classList.add('drawing');
    const cv = stage.querySelector('canvas') as HTMLCanvasElement;
    overlay.current = stage.querySelector('.draw-live') as HTMLCanvasElement | null;
    let pts: number[][] = []; let drawing = false;
    const toWorld = (e: PointerEvent): [number, number] | null => {
      const NS = window.Inkreel as unknown as { lastFrame?: { fx: number; fy: number; scale: number; panX: number; panY: number } };
      const lf = NS.lastFrame; if (!lf) return null;
      const r = cv.getBoundingClientRect(); const sx = ((e.clientX - r.left) / r.width) * 1280, sy = ((e.clientY - r.top) / r.height) * 720;
      return [(sx - 640 - lf.panX) / lf.scale + lf.fx, (sy - 360 - lf.panY) / lf.scale + lf.fy];
    };
    const down = (e: PointerEvent) => { if (e.button !== 0 || e.shiftKey) return; e.stopPropagation(); (e.target as Element).setPointerCapture?.(e.pointerId); drawing = true; pts = []; const w = toWorld(e); if (w) pts.push(w); clock.playing = false; clock.emit(); };
    const move = (e: PointerEvent) => { if (!drawing) return; e.stopPropagation(); const w = toWorld(e); if (w) { pts.push(w); live(); } };
    const up = async (e: PointerEvent) => {
      if (!drawing) return; e.stopPropagation(); drawing = false; const ov = overlay.current; if (ov) ov.getContext('2d')!.clearRect(0, 0, ov.width, ov.height);
      if (!pts.length || !cur || !sid) return;
      try {
        const r = await api.ops(sid, [{ name: 'add_drawing', args: { scene: cur.scene.id, t: Math.round(cur.t * 1000) / 1000, dur, strokes: [{ c: color, w: size, pts }] } }], 'draw');
        if (!r.results[0].ok) toast({ kind: 'error', text: r.results[0].message });
      } catch (err) { toast({ kind: 'error', text: (err as Error).message }); }
    };
    const live = () => {  // show the stroke while it is being drawn, before it is saved
      const NS = window.Inkreel as unknown as { lastFrame?: { fx: number; fy: number; scale: number; panX: number; panY: number } };
      const lf = NS.lastFrame, ov = overlay.current; if (!lf || !ov) return; const c = ov.getContext('2d')!;
      c.clearRect(0, 0, ov.width, ov.height); c.lineCap = 'round'; c.lineJoin = 'round'; c.strokeStyle = color; c.lineWidth = size * lf.scale; c.beginPath();
      pts.forEach((p, i) => { const x = (p[0] - lf.fx) * lf.scale + 640 + lf.panX, y = (p[1] - lf.fy) * lf.scale + 360 + lf.panY; if (i) c.lineTo(x, y); else c.moveTo(x, y); }); c.stroke();
    };
    stage.addEventListener('pointerdown', down, true); stage.addEventListener('pointermove', move, true); stage.addEventListener('pointerup', up, true);
    return () => { stage.removeEventListener('pointerdown', down, true); stage.removeEventListener('pointermove', move, true); stage.removeEventListener('pointerup', up, true); stage.classList.remove('drawing'); };
  }, [on, color, size, dur, cur?.scene.id, cur?.t, sid]);  // eslint-disable-line react-hooks/exhaustive-deps

  // onion skin flag is read by the engine through opts; stored on window for the viewport loop
  useEffect(() => { (window as unknown as { __onion?: boolean }).__onion = on && onion; clock.emit(); }, [on, onion, clock]);

  if (!cur || !sid || !bundle || !engine) return <p className="empty">Pick a scene to draw on.</p>;
  const cels = ((cur.scene as unknown as { drawings?: Ev[] }).drawings ?? []).slice().sort((a, b) => a.t - b.t);
  const here = cels.find(d => cur.t >= d.t - 1e-6 && cur.t < d.t + ((d as unknown as { dur?: number }).dur ?? 1 / 12) - 1e-6);
  const undoStroke = async () => { try { await api.ops(sid, [{ name: 'clear_drawing', args: { scene: cur.scene.id, t: cur.t, last_stroke_only: true } }], 'erase stroke'); } catch (e) { toast({ kind: 'error', text: (e as Error).message }); } };
  const clearFrame = async () => { try { await api.ops(sid, [{ name: 'clear_drawing', args: { scene: cur.scene.id, t: cur.t } }], 'erase drawing'); } catch (e) { toast({ kind: 'error', text: (e as Error).message }); } };
  const nextFrame = () => { clock.t += dur; clock.playing = false; clock.emit(); };
  return (
    <div className="draw">
      <button className={`tool big ${on ? 'on' : ''}`} onClick={() => setOn(!on)} aria-pressed={on}><Icon name="ink" /> {on ? 'Drawing on (click to stop)' : 'Start drawing'}</button>
      <p className="tiny dim">Draw on the stage at the current frame. Each frame you draw on becomes a hand-drawn cel that shows for its length, so stepping and drawing again makes frame-by-frame animation. Drawings live in the scene and turn with the 3D view.</p>
      <div className="row2"><label>Colour <input type="color" value={color} onChange={e => setColor(e.target.value)} /></label>
        <label>Size <input type="range" min="1" max="30" value={size} onChange={e => setSize(Number(e.target.value))} /> <output className="num">{size}</output></label></div>
      <div className="row2"><label>Frame length <select value={dur} onChange={e => setDur(Number(e.target.value))}>{[[1 / 24, '1 frame (24fps)'], [1 / 12, '2 frames (on twos)'], [1 / 8, '3 frames'], [0.25, '6 frames']].map(([v, l]) => <option key={String(v)} value={String(v)}>{l as string}</option>)}</select></label>
        <label className="check"><input type="checkbox" checked={onion} onChange={e => setOnion(e.target.checked)} /> onion skin</label></div>
      <div className="row2 btns">
        <button className="tool" onClick={nextFrame}>Next frame ▸</button>
        <button className="tool" onClick={() => void undoStroke()} disabled={!here}>Undo stroke</button>
        <button className="tool" onClick={() => void clearFrame()} disabled={!here}>Clear frame</button>
      </div>
      <p className="tiny dim">{cels.length} drawn frame(s) in this scene{here ? ` · this frame has ${((here as unknown as { strokes?: unknown[] }).strokes ?? []).length} stroke(s)` : ''}</p>
    </div>
  );
}

// ---------------------------------------------------------------- voice
function VoiceTab() {
  const { sid, toast, clock } = useStudio();
  const cur = useCurrent();
  const [rec, setRec] = useState<string | null>(null);
  const mr = useRef<{ r: MediaRecorder; chunks: Blob[] } | null>(null);
  if (!cur || !sid) return <p className="empty">Pick a scene.</p>;
  const lines: { cid: string; ev: Ev & { text?: string; dur?: number; audio?: string; env?: number[] } }[] = [];
  for (const [cid, a] of Object.entries(cur.scene.actors)) for (const s of ((a as unknown as { says?: Ev[] }).says ?? [])) lines.push({ cid, ev: s as never });
  lines.sort((a, b) => a.ev.t - b.ev.t);

  const start = async (cid: string, ev: Ev & { text?: string; dur?: number }) => {
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false } });
      const chunks: Blob[] = []; const r = new MediaRecorder(stream);
      r.ondataavailable = e => e.data.size && chunks.push(e.data);
      r.onstop = async () => {
        stream.getTracks().forEach(t => t.stop()); setRec(null); clock.playing = false; clock.emit();
        try {
          const blob = new Blob(chunks, { type: r.mimeType || 'audio/webm' });
          const up = await fetch(`/api/audio?name=${encodeURIComponent(cid + '-' + ev.id)}&ext=webm`, { method: 'POST', body: blob });
          if (!up.ok) throw new Error((await up.json()).detail?.error ?? 'upload failed');
          const { file } = await up.json();
          const ctx = new AudioContext(); const buf = await ctx.decodeAudioData(await blob.arrayBuffer()); void ctx.close();
          const env = envelope(buf, 24);
          const res = await api.ops(sid, [{ name: 'set_voice', args: { scene: cur.scene.id, id: ev.id, audio: file, env, env_fps: 24, dur: Math.round(buf.duration * 100) / 100 } }], `voice ${cid}`);
          toast({ kind: res.results[0].ok ? 'ok' : 'error', text: res.results[0].ok ? 'Voice saved. The mouth now follows your recording.' : res.results[0].message });
        } catch (e) { toast({ kind: 'error', text: (e as Error).message, hint: 'Allow the microphone and try again.' }); }
      };
      mr.current = { r, chunks }; r.start(); setRec(ev.id);
      clock.t = cur.T - cur.t + ev.t; clock.playing = true; clock.emit();   // play the scene so the voice actor hears and sees the timing
    } catch (e) { toast({ kind: 'error', text: 'Cannot use the microphone.', hint: (e as Error).message }); }
  };
  const stop = () => { mr.current?.r.stop(); };
  const edit = async (ev: Ev, text: string) => { try { await api.ops(sid, [{ name: 'update_event', args: { scene: cur.scene.id, id: ev.id, fields: { text } } }], 'edit line'); } catch (e) { toast({ kind: 'error', text: (e as Error).message }); } };
  const play = (ev: Ev & { audio?: string }) => { if (ev.audio) void new Audio(`/audio/${ev.audio}`).play(); };

  return (
    <div className="voice">
      <p className="tiny dim">Lines of dialogue in this scene. The mouth follows the letters of each line; record the real voice and it follows your recording instead.</p>
      {lines.length === 0 && <p className="empty">No dialogue in this scene.</p>}
      {lines.map(({ cid, ev }) => (
        <div key={ev.id} className="line">
          <div className="who"><b>{cid}</b><span className="dim num">{ev.t.toFixed(1)}s · {(ev.dur ?? 0).toFixed(1)}s</span></div>
          <textarea defaultValue={ev.text} rows={2} onBlur={e => e.target.value !== ev.text && void edit(ev, e.target.value)} aria-label={`Line by ${cid}`} />
          <div className="row2 btns">
            {rec === ev.id ? <button className="rec live small" onClick={stop}><Icon name="stop" /> Stop</button>
              : <button className="rec small" onClick={() => void start(cid, ev)} disabled={rec !== null}><Icon name="record" /> Record voice</button>}
            {ev.audio && <button className="tool" onClick={() => play(ev)}>▶ Play voice</button>}
            {ev.audio && <span className="chip ok">voiced</span>}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Mouth-openness envelope from a real recording: RMS per 1/fps seconds, normalised to the loud parts. */
function envelope(buf: AudioBuffer, fps: number): number[] {
  const ch = buf.getChannelData(0), win = Math.max(1, Math.floor(buf.sampleRate / fps)), n = Math.ceil(ch.length / win), out: number[] = [];
  for (let i = 0; i < n; i++) { let s = 0; const a = i * win, b = Math.min(ch.length, a + win); for (let j = a; j < b; j++) s += ch[j] * ch[j]; out.push(Math.sqrt(s / Math.max(1, b - a))); }
  const sorted = [...out].sort((x, y) => x - y), ref = sorted[Math.floor(sorted.length * 0.95)] || 1, floor = sorted[Math.floor(sorted.length * 0.2)] || 0;
  return out.map(v => Math.max(0, Math.min(1, (v - floor) / Math.max(1e-6, ref - floor))));
}
