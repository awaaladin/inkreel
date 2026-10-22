import { useStudio } from '../state';
import { api } from '../lib/api';

/** Scene cards for the selected episode (or every episode when none is selected). Thumbnails are server-rendered stills. */
export function EpisodeBoard() {
  const { series, scope, setScope, sid } = useStudio();
  if (!series || !sid) return null;
  const eps = series.episodes.filter(e => !scope.episode || e.id === scope.episode);
  return (
    <section className="board" aria-label="Episode board">
      {eps.map(ep => (
        <div key={ep.id} style={{ marginBottom: 'var(--s-5)' }}>
          <h3>Ep {ep.number} <span style={{ color: 'var(--c-text-dim)', fontWeight: 400 }}>{ep.title}</span></h3>
          <p className="sub">{ep.synopsis || `${ep.scene_info.length} scenes`} <span className="num">{ep.duration.toFixed(1)}s</span></p>
          {ep.scene_info.length === 0 && <div className="empty"><b>No scenes yet</b>Ask the director to build one.</div>}
          <div className="cards">
            {ep.scene_info.map((s, i) => (
              <button key={s.id} className="card" style={{ ['--i' as string]: i }} aria-current={scope.scene === s.id} onClick={() => setScope({ episode: ep.id, scene: s.id })}>
                <img className="thumb skeleton" loading="lazy" alt="" src={api.stillUrl(sid, s.id, Math.min(s.duration * 0.4, 6), series.rev)} onLoad={e => e.currentTarget.classList.remove('skeleton')} />
                <span className="dur num">{s.duration.toFixed(1)}s</span>
                <span className="meta"><b>{s.name}</b><span>{s.background.preset} / {s.background.time ?? 'day'} · {s.cast.join(', ') || 'no cast'}</span></span>
              </button>
            ))}
          </div>
        </div>
      ))}
    </section>
  );
}
