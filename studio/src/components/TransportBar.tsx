import { useCallback, useRef, useState, type KeyboardEvent, type PointerEvent } from 'react';
import { useClock, useStudio } from '../state';
import { Button } from './Button';

const fmt = (s: number) => `${Math.floor(s / 60)}:${(s % 60).toFixed(1).padStart(4, '0')}`;

export function TransportBar() {
  const { clock, bundle, engine, overlays, toggleOverlay } = useStudio();
  const { t, playing, loop, total } = useClock();
  const [drag, setDrag] = useState(false);
  const track = useRef<HTMLDivElement>(null);
  const marks = bundle && engine && bundle.scenes.length > 1 ? engine.timeline(bundle).scenes.slice(1).map(s => s.start / (total || 1)) : [];

  const seek = useCallback((x: number) => {
    const r = track.current!.getBoundingClientRect(); const p = Math.min(1, Math.max(0, (x - r.left) / r.width));
    clock.t = p * total; clock.emit();
  }, [clock, total]);
  const down = (e: PointerEvent<HTMLDivElement>) => { e.currentTarget.setPointerCapture(e.pointerId); setDrag(true); clock.playing = false; seek(e.clientX); };
  const key = (e: KeyboardEvent) => {
    const step = e.shiftKey ? 1 : 1 / 24;
    if (e.key === 'ArrowRight') { clock.t = Math.min(total, clock.t + step); clock.emit(); e.preventDefault(); }
    if (e.key === 'ArrowLeft') { clock.t = Math.max(0, clock.t - step); clock.emit(); e.preventDefault(); }
    if (e.key === 'Home') { clock.t = 0; clock.emit(); }
    if (e.key === 'End') { clock.t = total; clock.emit(); }
  };
  const toggle = () => { if (!playing && clock.t >= total - 0.05) clock.t = 0; clock.playing = !playing; clock.emit(); };
  const disabled = !total;

  return (
    <div className="transport" role="group" aria-label="Transport">
      <Button icon={playing ? 'pause' : 'play'} variant="primary" iconOnly tip={playing ? 'Pause (Space)' : 'Play (Space)'} aria-label={playing ? 'Pause' : 'Play'} onClick={toggle} disabled={disabled} />
      <Button icon="loop" iconOnly variant="ghost" tip="Loop (L)" aria-label="Loop" aria-pressed={loop} onClick={() => { clock.loop = !clock.loop; clock.emit(); }} />
      <div className={`scrub ${drag ? 'drag' : ''}`} onPointerDown={down} onPointerMove={e => drag && seek(e.clientX)} onPointerUp={() => setDrag(false)} onPointerCancel={() => setDrag(false)}
        role="slider" tabIndex={0} aria-label="Timeline position" aria-valuemin={0} aria-valuemax={Math.round(total * 10) / 10} aria-valuenow={Math.round(t * 10) / 10} aria-valuetext={`${fmt(t)} of ${fmt(total)}`} onKeyDown={key}>
        <div className="scrub-track" ref={track}>
          <div className="scrub-fill" style={{ width: `${total ? (t / total) * 100 : 0}%` }} />
          {marks.map((m, i) => <span key={i} className="scrub-mark" style={{ left: `${m * 100}%` }} />)}
          <div className="scrub-knob" style={{ left: `${total ? (t / total) * 100 : 0}%` }} />
        </div>
      </div>
      <span className="clock num" aria-live="off">{fmt(t)} / {fmt(total)}</span>
      <Button icon="grid" iconOnly variant="ghost" tip="Rule of thirds" aria-label="Rule of thirds overlay" aria-pressed={overlays.thirds} onClick={() => toggleOverlay('thirds')} />
      <Button icon="frame" iconOnly variant="ghost" tip="Safe area" aria-label="Safe area overlay" aria-pressed={overlays.safe} onClick={() => toggleOverlay('safe')} />
    </div>
  );
}
