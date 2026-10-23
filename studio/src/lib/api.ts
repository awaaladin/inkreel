// Typed client for the Inkreel server. Errors carry the server's hint so the UI can say how to fix them.
export interface ApiError extends Error { hint?: string; status: number }

async function req<T>(url: string, init?: RequestInit): Promise<T> {
  let r: Response;
  try { r = await fetch(url, init); } catch {
    const err = new Error('Cannot reach the Inkreel server') as ApiError; err.hint = 'Is `inkreel serve` still running?'; err.status = 0; throw err;
  }
  if (!r.ok) {
    let body: { detail?: { error?: string; hint?: string } } = {};
    try { body = await r.json(); } catch { /* not json */ }
    const err = new Error(body.detail?.error ?? `${r.status} ${r.statusText}`) as ApiError;
    err.hint = body.detail?.hint; err.status = r.status; throw err;
  }
  return r.json() as Promise<T>;
}

export interface SceneInfo { id: string; name: string; duration: number; background: { preset: string; time?: string }; cast: string[] }
export interface EpisodeInfo { id: string; title: string; number: number; synopsis: string; scenes: string[]; scene_info: SceneInfo[]; duration: number }
export interface CharacterRec { id: string; name: string; height?: number; skin?: string; top?: string; bottom?: string; hair?: string; weapon?: string }
export interface SeriesData { series: { id: string; title: string; episodes: string[] }; characters: Record<string, CharacterRec>; episodes: EpisodeInfo[]; rev: number }
export interface Ev { id: string; t: number; src: 'ai' | 'user' | 'import'; lock: boolean; [k: string]: unknown }
export interface SceneBundle { id: string; name?: string; actors: Record<string, { x: number; y: number; moves: Ev[]; actions: Ev[]; says: Ev[]; emotes: Ev[]; stances: Ev[]; faces: Ev[] }>; camera: Ev[]; fx: Ev[]; captions: Ev[]; duration?: number }
export interface Bundle { meta: { title: string; fps: number }; style: Record<string, number | string>; characters: Record<string, unknown>; scenes: SceneBundle[]; actions: Record<string, unknown> }
export interface OpResult { name: string; ok: boolean; message: string }
export interface Recording { file: string; url: string; mb: number }

const JSON_HDR = { 'Content-Type': 'application/json' };

export const api = {
  workspace: () => req<{ name: string; series: string[]; root: string }>('/api/workspace'),
  series: (sid: string) => req<SeriesData>(`/api/series/${sid}`),
  bundle: (sid: string, episode?: string, scene?: string) => {
    const q = new URLSearchParams(); if (episode) q.set('episode', episode); if (scene) q.set('scene', scene);
    return req<{ bundle: Bundle; rev: number }>(`/api/series/${sid}/bundle?${q}`);
  },
  library: () => req<{ actions: Record<string, unknown>; stances: Record<string, unknown>; emotions: Record<string, unknown> }>('/api/library'),
  ops: (sid: string, ops: { name: string; args: Record<string, unknown> }[], label = 'studio edit', episode?: string) =>
    req<{ results: OpResult[]; rev: number }>(`/api/series/${sid}/ops`, { method: 'POST', headers: JSON_HDR, body: JSON.stringify({ ops, src: 'user', label, episode }) }),
  undo: (sid: string) => req<{ undone: { label: string } | null }>(`/api/series/${sid}/undo`, { method: 'POST' }),
  redo: (sid: string) => req<{ redone: { label: string } | null }>(`/api/series/${sid}/redo`, { method: 'POST' }),
  saveRecording: (blob: Blob, name: string) =>
    req<{ file: string; url: string; mp4: boolean; note?: string; path?: string }>(`/api/recordings?name=${encodeURIComponent(name)}`, { method: 'POST', body: blob }),
  recordings: () => req<{ recordings: Recording[] }>('/api/recordings'),
};
