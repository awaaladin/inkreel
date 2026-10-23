import { useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { useClock, useStudio } from '../state';
import { Icon } from './Icon';

const fmt = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`;

export function Transport() {
  const { clock, bundle, engine } = useStudio();
  const { t, playing, loop, a, b } = useClock();
  const len = Math.max(0, b - a), rel = Math.min(len, Math.max(0, t - a));
  const [drag, setDrag] = useState(false);
  const track = useRef<HTMLDivElement>(null);
  const marks = bundle && engine ? engine.timeline(bundle).scenes.map(s => s.start).filter(s => s > a + 0.01 && s < b - 0.01).map(s => (s - a) / (len || 1)) : [];

  const seek = (x: number) => { const r = track.current!.getBoundingClientRect(); clock.t = a + Math.min(1, Math.max(0, (x - r.left) / r.width)) * len; clock.emit(); };
  const down = (e: PointerEvent<HTMLDivElement>) => { e.currentTarget.setPointerCapture(e.pointerId); setDrag(true); clock.playing = false; seek(e.clientX); };
  const key = (e: KeyboardEvent) => {
    const step = e.shiftKey ? 1 : 1 / 24;
    if (e.key === 'ArrowRight') { clock.t = Math.min(b, clock.t + step); clock.emit(); e.preventDefault(); }
    if (e.key === 'ArrowLeft') { clock.t = Math.max(a, clock.t - step); clock.emit(); e.preventDefault(); }
  };
  const toggle = () => { if (!playing && clock.t >= b - 0.05) clock.t = a; clock.playing = !playing; clock.emit(); };

  return (
    <div className="transport" role="group" aria-label="Playback">
      <button className="play" onClick={toggle} disabled={!len} aria-label={playing ? 'Pause' : 'Play'}><Icon name={playing ? 'pause' : 'play'} /></button>
      <button className={`tool icon ${loop ? 'on' : ''}`} onClick={() => { clock.loop = !loop; clock.emit(); }} aria-pressed={loop} aria-label="Loop" title="Loop"><Icon name="loop" /></button>
      <div className={`scrub ${drag ? 'drag' : ''}`} onPointerDown={down} onPointerMove={e => drag && seek(e.clientX)} onPointerUp={() => setDrag(false)} onPointerCancel={() => setDrag(false)}
        role="slider" tabIndex={0} aria-label="Position" aria-valuemin={0} aria-valuemax={Math.round(len * 10) / 10} aria-valuenow={Math.round(rel * 10) / 10} onKeyDown={key}>
        <div className="scrub-track" ref={track}>
          <div className="scrub-fill" style={{ width: `${len ? (rel / len) * 100 : 0}%` }} />
          {marks.map((m, i) => <span key={i} className="scrub-mark" style={{ left: `${m * 100}%` }} />)}
          <div className="scrub-knob" style={{ left: `${len ? (rel / len) * 100 : 0}%` }} />
        </div>
      </div>
      <span className="clock">{fmt(rel)} / {fmt(len)}</span>
      <select className="speed" aria-label="Speed" defaultValue="1" onChange={e => { clock.speed = Number(e.target.value); }}>
        {[0.25, 0.5, 1, 2].map(s => <option key={s} value={s}>{s}x</option>)}
      </select>
    </div>
  );
}
