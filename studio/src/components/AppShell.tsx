import { useEffect } from 'react';
import { useStudio } from '../state';
import { Button } from './Button';
import { CommandPalette } from './CommandPalette';
import { DirectorPanel } from './DirectorPanel';
import { EpisodeBoard } from './EpisodeBoard';
import { Icon } from './Icons';
import { SeriesTree } from './SeriesTree';
import { Stage } from './Stage';
import { Toasts } from './Toasts';
import { TransportBar } from './TransportBar';

function WorkspaceSwitcher() {
  const { sid, seriesList, setSid, series } = useStudio();
  if (seriesList.length <= 1) return <span style={{ color: 'var(--c-text-dim)', fontSize: 'var(--t-sm)' }}>{series?.series.title ?? sid ?? 'No series'}</span>;
  return (
    <select aria-label="Series" value={sid ?? ''} onChange={e => setSid(e.target.value)} className="btn" style={{ paddingRight: 8 }}>
      {seriesList.map(s => <option key={s} value={s}>{s}</option>)}
    </select>
  );
}

export function AppShell() {
  const s = useStudio();
  const { clock, scope, series, connection, theme } = s;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement; const typing = el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.tagName === 'SELECT' || el.isContentEditable;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') { e.preventDefault(); s.setPaletteOpen(!s.paletteOpen); return; }
      if (typing) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); void (e.shiftKey ? s.redo() : s.undo()); }
      else if (e.code === 'Space') { e.preventDefault(); clock.playing = !clock.playing; clock.emit(); }
      else if (e.key.toLowerCase() === 'l') { clock.loop = !clock.loop; clock.emit(); }
    };
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey);
  }, [s, clock]);

  const ep = series?.episodes.find(e => e.id === scope.episode); const sc = ep?.scene_info.find(x => x.id === scope.scene);
  return (
    <div className="shell">
      <header className="topbar">
        <div className="brand"><Icon name="ink" /> Inkreel</div>
        <WorkspaceSwitcher />
        <span style={{ color: 'var(--c-text-faint)' }}>/</span>
        <span style={{ fontSize: 'var(--t-sm)' }}>{sc ? sc.name : ep ? `Episode ${ep.number}` : 'Whole series'}</span>
        <div className="spacer" />
        <span className={`chip ${connection}`} role="status"><i />{connection === 'live' ? 'Live' : connection === 'reconnecting' ? 'Reconnecting' : 'Offline'}</span>
        <Button icon="undo" iconOnly variant="ghost" tip="Undo (Ctrl Z)" aria-label="Undo" onClick={() => void s.undo()} />
        <Button icon="redo" iconOnly variant="ghost" tip="Redo" aria-label="Redo" onClick={() => void s.redo()} />
        <Button icon="download" onClick={() => void s.exportScope()}>Export</Button>
        <Button icon="command" onClick={() => s.setPaletteOpen(true)} aria-label="Open command palette">Ctrl K</Button>
        <Button icon={theme === 'dark' ? 'sun' : 'moon'} iconOnly variant="ghost" tip="Theme" aria-label="Switch theme" onClick={s.toggleTheme} />
      </header>
      <aside className="side"><SeriesTree /></aside>
      <main className="main">
        <Stage />
        <TransportBar />
        <EpisodeBoard />
      </main>
      <DirectorPanel />
      <CommandPalette />
      <Toasts />
    </div>
  );
}
