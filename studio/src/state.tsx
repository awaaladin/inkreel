// Studio state. Playback time and the orbit view live in external stores so dragging/playing never re-renders React.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { api, type ApiError, type Bundle, type Recording, type SeriesData } from './lib/api';
import { FLAT, loadEngine, type InkreelNS, type View } from './lib/engine';

export interface Scope { episode?: string; scene?: string }
export interface Toast { id: number; kind: 'ok' | 'error' | 'info'; text: string; hint?: string; href?: string }

/** Playback clock over the whole-series timeline; `a`..`b` is the range of the current scope. */
export class Clock {
  t = 0; playing = false; loop = false; a = 0; b = 0; speed = 1;
  private subs = new Set<() => void>();
  private snap = { t: 0, playing: false, loop: false, a: 0, b: 0 };
  subscribe = (fn: () => void) => { this.subs.add(fn); return () => { this.subs.delete(fn); }; };
  getSnapshot = () => this.snap;
  emit() { this.snap = { t: this.t, playing: this.playing, loop: this.loop, a: this.a, b: this.b }; this.subs.forEach(f => f()); }
}

/** Orbit camera for the 3D view. Animates toward a target so presets glide and can be interrupted. */
export class ViewStore {
  v: View = { ...FLAT }; target: View = { ...FLAT };
  private subs = new Set<() => void>();
  subscribe = (fn: () => void) => { this.subs.add(fn); return () => { this.subs.delete(fn); }; };
  emit() { this.subs.forEach(f => f()); }
  set(p: Partial<View>) { this.v = { ...this.v, ...p }; this.target = { ...this.v }; this.emit(); }
  glideTo(p: Partial<View>) { this.target = { ...this.target, ...p }; this.emit(); }
  step(dt: number): boolean {
    const k = 1 - Math.exp(-dt * 12); let moving = false;
    for (const key of Object.keys(this.v) as (keyof View)[]) {
      const d = this.target[key] - this.v[key];
      if (d === 0) continue;
      moving = true;                                   // also true on the frame that lands exactly on the target, so it gets drawn
      this.v[key] = Math.abs(d) > 0.01 ? this.v[key] + d * k : this.target[key];
    }
    return moving;
  }
  get is3d() { return Math.abs(this.v.yaw) > 0.5 || Math.abs(this.v.pitch) > 0.5; }
}

interface Studio {
  sid: string | null; seriesList: string[]; series: SeriesData | null; bundle: Bundle | null; engine: InkreelNS | null;
  scope: Scope; setScope(s: Scope): void; clock: Clock; view: ViewStore; setSid(s: string): void;
  toasts: Toast[]; toast(t: Omit<Toast, 'id'>): void; dismissToast(id: number): void; loading: boolean; error: ApiError | null;
  recordings: Recording[]; refreshRecordings(): Promise<void>; undo(): Promise<void>; redo(): Promise<void>;
  sceneStart(id: string): number; sceneThumbs: Record<string, string>;
}

const Ctx = createContext<Studio | null>(null);
export const useStudio = () => { const c = useContext(Ctx); if (!c) throw new Error('StudioProvider missing'); return c; };
export const useClock = () => { const { clock } = useStudio(); return useSyncExternalStore(clock.subscribe, clock.getSnapshot); };

let nextId = 1;

