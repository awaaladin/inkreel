import { useCallback, useEffect, useRef, useState, type PointerEvent as RPointerEvent, type WheelEvent as RWheelEvent } from 'react';
import { api } from '../lib/api';
import { engineOpts, quantize } from '../lib/engine';
import { useClock, useStudio } from '../state';
import { Icon } from './Icon';

const PRESETS: { id: string; label: string; yaw: number; pitch: number }[] = [
  { id: 'front', label: 'Front', yaw: 0, pitch: 0 },
  { id: 'three', label: '3/4', yaw: 30, pitch: 12 },
  { id: 'side', label: 'Side', yaw: 90, pitch: 0 },
  { id: 'top', label: 'Top', yaw: 0, pitch: 72 },
];

/** The stage: draws the scene with the orbit renderer; drag to orbit, right-drag to pan, wheel to zoom; record what you see. */
export function Viewport() {
  const { bundle, engine, clock, view, scope, series, toast, refreshRecordings, loading, error } = useStudio();
  const cvRef = useRef<HTMLCanvasElement>(null);
  const [recording, setRecording] = useState(false);
  const [recSecs, setRecSecs] = useState(0);
  const recRef = useRef<{ rec: MediaRecorder; chunks: Blob[]; stopAtEnd: boolean } | null>(null);
  const [stopAtEnd, setStopAtEnd] = useState(true);
  const dragRef = useRef<{ x: number; y: number; mode: 'orbit' | 'pan' } | null>(null);
  const [, force] = useState(0);
  const { playing } = useClock();

  // ---- render loop (draws only when something changed, or while playing / recording / gliding)
  useEffect(() => {
    const cv = cvRef.current; if (!cv || !bundle || !engine || !bundle.scenes.length) return;
    const ctx = cv.getContext('2d'); if (!ctx) return;
    cv.width = engine.VW; cv.height = engine.VH;
    let raf = 0, last = performance.now(), dirty = true;
    const mark = () => { dirty = true; };
    const u1 = clock.subscribe(mark), u2 = view.subscribe(mark);
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.1, (now - last) / 1000); last = now;
      if (clock.playing) {
        clock.t += dt * clock.speed;
        if (clock.t >= clock.b) {
          if (recRef.current?.stopAtEnd) { clock.t = clock.b - 1e-3; clock.playing = false; stopRecording(); }
          else if (clock.loop) clock.t = clock.a; else { clock.t = Math.max(clock.a, clock.b - 1e-3); clock.playing = false; }
        }
        clock.emit(); dirty = true;
      }
      if (view.step(dt)) dirty = true;
      if (!dirty) return;
      dirty = false;
      try { engine.renderOrbit(ctx, bundle, quantize(clock.t, bundle), engineOpts(bundle, view.v)); } catch (e) { console.error('render failed', e); }
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); u1(); u2(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bundle, engine, clock, view]);

  // ---- orbit controls
  const down = (e: RPointerEvent<HTMLDivElement>) => {
    e.currentTarget.setPointerCapture(e.pointerId);
    dragRef.current = { x: e.clientX, y: e.clientY, mode: e.button === 2 || e.shiftKey || e.button === 1 ? 'pan' : 'orbit' };
  };
  const move = (e: RPointerEvent<HTMLDivElement>) => {
    const d = dragRef.current; if (!d) return;
    const dx = e.clientX - d.x, dy = e.clientY - d.y; d.x = e.clientX; d.y = e.clientY;
    if (d.mode === 'orbit') view.set({ yaw: view.v.yaw + dx * 0.4, pitch: Math.max(-60, Math.min(80, view.v.pitch + dy * 0.3)) });
    else view.set({ panX: view.v.panX + dx * (1280 / e.currentTarget.clientWidth), panY: view.v.panY + dy * (1280 / e.currentTarget.clientWidth) });
  };
  const up = () => { dragRef.current = null; };
  const wheel = (e: RWheelEvent<HTMLDivElement>) => { view.set({ zoom: Math.max(0.25, Math.min(4, view.v.zoom * Math.exp(-e.deltaY * 0.0012))) }); };
  const reset = () => view.glideTo({ yaw: 0, pitch: 0, zoom: 1, panX: 0, panY: 0 });

  // ---- record exactly what the canvas shows (including the orbit you do while it plays)
  const startRecording = useCallback(() => {
    const cv = cvRef.current; if (!cv || recRef.current) return;
    if (typeof MediaRecorder === 'undefined') { toast({ kind: 'error', text: 'This browser cannot record the canvas.', hint: 'Use Chrome or Edge.' }); return; }
    const mime = ['video/webm;codecs=vp9', 'video/webm;codecs=vp8', 'video/webm'].find(m => MediaRecorder.isTypeSupported(m));
    const stream = cv.captureStream(30);
    const rec = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 12_000_000 });
    const chunks: Blob[] = [];
    rec.ondataavailable = e => { if (e.data.size) chunks.push(e.data); };
    rec.onstop = async () => {
      recRef.current = null; setRecording(false); clock.playing = false; clock.emit();
      const name = [series?.series.id, scope.scene ?? scope.episode].filter(Boolean).join('-') || 'recording';
      try {
        const r = await api.saveRecording(new Blob(chunks, { type: 'video/webm' }), name);
        toast({ kind: 'ok', text: r.mp4 ? `Saved ${r.file}` : `Saved ${r.file} (WebM)`, hint: r.note ?? r.path ?? 'Saved in the workspace exports folder.', href: r.url });
        void refreshRecordings();
      } catch (e) { const er = e as Error & { hint?: string }; toast({ kind: 'error', text: er.message, hint: er.hint }); }
    };
    recRef.current = { rec, chunks, stopAtEnd };
    rec.start(250); setRecording(true); setRecSecs(0);
    clock.t = clock.a; clock.playing = true; clock.emit();
  }, [clock, series, scope, stopAtEnd, toast, refreshRecordings]);
  function stopRecording() { const r = recRef.current; if (r && r.rec.state !== 'inactive') r.rec.stop(); }
  useEffect(() => { if (!recording) return; const i = setInterval(() => setRecSecs(s => s + 1), 1000); return () => clearInterval(i); }, [recording]);

  const empty = !!bundle && !bundle.scenes.length;
  const presetActive = (p: { yaw: number; pitch: number }) => Math.abs(view.target.yaw - p.yaw) < 1 && Math.abs(view.target.pitch - p.pitch) < 1;

  return (
    <section className="viewport" aria-label="Viewport">
      <div className="vp-tools">
        <div className="seg" role="group" aria-label="Camera angle">
          {PRESETS.map(p => <button key={p.id} className={presetActive(p) ? 'on' : ''} onClick={() => { view.glideTo({ yaw: p.yaw, pitch: p.pitch }); force(n => n + 1); }}>{p.label}</button>)}
        </div>
        <button className="tool" onClick={() => { reset(); force(n => n + 1); }} title="Reset view (double-click the stage)"><Icon name="reset" /> Reset</button>
        <span className="hint"><Icon name="orbit" width={15} height={15} /> drag to orbit · right-drag to pan · scroll to zoom</span>
        <div className="spacer" />
        <label className="check"><input type="checkbox" checked={stopAtEnd} onChange={e => setStopAtEnd(e.target.checked)} disabled={recording} /> stop at end</label>
        <button className={`rec ${recording ? 'live' : ''}`} onClick={() => (recording ? stopRecording() : startRecording())} disabled={!bundle || empty}
          aria-pressed={recording} title="Record what you see (including any orbit you do) and save it as a video">
          <Icon name={recording ? 'stop' : 'record'} />{recording ? `Stop ${String(Math.floor(recSecs / 60)).padStart(1, '0')}:${String(recSecs % 60).padStart(2, '0')}` : 'Record'}
        </button>
      </div>
      <div className={`stage ${playing ? 'playing' : ''}`} onPointerDown={down} onPointerMove={move} onPointerUp={up} onPointerCancel={up}
        onWheel={wheel} onDoubleClick={reset} onContextMenu={e => e.preventDefault()} role="application" aria-label="Animation stage. Drag to orbit the camera.">
        <canvas ref={cvRef} width={1280} height={720} />
        {recording && <div className="rec-badge"><i /> REC</div>}
        {(loading || (!bundle && !error) || !engine) && <div className="stage-msg"><div className="spin" /> {loading ? 'Opening workspace' : 'Loading scenes'}</div>}
        {empty && <div className="stage-msg"><div><Icon name="film" width={30} height={30} /><p>No scenes yet. Ask Claude Code to build one.</p></div></div>}
        {error && !bundle && <div className="stage-msg"><div><Icon name="alert" width={30} height={30} /><p>{error.message}<br /><small>{error.hint}</small></p></div></div>}
      </div>
    </section>
  );
}
