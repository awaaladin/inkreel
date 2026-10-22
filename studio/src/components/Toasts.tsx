import { useStudio } from '../state';

export function Toasts() {
  const { toasts, dismissToast } = useStudio();
  return (
    <div className="toasts" role="status" aria-live="polite">
      {toasts.map(t => (
        <div key={t.id} className={`toast ${t.kind}`} onClick={() => dismissToast(t.id)}>
          {t.text}{t.hint && <small>{t.hint}</small>}
        </div>
      ))}
    </div>
  );
}
