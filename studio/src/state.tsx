// Studio state: server data, scope (what is on stage), playback clock, log, toasts. Playback time lives in an external store so
// the 60fps clock never re-renders the React tree.
import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';
import { api, type ApiError, type Bundle, type SeriesData, type StudioEvent } from './lib/api';
import { loadEngine, type InkreelNS } from './lib/engine';

export interface Scope { episode?: string; scene?: string }
export interface LogLine { id: number; kind: 'ai' | 'user' | 'import' | 'history' | 'error' | 'system'; text: string; sub?: string }
export interface Toast { id: number; kind: 'ok' | 'error' | 'info'; text: string; hint?: string }
export type Connection = 'live' | 'reconnecting' | 'offline';

// ---------------------------------------------------------------- clock (external store)
class Clock {
  t = 0; playing = false; loop = false; speed = 1; total = 0;
  private subs = new Set<() => void>();
  private snap = { t: 0, playing: false, loop: false, total: 0 };
  subscribe = (fn: () => void) => { this.subs.add(fn); return () => { this.subs.delete(fn); }; };
  getSnapshot = () => this.snap;
  emit() { this.snap = { t: this.t, playing: this.playing, loop: this.loop, total: this.total }; this.subs.forEach(f => f()); }
}

interface Studio {
  sid: string | null; series: SeriesData | null; bundle: Bundle | null; engine: InkreelNS | null; scope: Scope; setScope(s: Scope): void;
  clock: Clock; log: LogLine[]; toasts: Toast[]; toast(t: Omit<Toast, 'id'>): void; dismissToast(id: number): void;
  connection: Connection; loading: boolean; error: ApiError | null; theme: 'dark' | 'light'; toggleTheme(): void;
  paletteOpen: boolean; setPaletteOpen(v: boolean): void; overlays: { thirds: boolean; safe: boolean }; toggleOverlay(k: 'thirds' | 'safe'): void;
  undo(): Promise<void>; redo(): Promise<void>; exportScope(): Promise<void>; refresh(): Promise<void>; seriesList: string[]; setSid(s: string): void;
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
  const [log, setLog] = useState<LogLine[]>([]);
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [connection, setConnection] = useState<Connection>('reconnecting');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<ApiError | null>(null);
  const [theme, setTheme] = useState<'dark' | 'light'>(() => { try { return (localStorage.getItem('inkreel.theme') as 'dark' | 'light') || 'dark'; } catch { return 'dark'; } });
  const [paletteOpen, setPaletteOpen] = useState(false);
  const [overlays, setOverlays] = useState({ thirds: false, safe: false });
  const clock = useRef(new Clock()).current;
  const scopeRef = useRef(scope); scopeRef.current = scope;
  const sidRef = useRef(sid); sidRef.current = sid;

  useEffect(() => { document.documentElement.dataset.theme = theme; try { localStorage.setItem('inkreel.theme', theme); } catch { /* private mode */ } }, [theme]);

  const toast = useCallback((t: Omit<Toast, 'id'>) => {
    const id = nextId++; setToasts(x => [...x.slice(-3), { ...t, id }]);
    setTimeout(() => setToasts(x => x.filter(y => y.id !== id)), t.kind === 'error' ? 7000 : 3200);
  }, []);
  const dismissToast = useCallback((id: number) => setToasts(x => x.filter(y => y.id !== id)), []);
  const addLog = useCallback((l: Omit<LogLine, 'id'>) => setLog(x => [{ ...l, id: nextId++ }, ...x].slice(0, 120)), []);
  const fail = useCallback((e: unknown) => { const err = e as ApiError; setError(err); toast({ kind: 'error', text: err.message, hint: err.hint }); }, [toast]);

  // engine + workspace bootstrap
  useEffect(() => {
    loadEngine().then(setEngine).catch(e => fail(Object.assign(e, { status: 0, hint: 'The drawing engine failed to load from /engine.' })));
    api.workspace().then(w => { setSeriesList(w.series); setSidState(s => s ?? w.series[0] ?? null); setError(null); }).catch(fail).finally(() => setLoading(false));
  }, [fail]);

