import { useEffect, useRef } from 'react';
import { useStudio } from '../state';
import { engineOpts, quantize } from '../lib/engine';
import { Icon } from './Icons';

/** Canvas host for the animation engine. Draws on every animation frame; advances the shared clock while playing. */
export function Stage() {
  const { bundle, engine, clock, overlays, loading, error } = useStudio();
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const cv = ref.current; if (!cv || !bundle || !engine || !bundle.scenes.length) return;
    const ctx = cv.getContext('2d'); if (!ctx) return;
    const opts = engineOpts(bundle); const W = engine.VW, H = engine.VH; cv.width = W; cv.height = H;
    let raf = 0, last = performance.now(), lastDrawn = -1;
    const frame = (now: number) => {
      raf = requestAnimationFrame(frame);
      const dt = Math.min(0.1, (now - last) / 1000); last = now;
      if (clock.playing) {
        clock.t += dt * clock.speed;
        if (clock.t >= clock.total) { if (clock.loop) clock.t = 0; else { clock.t = Math.max(0, clock.total - 1e-3); clock.playing = false; } }
        clock.emit();
      }
      const T = quantize(clock.t, bundle);
      if (T === lastDrawn && !clock.playing) return;
      lastDrawn = T;
      ctx.save();
      try { engine.renderProject(ctx, bundle, T, opts); } catch (e) { console.error('render failed', e); }
      ctx.restore();
    };
    raf = requestAnimationFrame(frame);
    // redraw when paused and the clock is scrubbed
    const unsub = clock.subscribe(() => { lastDrawn = -1; });
    return () => { cancelAnimationFrame(raf); unsub(); };
  }, [bundle, engine, clock]);

  const empty = !!bundle && !bundle.scenes.length;
  return (
    <div className="stage-wrap" role="img" aria-label="Animation stage">
      <canvas ref={ref} width={1280} height={720} />
      {overlays.thirds && <div className="overlay thirds" />}
      {overlays.safe && <div className="overlay safe" />}
      {(!bundle || !engine) && !error && <div className="stage-state skeleton" aria-busy="true"><span>{loading ? 'Opening workspace' : 'Loading the engine'}</span></div>}
      {empty && <div className="stage-state"><div><Icon name="film" width={28} height={28} /><p>No scenes here yet.<br />Ask the director, or run <kbd>/op create_scene</kbd>.</p></div></div>}
      {error && !bundle && <div className="stage-state"><div><Icon name="alert" width={28} height={28} /><p>{error.message}<br /><small>{error.hint}</small></p></div></div>}
    </div>
  );
}
