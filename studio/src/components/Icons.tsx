// One icon family: 24px grid, 1.6px stroke, round caps/joins, currentColor. Drawn here, no third-party icon packs.
import type { ReactElement, SVGProps } from 'react';

const paths = {
  play: <path d="M8 5.5v13l11-6.5z" />,
  pause: <><path d="M8 5.5v13" /><path d="M16 5.5v13" /></>,
  loop: <><path d="M4 11V9a3 3 0 0 1 3-3h11" /><path d="m15 3 3 3-3 3" /><path d="M20 13v2a3 3 0 0 1-3 3H6" /><path d="m9 21-3-3 3-3" /></>,
  undo: <><path d="M9 7 4 12l5 5" /><path d="M4 12h10a6 6 0 0 1 0 12" transform="translate(0 -5)" /></>,
  redo: <><path d="m15 7 5 5-5 5" /><path d="M20 12H10a6 6 0 0 0 0 12" transform="translate(0 -5)" /></>,
  search: <><circle cx="11" cy="11" r="6" /><path d="m20 20-4.2-4.2" /></>,
  spark: <><path d="M12 3v5" /><path d="M12 16v5" /><path d="M3 12h5" /><path d="M16 12h5" /><path d="m6.3 6.3 2.8 2.8" /><path d="m14.9 14.9 2.8 2.8" /></>,
  film: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 4v16" /><path d="M16 4v16" /><path d="M4 9h4" /><path d="M4 15h4" /><path d="M16 9h4" /><path d="M16 15h4" /></>,
  scene: <><rect x="3.5" y="5.5" width="17" height="13" rx="2" /><path d="m3.5 15 4.5-4 4 3.5 3-2.5 5.5 4.5" /></>,
  user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.7-3.6 3.4-5.5 7-5.5s6.3 1.9 7 5.5" /></>,
  download: <><path d="M12 4v11" /><path d="m7 11 5 5 5-5" /><path d="M5 20h14" /></>,
  sun: <><circle cx="12" cy="12" r="4" /><path d="M12 3v2M12 19v2M3 12h2M19 12h2M5.6 5.6 7 7M17 17l1.4 1.4M5.6 18.4 7 17M17 7l1.4-1.4" /></>,
  moon: <path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z" />,
  grid: <><path d="M9 4v16" /><path d="M15 4v16" /><path d="M4 9h16" /><path d="M4 15h16" /></>,
  frame: <><rect x="4" y="4" width="16" height="16" rx="1.5" strokeDasharray="3 3" /><rect x="8" y="8" width="8" height="8" rx="1" /></>,
  send: <><path d="M4 12 20 4l-4 16-4.5-6.5z" /><path d="m11.5 13.5 4-4" /></>,
  lock: <><rect x="5.5" y="11" width="13" height="9" rx="2" /><path d="M8.5 11V8a3.5 3.5 0 0 1 7 0v3" /></>,
  check: <path d="m5 12.5 4.5 4.5L19 7.5" />,
  alert: <><path d="M12 4 3 19.5h18z" /><path d="M12 10v4.5" /><path d="M12 17.2v.01" /></>,
  x: <><path d="m6 6 12 12" /><path d="m18 6-12 12" /></>,
  chevron: <path d="m9 6 6 6-6 6" />,
  command: <><path d="M9 9h6v6H9z" /><path d="M9 9V7a2 2 0 1 0-2 2h2" /><path d="M15 9V7a2 2 0 1 1 2 2h-2" /><path d="M9 15v2a2 2 0 1 1-2-2h2" /><path d="M15 15v2a2 2 0 1 0 2-2h-2" /></>,
  ink: <><path d="M5 19c2-8 5-12 14-13-1 8-5 12-14 13z" /><path d="m5 19 8-8" /></>,
} satisfies Record<string, ReactElement>;

export type IconName = keyof typeof paths;

export function Icon({ name, ...rest }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      {paths[name]}
    </svg>
  );
}