export function StudioProvider({ children }: { children: ReactNode }) {
  const [seriesList, setSeriesList] = useState<string[]>([]);
  const [sid, setSidState] = useState<string | null>(new URLSearchParams(location.search).get('series'));
  const [series, setSeries] = useState<SeriesData | null>(null);
  const [bundle, setBundle] = useState<Bundle | null>(null);
  const [engine, setEngine] = useState<InkreelNS | null>(null);
  const [scope, setScope] = useState<Scope>({});
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [recordings, setRecordings] = useState<Recording[]>([]);
  const [sceneThumbs, setThumbs] = useState<Record<string, string>>({});
  const clock = useRef(new Clock()).current;
  const view = useRef(new ViewStore()).current;
  const sidRef = useRef(sid); sidRef.current = sid;

  const toast = useCallback((t: Omit<Toast, 'id'>) => {
    const id = nextId++; setToasts(x => [...x.slice(-3), { ...t, id }]);
    setTimeout(() => setToasts(x => x.filter(y => y.id !== id)), t.kind === 'error' ? 8000 : 5000);
  }, []);
  const dismissToast = useCallback((id: number) => setToasts(x => x.filter(y => y.id !== id)), []);
  const fail = useCallback((e: unknown) => { const err = e as ApiError; setError(err); toast({ kind: 'error', text: err.message, hint: err.hint }); }, [toast]);

  useEffect(() => {
    loadEngine().then(setEngine).catch(e => fail(Object.assign(e, { status: 0, hint: 'The drawing engine failed to load from /engine.' })));
    api.workspace().then(w => { setSeriesList(w.series); setSidState(s => s ?? w.series[0] ?? null); setError(null); }).catch(fail).finally(() => setLoading(false));
  }, [fail]);

  const refreshRecordings = useCallback(async () => { try { setRecordings((await api.recordings()).recordings); } catch { /* listed again next time */ } }, []);
  useEffect(() => { void refreshRecordings(); }, [refreshRecordings]);

  const load = useCallback(async () => {
    const id = sidRef.current; if (!id) return;
    try {
      const [s, b] = await Promise.all([api.series(id), api.bundle(id)]);
      setSeries(s); setBundle(b.bundle); setError(null);
    } catch (e) { fail(e); }
  }, [fail]);
  useEffect(() => { setSeries(null); setBundle(null); void load(); }, [sid, load]);

  // live sync: when the series changes on disk (Claude Code / terminal / another tab), reload
  useEffect(() => {
    const es = new EventSource('/api/events'); let timer = 0;
    es.onmessage = m => { const ev = JSON.parse(m.data); if (ev.type === 'changed' && ev.series === sidRef.current) { clearTimeout(timer); timer = window.setTimeout(() => void load(), 150); } };
    return () => { es.close(); clearTimeout(timer); };
  }, [load]);

  const timeline = useMemo(() => (bundle && engine && bundle.scenes.length ? engine.timeline(bundle) : { scenes: [], total: 0 }), [bundle, engine]);
  const sceneStart = useCallback((id: string) => timeline.scenes.find(s => s.id === id)?.start ?? 0, [timeline]);

  // clock range follows the scope
  useEffect(() => {
    let a = 0, b = timeline.total;
    if (scope.scene) { const s = timeline.scenes.find(x => x.id === scope.scene); if (s) { a = s.start; b = s.start + s.duration; } }
    else if (scope.episode && series) {
      const ids = series.episodes.find(e => e.id === scope.episode)?.scenes ?? []; const ss = timeline.scenes.filter(x => ids.includes(x.id));
      if (ss.length) { a = ss[0].start; b = ss[ss.length - 1].start + ss[ss.length - 1].duration; }
    }
    clock.a = a; clock.b = b; if (clock.t < a || clock.t > b) clock.t = a; clock.emit();
  }, [scope, timeline, series, clock]);
  useEffect(() => { clock.playing = false; clock.t = clock.a; clock.emit(); }, [scope, sid, clock]);

  // scene thumbnails drawn by the same engine
  useEffect(() => {
    if (!engine || !bundle) return;
    const cv = document.createElement('canvas'); cv.width = engine.VW; cv.height = engine.VH; const ctx = cv.getContext('2d')!;
    const small = document.createElement('canvas'); small.width = 320; small.height = 180; const sc = small.getContext('2d')!;
    const out: Record<string, string> = {};
    for (const s of timeline.scenes) {
      try { engine.renderOrbit(ctx, bundle, s.start + Math.min(s.duration * 0.4, 6), { view: FLAT, bubbles: true }); sc.drawImage(cv, 0, 0, 320, 180); out[s.id] = small.toDataURL('image/jpeg', 0.8); } catch { /* no thumb */ }
    }
    setThumbs(out);
  }, [engine, bundle, timeline]);

  const undo = useCallback(async () => {
    if (!sid) return; try { const r = await api.undo(sid); toast({ kind: r.undone ? 'ok' : 'info', text: r.undone ? `Undid: ${r.undone.label}` : 'Nothing to undo' }); } catch (e) { fail(e); }
  }, [sid, toast, fail]);
  const redo = useCallback(async () => {
    if (!sid) return; try { const r = await api.redo(sid); toast({ kind: r.redone ? 'ok' : 'info', text: r.redone ? `Redid: ${r.redone.label}` : 'Nothing to redo' }); } catch (e) { fail(e); }
  }, [sid, toast, fail]);

  const value = useMemo<Studio>(() => ({
    sid, seriesList, series, bundle, engine, scope, setScope, clock, view, setSid: s => { setSidState(s); setScope({}); },
    toasts, toast, dismissToast, loading, error, recordings, refreshRecordings, undo, redo, sceneStart, sceneThumbs,
  }), [sid, seriesList, series, bundle, engine, scope, clock, view, toasts, toast, dismissToast, loading, error, recordings, refreshRecordings, undo, redo, sceneStart, sceneThumbs]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
