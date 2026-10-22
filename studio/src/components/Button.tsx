import { forwardRef, type ButtonHTMLAttributes, type PointerEvent } from 'react';
import { Icon, type IconName } from './Icons';

interface Props extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: IconName; variant?: 'default' | 'primary' | 'ghost' | 'danger'; tip?: string; iconOnly?: boolean;
}

/** Pointer-aware hover glow (follows the cursor), <100ms press feedback, animated focus ring (global.css). */
export const Button = forwardRef<HTMLButtonElement, Props>(function Button({ icon, variant = 'default', tip, iconOnly, className = '', children, onPointerMove, ...rest }, ref) {
  const move = (e: PointerEvent<HTMLButtonElement>) => {
    const r = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty('--mx', `${e.clientX - r.left}px`); e.currentTarget.style.setProperty('--my', `${e.clientY - r.top}px`);
    onPointerMove?.(e);
  };
  return (
    <button ref={ref} type="button" data-tip={tip} className={`btn ${variant === 'default' ? '' : variant} ${iconOnly ? 'icon' : ''} ${className}`} onPointerMove={move} {...rest}>
      {icon && <Icon name={icon} />}
      {children}
    </button>
  );
});
