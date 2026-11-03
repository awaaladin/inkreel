import { useMemo, useRef, useState, type PointerEvent } from 'react';
import { api, type Ev } from '../lib/api';
import { useClock, useStudio } from '../state';
import { Icon } from './Icon';

interface Item { ev: Ev & Record<string, unknown>; label: string; dur: number; diamond?: boolean }
interface Row { id: string; label: string; items: Item[] }

const SNAP = 1 / 24;

/** Scene timeline: one row per character plus camera / fx / captions / drawings. Drag a block to retime it (saved as a real edit).
 *  Colour shows who made it (AI, you, import); a lock means the AI may not touch it. */
export function Timeline() {
  const { bundle, engine, scope, sid, toast, clock } = useStudio();
  const { t: T } = useClock();
  const [pxPerSec, setPx] = useState(70);
  const [sel, setSel] = useState<string | null>(null);
  const drag = useRef<{ id: string; x0: number; t0: number; moved: boolean } | null>(null);
  const [live, setLive] = useState<{ id: string; t: number } | null>(null);

  const info = useMemo(() => {
    if (!bundle || !engine || !scope.scene) return null;
    const tl = engine.timeline(bundle).scenes.find(s => s.id === scope.scene); const sc = bundle.scenes.find(s => s.id === scope.scene);
    if (!tl || !sc) return null;
    const lib = (engine as unknown as { getLibrary(): { actions: Record<string, { dur: number }> } }).getLibrary().actions;
    const actionDur = (name: string, ev: Ev & { dur?: number }) => ev.dur ?? (bundle.actions[name] as { dur?: number } | undefined)?.dur ?? lib[name]?.dur ?? 0.8;
    const rows: Row[] = [];
    for (const [cid, a] of Object.entries(sc.actors)) {
      const items: Item[] = [];
      for (const m of a.moves ?? []) items.push({ ev: m as never, label: `${(m as { style?: string }).style ?? 'walk'}`, dur: (m as { dur?: number }).dur ?? 1 });
      for (const x of a.actions ?? []) items.push({ ev: x as never, label: String((x as { action?: string }).action).replace(/^_.*_\d+$/, 'custom'), dur: actionDur(String((x as { action?: string }).action), x as never) });
      for (const s of a.says ?? []) items.push({ ev: s as never, label: `"${String((s as { text?: string }).text ?? '').slice(0, 24)}"`, dur: (s as { dur?: number }).dur ?? 2 });
      for (const k of (a as unknown as { keys?: Ev[] }).keys ?? []) items.push({ ev: k as never, label: '', dur: 0, diamond: true });
      rows.push({ id: cid, label: cid, items });
    }
    const simple = (id: string, label: string, list: Ev[] | undefined, text: (e: Ev & Record<string, unknown>) => string, dur: (e: Ev & Record<string, unknown>) => number) =>
      rows.push({ id, label, items: (list ?? []).map(e => ({ ev: e as never, label: text(e as never), dur: dur(e as never) })) });
    simple('camera', 'Camera', sc.camera, e => String(e.kind), e => Number(e.dur ?? 0.3));
    simple('fx', 'Effects', sc.fx, e => String(e.kind), e => Number(e.dur ?? 0.5));
    simple('captions', 'Captions', sc.captions, e => String(e.text ?? '').slice(0, 20), e => Number(e.dur ?? 2));
    const drawings = (sc as unknown as { drawings?: Ev[] }).drawings;
    if (drawings?.length) simple('drawings', 'Drawings', drawings, () => 'cel', e => Number(e.dur ?? 1 / 12));
    return { start: tl.start, dur: tl.duration, rows, sceneId: sc.id };
  }, [bundle, engine, scope.scene]);

  if (!info) return <section className="timeline empty-tl"><Icon name="scene" /> Pick a scene on the left to edit its timeline.</section>;
  const W = Math.max(600, info.dur * pxPerSec + 40);
  const local = Math.max(0, T - info.start);
  const ticks = Array.from({ length: Math.ceil(info.dur) + 1 }, (_, i) => i);

  const down = (e: PointerEvent, it: Item) => {
    e.stopPropagation(); (e.currentTarget as Element).setPointerCapture(e.pointerId);
    drag.current = { id: it.ev.id, x0: e.clientX, t0: it.ev.t, moved: false }; setSel(it.ev.id);
  };
  const move = (e: PointerEvent) => {
    const d = drag.current; if (!d) return; const dx = e.clientX - d.x0; if (Math.abs(dx) > 3) d.moved = true;
    if (d.moved) setLive({ id: d.id, t: Math.max(0, Math.round((d.t0 + dx / pxPerSec) / SNAP) * SNAP) });
  };
  const up = async (e: PointerEvent, it: Item) => {
    const d = drag.current; drag.current = null; const l = live; setLive(null);
    (e.currentTarget as Element).releasePointerCapture?.(e.pointerId);
    if (!d) return;
    if (!d.moved || !l) { clock.t = info.start + it.ev.t; clock.playing = false; clock.emit(); return; }   // a click seeks to the block
    try {
      const r = await api.ops(sid!, [{ name: 'update_event', args: { scene: info.sceneId, id: it.ev.id, fields: { t: Math.round(l.t * 1000) / 1000 } } }], 'retime');
      if (!r.results[0].ok) toast({ kind: 'error', text: r.results[0].message });
    } catch (err) { toast({ kind: 'error', text: (err as Error).message }); }
  };
  const remove = async () => {
    if (!sel) return;
    try { const r = await api.ops(sid!, [{ name: 'delete_event', args: { scene: info.sceneId, id: sel } }], 'delete event'); if (!r.results[0].ok) toast({ kind: 'error', text: r.results[0].message }); else setSel(null); }
    catch (err) { toast({ kind: 'error', text: (err as Error).message }); }
  };
  const toggleLock = async () => {
    if (!sel) return; const it = info.rows.flatMap(r => r.items).find(i => i.ev.id === sel); if (!it) return;
    try { await api.ops(sid!, [{ name: 'set_lock', args: { scene: info.sceneId, ids: [sel], lock: !it.ev.lock } }], 'lock'); } catch (err) { toast({ kind: 'error', text: (err as Error).message }); }
  };
  const seek = (e: PointerEvent<HTMLDivElement>) => {
    const r = e.currentTarget.getBoundingClientRect(); clock.t = info.start + Math.max(0, Math.min(info.dur, (e.clientX - r.left) / pxPerSec)); clock.playing = false; clock.emit();
  };

  return (
    <section className="timeline" aria-label="Timeline">
      <div className="tl-head">
        <b>Timeline</b>
        <span className="dim">drag a block to retime · click to jump · <span className="legend ai">AI</span> <span className="legend user">you</span> <span className="legend import">imported</span></span>
        <div className="spacer" />
        <button className="tool" onClick={() => void toggleLock()} disabled={!sel} title="Lock so the AI cannot change it">Lock / unlock</button>
        <button className="tool" onClick={() => void remove()} disabled={!sel}>Delete</button>
        <label className="zoom">zoom <input type="range" min="30" max="220" value={pxPerSec} onChange={e => setPx(Number(e.target.value))} /></label>
      </div>
      <div className="tl-scroll">
        <div className="tl-body" style={{ width: W + 96 }}>
          <div className="tl-ruler" onPointerDown={seek} style={{ marginLeft: 96, width: W }}>
            {ticks.map(i => <span key={i} style={{ left: i * pxPerSec }}>{i}s</span>)}
          </div>
          {info.rows.map(row => (
            <div key={row.id} className="tl-row">
              <div className="tl-label">{row.label}</div>
              <div className="tl-track" style={{ width: W }} onPointerDown={seek}>
                {row.items.map(it => {
                  const t = live?.id === it.ev.id ? live.t : it.ev.t;
                  const cls = `blk ${it.ev.src} ${it.ev.lock ? 'locked' : ''} ${sel === it.ev.id ? 'sel' : ''} ${it.diamond ? 'dia' : ''}`;
                  return (
                    <div key={it.ev.id + row.id} className={cls} title={`${it.label || 'pose key'} · ${t.toFixed(2)}s · ${it.ev.src}${it.ev.lock ? ' · locked' : ''}`}
                      style={{ left: t * pxPerSec, width: it.diamond ? 11 : Math.max(8, it.dur * pxPerSec) }}
                      onPointerDown={e => down(e, it)} onPointerMove={move} onPointerUp={e => void up(e, it)}>{it.label}</div>
                  );
                })}
              </div>
            </div>
          ))}
          <div className="tl-playhead" style={{ left: 96 + local * pxPerSec }} />
        </div>
      </div>
    </section>
  );
}
