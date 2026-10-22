import { useEffect, useMemo, useRef, useState } from 'react';
import { useStudio } from '../state';
import { Icon, type IconName } from './Icons';

interface Cmd { id: string; label: string; group: string; icon: IconName; run(): void; keys?: string }

export function CommandPalette() {
  const s = useStudio();
  const [q, setQ] = useState(''); const [sel, setSel] = useState(0); const input = useRef<HTMLInputElement>(null);
  const { paletteOpen, setPaletteOpen, clock } = s;

  const cmds = useMemo<Cmd[]>(() => {
    const out: Cmd[] = [
      { id: 'play', label: 'Play / pause', group: 'Playback', icon: 'play', keys: 'Space', run: () => { clock.playing = !clock.playing; clock.emit(); } },
      { id: 'loop', label: 'Toggle loop', group: 'Playback', icon: 'loop', keys: 'L', run: () => { clock.loop = !clock.loop; clock.emit(); } },
      { id: 'undo', label: 'Undo last change', group: 'Edit', icon: 'undo', keys: 'Ctrl Z', run: () => void s.undo() },
      { id: 'redo', label: 'Redo', group: 'Edit', icon: 'redo', keys: 'Ctrl Shift Z', run: () => void s.redo() },
      { id: 'export', label: `Export ${s.scope.scene ? 'scene' : s.scope.episode ? 'episode' : 'series'} as MP4`, group: 'Export', icon: 'download', run: () => void s.exportScope() },
      { id: 'theme', label: 'Switch light / dark theme', group: 'View', icon: s.theme === 'dark' ? 'sun' : 'moon', run: s.toggleTheme },
      { id: 'thirds', label: 'Toggle rule-of-thirds overlay', group: 'View', icon: 'grid', run: () => s.toggleOverlay('thirds') },
      { id: 'safe', label: 'Toggle safe-area overlay', group: 'View', icon: 'frame', run: () => s.toggleOverlay('safe') },
      { id: 'all', label: 'Show whole series', group: 'Go to', icon: 'film', run: () => s.setScope({}) },
    ];
    for (const ep of s.series?.episodes ?? []) {
      out.push({ id: `ep-${ep.id}`, label: `Episode ${ep.number}: ${ep.title}`, group: 'Go to', icon: 'film', run: () => s.setScope({ episode: ep.id }) });
      for (const sc of ep.scene_info) out.push({ id: `sc-${sc.id}`, label: `Scene: ${sc.name}`, group: 'Go to', icon: 'scene', run: () => s.setScope({ episode: ep.id, scene: sc.id }) });
    }
    for (const id of s.seriesList) if (id !== s.sid) out.push({ id: `sr-${id}`, label: `Switch series: ${id}`, group: 'Workspace', icon: 'ink', run: () => s.setSid(id) });
    return out;
  }, [s, clock]);

  const shown = useMemo(() => { const n = q.trim().toLowerCase(); return n ? cmds.filter(c => (c.label + ' ' + c.group).toLowerCase().includes(n)) : cmds; }, [cmds, q]);
  useEffect(() => { setSel(0); }, [q, paletteOpen]);
  useEffect(() => { if (paletteOpen) { setQ(''); setTimeout(() => input.current?.focus(), 0); } }, [paletteOpen]);

  if (!paletteOpen) return null;
  const run = (c?: Cmd) => { if (!c) return; setPaletteOpen(false); c.run(); };
  return (
    <div className="scrim" onMouseDown={e => { if (e.target === e.currentTarget) setPaletteOpen(false); }}>
      <div className="palette" role="dialog" aria-modal="true" aria-label="Command palette">
        <input ref={input} value={q} onChange={e => setQ(e.target.value)} placeholder="Type a command or scene name…" aria-label="Search commands" role="combobox" aria-expanded="true" aria-controls="palette-list"
          aria-activedescendant={shown[sel] ? `cmd-${shown[sel].id}` : undefined}
          onKeyDown={e => {
            if (e.key === 'ArrowDown') { e.preventDefault(); setSel(i => Math.min(shown.length - 1, i + 1)); }
            else if (e.key === 'ArrowUp') { e.preventDefault(); setSel(i => Math.max(0, i - 1)); }
            else if (e.key === 'Enter') run(shown[sel]);
            else if (e.key === 'Escape') setPaletteOpen(false);
          }} />
        <ul id="palette-list" role="listbox">
          {shown.length === 0 && <li aria-disabled="true" style={{ color: 'var(--c-text-dim)' }}>No matching command</li>}
          {shown.map((c, i) => (
            <li key={c.id} id={`cmd-${c.id}`} role="option" aria-selected={i === sel} onMouseEnter={() => setSel(i)} onClick={() => run(c)}>
              <Icon name={c.icon} width={18} height={18} /> {c.label}<span className="grp">{c.keys ? <kbd>{c.keys}</kbd> : c.group}</span>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
