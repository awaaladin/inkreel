import { useEffect, useRef, useState } from 'react';
import { springs, type SpringName } from '../design/tokens';

export const prefersReducedMotion = () => typeof matchMedia !== 'undefined' && matchMedia('(prefers-reduced-motion: reduce)').matches;

/** Interruptible damped spring toward `target`. Retargeting mid-flight keeps the current velocity, so nothing ever blocks input.
 *  With prefers-reduced-motion the value snaps (callers fade opacity instead of moving). */
export function useSpring(target: number, name: SpringName = 'snappy'): number {
  const [v, setV] = useState(target);
  const st = useRef({ x: target, v: 0, target, raf: 0, last: 0 });
  useEffect(() => {
    const s = st.current; s.target = target;
    if (prefersReducedMotion()) { s.x = target; s.v = 0; setV(target); return; }
    const { stiffness: k, damping: c } = springs[name];
    const step = (now: number) => {
      const dt = Math.min(0.032, (now - s.last) / 1000 || 0.016); s.last = now;
      const a = -k * (s.x - s.target) - c * s.v; s.v += a * dt; s.x += s.v * dt;
      if (Math.abs(s.x - s.target) < 0.001 && Math.abs(s.v) < 0.001) { s.x = s.target; s.v = 0; setV(s.x); s.raf = 0; return; }
      setV(s.x); s.raf = requestAnimationFrame(step);
    };
    if (!s.raf) { s.last = performance.now(); s.raf = requestAnimationFrame(step); }
  }, [target, name]);
  useEffect(() => () => cancelAnimationFrame(st.current.raf), []);
  return v;
}