  const loadSeries = useCallback(async () => {
    const id = sidRef.current; if (!id) return;
    try { setSeries(await api.series(id)); setError(null); } catch (e) { fail(e); }
  }, [fail]);
  const loadBundle = useCallback(async () => {
    const id = sidRef.current; if (!id) return;
    try {
      const { bundle: b } = await api.bundle(id, scopeRef.current.episode, scopeRef.current.scene);
      setBundle(b);
    } catch (e) { fail(e); }
  }, [fail]);

  useEffect(() => { setSeries(null); void loadSeries(); }, [sid, loadSeries]);
  useEffect(() => { void loadBundle(); }, [sid, scope, loadBundle]);

  // total duration -> clock
  useEffect(() => {
    if (!bundle || !engine) { clock.total = 0; clock.emit(); return; }
    clock.total = bundle.scenes.length ? engine.timeline(bundle).total : 0;
    if (clock.t > clock.total) clock.t = 0;
    clock.emit();
  }, [bundle, engine, clock]);
  useEffect(() => { clock.t = 0; clock.playing = false; clock.emit(); }, [scope, sid, clock]);

  // live sync (SSE with reconnect)
  useEffect(() => {
    const es = new EventSource('/api/events'); let timer = 0;
    es.onopen = () => setConnection('live');
    es.onerror = () => setConnection(es.readyState === EventSource.CLOSED ? 'offline' : 'reconnecting');
    es.onmessage = m => {
      const ev = JSON.parse(m.data) as StudioEvent;
      if (ev.type === 'changed' && ev.series === sidRef.current) {
        const src = (ev.src as string) || 'system';
        addLog({ kind: src === 'ai' || src === 'user' || src === 'import' ? src : 'history', text: String(ev.label ?? 'change'), sub: `${(ev.scenes ?? []).join(', ') || 'series'} · rev ${ev.rev}` });
        clearTimeout(timer); timer = window.setTimeout(() => { void loadSeries(); void loadBundle(); }, 120);
      } else if (ev.type === 'cmd' && (ev as { action?: string }).action === 'play') { clock.playing = true; clock.t = 0; clock.emit(); }
    };
    return () => { es.close(); clearTimeout(timer); };
  }, [addLog, loadSeries, loadBundle, clock]);

  const undo = useCallback(async () => {
    if (!sid) return; try { const r = await api.undo(sid); toast({ kind: r.undone ? 'ok' : 'info', text: r.undone ? `Undid: ${r.undone.label}` : 'Nothing to undo' }); } catch (e) { fail(e); }
  }, [sid, toast, fail]);
  const redo = useCallback(async () => {
    if (!sid) return; try { const r = await api.redo(sid); toast({ kind: r.redone ? 'ok' : 'info', text: r.redone ? `Redid: ${r.redone.label}` : 'Nothing to redo' }); } catch (e) { fail(e); }
  }, [sid, toast, fail]);
  const exportScope = useCallback(async () => {
    if (!sid) return; try { await api.exportVideo(sid, { episode: scope.episode, scene: scope.scene }); toast({ kind: 'ok', text: 'Export started', hint: 'Progress appears in the render queue.' }); } catch (e) { fail(e); }
  }, [sid, scope, toast, fail]);

  const value = useMemo<Studio>(() => ({
    sid, series, bundle, engine, scope, setScope, clock, log, toasts, toast, dismissToast, connection, loading, error, theme,
    toggleTheme: () => setTheme(t => (t === 'dark' ? 'light' : 'dark')), paletteOpen, setPaletteOpen, overlays,
    toggleOverlay: k => setOverlays(o => ({ ...o, [k]: !o[k] })), undo, redo, exportScope, refresh: async () => { await loadSeries(); await loadBundle(); },
    seriesList, setSid: s => { setSidState(s); setScope({}); },
  }), [sid, series, bundle, engine, scope, clock, log, toasts, toast, dismissToast, connection, loading, error, theme, paletteOpen, overlays, undo, redo, exportScope, loadSeries, loadBundle, seriesList]);

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}
