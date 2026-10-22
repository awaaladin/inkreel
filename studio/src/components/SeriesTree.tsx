import { useStudio } from '../state';
import { Icon } from './Icons';

export function SeriesTree() {
  const { series, scope, setScope, loading } = useStudio();
  if (loading || !series) return <nav className="tree" aria-label="Series" aria-busy={loading}>{[1, 2, 3, 4, 5].map(i => <div key={i} className="skeleton" style={{ height: 28, margin: '8px 4px', borderRadius: 6 }} />)}</nav>;
  return (
    <nav className="tree" aria-label="Series">
      <button className="tree-item" aria-current={!scope.episode && !scope.scene} onClick={() => setScope({})}>
        <Icon name="film" width={16} height={16} /> <b>{series.series.title}</b><span className="dim num">{series.episodes.reduce((a, e) => a + e.duration, 0).toFixed(0)}s</span>
      </button>
      <h4>Episodes</h4>
      {series.episodes.map(ep => (
        <div key={ep.id}>
          <button className="tree-item" aria-current={scope.episode === ep.id && !scope.scene} onClick={() => setScope({ episode: ep.id })}>
            <Icon name="chevron" width={14} height={14} style={{ transform: scope.episode === ep.id ? 'rotate(90deg)' : undefined, transition: 'transform var(--d-fast)' }} />
            Ep {ep.number} <span style={{ color: 'var(--c-text-faint)' }}>{ep.title}</span><span className="dim num">{ep.duration.toFixed(0)}s</span>
          </button>
          {scope.episode === ep.id && (
            <div className="tree-sub">
              {ep.scene_info.map(s => (
                <button key={s.id} className="tree-item" aria-current={scope.scene === s.id} onClick={() => setScope({ episode: ep.id, scene: s.id })}>
                  <Icon name="scene" width={15} height={15} /> {s.name}<span className="dim num">{s.duration.toFixed(0)}s</span>
                </button>
              ))}
            </div>
          )}
        </div>
      ))}
      <h4>Cast</h4>
      {Object.values(series.characters).map(c => (
        <div key={c.id} className="tree-item" style={{ cursor: 'default' }}>
          <span className="swatches" aria-hidden="true">{[c.skin, c.top, c.bottom, c.hair].map((col, i) => <i key={i} style={{ background: col }} />)}</span>
          <span>{c.name}</span><span className="dim">{c.height}px</span>
        </div>
      ))}
    </nav>
  );
}
