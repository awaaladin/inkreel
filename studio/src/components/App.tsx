import { useEffect } from 'react';
import { useStudio } from '../state';
import { Icon } from './Icon';
import { Inspector } from './Inspector';
import { Library } from './Library';
import { Transport } from './Transport';
import { Viewport } from './Viewport';

export function App() {
  const s = useStudio();
  const { clock, scope, series, toasts, dismissToast, seriesList, sid, setSid } = s;

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement; if (['INPUT', 'TEXTAREA', 'SELECT'].includes(el.tagName) || el.isContentEditable) return;
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'z') { e.preventDefault(); void (e.shiftKey ? s.redo() : s.undo()); }
      else if (e.code === 'Space') { e.preventDefault(); clock.playing = !clock.playing; clock.emit(); }
      else if (e.key.toLowerCase() === 'l') { clock.loop = !clock.loop; clock.emit(); }
      else if (e.key === 'ArrowUp') s.view.glideTo({ pitch: Math.min(80, s.view.target.pitch + 10) });
      else if (e.key === 'ArrowDown') s.view.glideTo({ pitch: Math.max(-60, s.view.target.pitch - 10) });
    };
    window.addEventListener('keydown', onKey); return () => window.removeEventListener('keydown', onKey);
  }, [s, clock]);

  const ep = series?.episodes.find(e => e.id === scope.episode); const sc = ep?.scene_info.find(x => x.id === scope.scene);
  return (
    <div className="app">
      <header className="top">
        <div className="brand"><Icon name="ink" /> Inkreel</div>
        {seriesList.length > 1
          ? <select aria-label="Series" value={sid ?? ''} onChange={e => setSid(e.target.value)}>{seriesList.map(x => <option key={x}>{x}</option>)}</select>
          : <span className="crumb">{series?.series.title ?? ''}</span>}
        <span className="crumb dim">{sc ? `/ ${sc.name}` : ep ? `/ Episode ${ep.number}` : '/ Whole series'}</span>
        <div className="spacer" />
        <button className="tool icon" onClick={() => void s.undo()} aria-label="Undo" title="Undo (Ctrl Z)"><Icon name="undo" /></button>
        <button className="tool icon" onClick={() => void s.redo()} aria-label="Redo" title="Redo (Ctrl Shift Z)"><Icon name="redo" /></button>
      </header>
      <aside className="left"><Library /></aside>
      <main className="center">
        <Viewport />
        <Transport />
      </main>
      <div className="right"><Inspector /></div>
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map(t => (
          <div key={t.id} className={`toast ${t.kind}`} onClick={() => dismissToast(t.id)}>
            <b>{t.text}</b>{t.hint && <small>{t.hint}</small>}{t.href && <a href={t.href} target="_blank" rel="noreferrer" onClick={e => e.stopPropagation()}>Open video</a>}
          </div>
        ))}
      </div>
    </div>
  );
}
