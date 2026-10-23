import { useStudio } from '../state';
import { Icon } from './Icon';

/** Left rail: the real structure of the series (episodes, scenes), the cast, and saved recordings. Nothing placeholder. */
export function Library() {
  const { series, scope, setScope, sceneThumbs, recordings, loading } = useStudio();
  if (loading || !series) return <nav className="lib" aria-busy="true">{[1, 2, 3, 4].map(i => <div key={i} className="skeleton" style={{ height: 44, margin: '10px 0', borderRadius: 8 }} />)}</nav>;
  const chars = Object.values(series.characters);
  return (
    <nav className="lib" aria-label="Series">
      <button className={`row all ${!scope.episode && !scope.scene ? 'on' : ''}`} onClick={() => setScope({})}>
        <Icon name="film" /> <b>{series.series.title}</b><span className="dim">{series.episodes.reduce((a, e) => a + e.duration, 0).toFixed(0)}s</span>
      </button>
      {series.episodes.map(ep => (
        <div key={ep.id} className="group">
          <button className={`row ep ${scope.episode === ep.id && !scope.scene ? 'on' : ''}`} onClick={() => setScope({ episode: ep.id })}>
            <Icon name="folder" /> <span>Ep {ep.number} · {ep.title}</span><span className="dim">{ep.duration.toFixed(0)}s</span>
          </button>
          {ep.scene_info.map(s => (
            <button key={s.id} className={`scene ${scope.scene === s.id ? 'on' : ''}`} onClick={() => setScope({ episode: ep.id, scene: s.id })}>
              {sceneThumbs[s.id] ? <img src={sceneThumbs[s.id]} alt="" /> : <span className="thumb-ph skeleton" />}
              <span className="meta"><b>{s.name}</b><small>{s.duration.toFixed(1)}s · {s.cast.join(', ') || 'no cast'}</small></span>
            </button>
          ))}
        </div>
      ))}
      <h4>Characters</h4>
      {chars.length === 0 && <p className="none">No characters yet.</p>}
      {chars.map(c => (
        <div key={c.id} className="row static">
          <span className="swatches" aria-hidden="true">{[c.skin, c.top, c.bottom, c.hair].map((col, i) => <i key={i} style={{ background: col }} />)}</span>
          <span>{c.name}</span><span className="dim">{c.height}px</span>
        </div>
      ))}
      <h4>Recordings</h4>
      {recordings.length === 0 && <p className="none">Press Record to save a video of the stage.</p>}
      {recordings.slice(0, 8).map(r => (
        <a key={r.file} className="row rec-row" href={r.url} target="_blank" rel="noreferrer" download><Icon name="download" /> <span>{r.file}</span><span className="dim">{r.mb} MB</span></a>
      ))}
    </nav>
  );
}
