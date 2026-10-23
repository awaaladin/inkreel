// One icon family: 24px grid, 1.6px stroke, round caps. Drawn here; no icon packs.
import type { ReactElement, SVGProps } from 'react';

const paths = {
  play: <path d="M8 5.5v13l11-6.5z" />,
  pause: <><path d="M8 5.5v13" /><path d="M16 5.5v13" /></>,
  loop: <><path d="M4 11V9a3 3 0 0 1 3-3h11" /><path d="m15 3 3 3-3 3" /><path d="M20 13v2a3 3 0 0 1-3 3H6" /><path d="m9 21-3-3 3-3" /></>,
  undo: <><path d="M9 7 4 12l5 5" /><path d="M4 12h9a6 6 0 0 1 0 8" /></>,
  redo: <><path d="m15 7 5 5-5 5" /><path d="M20 12h-9a6 6 0 0 0 0 8" /></>,
  record: <circle cx="12" cy="12" r="6" />,
  stop: <rect x="7" y="7" width="10" height="10" rx="1.5" />,
  orbit: <><ellipse cx="12" cy="12" rx="9" ry="4" /><circle cx="12" cy="12" r="2" /><path d="M17.5 8.3 20 6" /></>,
  cube: <><path d="M12 3 4 7.5v9L12 21l8-4.5v-9z" /><path d="M4 7.5 12 12l8-4.5" /><path d="M12 12v9" /></>,
  reset: <><path d="M4 12a8 8 0 1 0 3-6.2" /><path d="M4 4v5h5" /></>,
  film: <><rect x="4" y="4" width="16" height="16" rx="2" /><path d="M8 4v16M16 4v16M4 9h4M4 15h4M16 9h4M16 15h4" /></>,
  scene: <><rect x="3.5" y="5.5" width="17" height="13" rx="2" /><path d="m3.5 15 4.5-4 4 3.5 3-2.5 5.5 4.5" /></>,
  user: <><circle cx="12" cy="8" r="3.5" /><path d="M5 20c.7-3.6 3.4-5.5 7-5.5s6.3 1.9 7 5.5" /></>,
  folder: <path d="M3.5 7.5a2 2 0 0 1 2-2H10l2 2.5h6.5a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2z" />,
  chevron: <path d="m9 6 6 6-6 6" />,
  alert: <><path d="M12 4 3 19.5h18z" /><path d="M12 10v4.5" /><path d="M12 17.2v.01" /></>,
  x: <><path d="m6 6 12 12" /><path d="m18 6-12 12" /></>,
  ink: <><path d="M5 19c2-8 5-12 14-13-1 8-5 12-14 13z" /><path d="m5 19 8-8" /></>,
  download: <><path d="M12 4v11" /><path d="m7 11 5 5 5-5" /><path d="M5 20h14" /></>,
} satisfies Record<string, ReactElement>;

export type IconName = keyof typeof paths;

export function Icon({ name, ...rest }: { name: IconName } & SVGProps<SVGSVGElement>) {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6} strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" {...rest}>
      {paths[name]}
    </svg>
  );
}
