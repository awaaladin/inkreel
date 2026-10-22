// Loads the (prototype) JS drawing engine served at /engine and exposes a typed render function.
// Phase 3 replaces this module with the Rust/WASM build behind the same interface.
import type { Bundle } from './api';

export interface InkreelNS {
  VW: number; VH: number;
  setLibrary(l: unknown): void;
  timeline(p: unknown): { scenes: { id: string; start: number; duration: number }[]; total: number };
  renderProject(ctx: CanvasRenderingContext2D, p: unknown, T: number, opts: Record<string, unknown>): { index: number } | null;
}
declare global { interface Window { Inkreel?: InkreelNS } }

let ready: Promise<InkreelNS> | null = null;
const loadScript = (src: string) => new Promise<void>((res, rej) => {
  const s = document.createElement('script'); s.src = src; s.onload = () => res(); s.onerror = () => rej(new Error(`failed to load ${src}`)); document.head.appendChild(s);
});

export function loadEngine(): Promise<InkreelNS> {
  if (ready) return ready;
  ready = (async () => {
    for (const f of ['core', 'draw', 'world', 'engine']) await loadScript(`/engine/${f}.js`);
    const lib = await (await fetch('/api/library')).json();
    const NS = window.Inkreel!; NS.setLibrary({ stances: lib.stances, emotions: lib.emotions, actions: lib.actions });
    const faces: [string, string][] = [['Patrick Hand', '/engine/fonts/patrick-hand-latin-400-normal.woff2'], ['Bangers', '/engine/fonts/bangers-latin-400-normal.woff2']];
    await Promise.all(faces.map(async ([fam, url]) => { try { const f = new FontFace(fam, `url(${url})`); await f.load(); document.fonts.add(f); } catch { /* falls back to a system font */ } }));
    return NS;
  })();
  ready.catch(() => { ready = null; });
  return ready;
}

export function engineOpts(b: Bundle): Record<string, unknown> {
  const st = b.style;
  return {
    createCanvas: (w: number, h: number) => { const c = document.createElement('canvas'); c.width = w; c.height = h; return c; },
    boilFps: st.boil_fps ?? 12, wobble: st.wobble ?? 1, grain: st.grain ?? 0.05, vignette: st.vignette ?? 0.16, handheld: st.handheld ?? 1,
  };
}

export function quantize(T: number, b: Bundle): number {
  const st = b.style;
  const f = Number(st.twos_fps ?? 12);
  return st.animate_on === 'twos' ? Math.floor(T * f + 1e-6) / f : T;
}
