// Loads the drawing engine served at /engine and exposes the orbit renderer. Preview, orbit and recording all use this one path.
import type { Bundle } from './api';

export interface View { yaw: number; pitch: number; zoom: number; panX: number; panY: number }
export const FLAT: View = { yaw: 0, pitch: 0, zoom: 1, panX: 0, panY: 0 };

export interface InkreelNS {
  VW: number; VH: number;
  setLibrary(l: unknown): void;
  timeline(p: unknown): { scenes: { id: string; start: number; duration: number }[]; total: number };
  renderOrbit(ctx: CanvasRenderingContext2D, p: unknown, T: number, opts: Record<string, unknown>): { index: number } | null;
}
declare global { interface Window { Inkreel?: InkreelNS } }

let ready: Promise<InkreelNS> | null = null;
const FILES = ['core', 'draw', 'parts', 'world', 'engine', 'orbit'];

export function loadEngine(): Promise<InkreelNS> {
  if (ready) return ready;
  ready = (async () => {
    // fetch everything in parallel, then run the scripts in dependency order (they share one global namespace)
    const [lib, ...codes] = await Promise.all([
      fetch('/api/library').then(r => r.json()),
      ...FILES.map(f => fetch(`/engine/${f}.js`).then(r => { if (!r.ok) throw new Error(`failed to load engine file ${f}.js (${r.status})`); return r.text(); })),
    ]);
    for (const code of codes) { const s = document.createElement('script'); s.textContent = code; document.head.appendChild(s); s.remove(); }
    const NS = window.Inkreel!; NS.setLibrary({ stances: lib.stances, emotions: lib.emotions, actions: lib.actions });
    const faces: [string, string][] = [['Patrick Hand', '/engine/fonts/patrick-hand-latin-400-normal.woff2'], ['Bangers', '/engine/fonts/bangers-latin-400-normal.woff2']];
    const fonts = Promise.all(faces.map(async ([fam, url]) => { try { const f = new FontFace(fam, `url(${url})`); await f.load(); document.fonts.add(f); } catch { /* system font fallback */ } }));
    await Promise.race([fonts, new Promise(r => setTimeout(r, 2500))]);   // never let a slow font block the stage
    return NS;
  })();
  ready.catch(() => { ready = null; });
  return ready;
}

export function engineOpts(b: Bundle, view: View): Record<string, unknown> {
  const st = b.style;
  return { view, boilFps: st.boil_fps ?? 12, wobble: st.wobble ?? 1, vignette: st.vignette ?? 0.16, handheld: st.handheld ?? 1, onion: !!(window as unknown as { __onion?: boolean }).__onion };
}

export function quantize(T: number, b: Bundle): number {
  const f = Number(b.style.twos_fps ?? 12);
  return b.style.animate_on === 'twos' ? Math.floor(T * f + 1e-6) / f : T;
}
