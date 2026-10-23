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
const loadScript = (src: string) => new Promise<void>((res, rej) => {
  const s = document.createElement('script'); s.src = src; s.onload = () => res(); s.onerror = () => rej(new Error(`failed to load ${src}`)); document.head.appendChild(s);
});

export function loadEngine(): Promise<InkreelNS> {
  if (ready) return ready;
  ready = (async () => {
    for (const f of ['core', 'draw', 'parts', 'world', 'engine', 'orbit']) await loadScript(`/engine/${f}.js?v=3`);
    const lib = await (await fetch('/api/library')).json();
    const NS = window.Inkreel!; NS.setLibrary({ stances: lib.stances, emotions: lib.emotions, actions: lib.actions });
    const faces: [string, string][] = [['Patrick Hand', '/engine/fonts/patrick-hand-latin-400-normal.woff2'], ['Bangers', '/engine/fonts/bangers-latin-400-normal.woff2']];
    await Promise.all(faces.map(async ([fam, url]) => { try { const f = new FontFace(fam, `url(${url})`); await f.load(); document.fonts.add(f); } catch { /* system font fallback */ } }));
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
