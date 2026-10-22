import { useRef, useState, type FormEvent, type KeyboardEvent } from 'react';
import { useStudio } from '../state';
import { Button } from './Button';
import { Icon } from './Icons';

const KIND_LABEL: Record<string, string> = { ai: 'Director', user: 'You', import: 'Import', history: 'History', error: 'Error', system: 'System' };

/** Mirror of everything that changes the series (director, terminal, studio) plus the prompt box. aria-live so screen readers hear director output. */
export function DirectorPanel() {
  const { log, sid, toast } = useStudio();
  const [text, setText] = useState(''); const [busy, setBusy] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);

  const submit = async (e?: FormEvent) => {
    e?.preventDefault(); const t = text.trim(); if (!t || !sid || busy) return;
    setBusy(true);
    try {
      const r = await fetch(`/api/series/${sid}/chat`, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ text: t }) });
      if (!r.ok) { const b = await r.json().catch(() => ({})); throw Object.assign(new Error(b.detail?.error ?? `${r.status}`), { hint: b.detail?.hint }); }
      setText('');
    } catch (err) { const x = err as Error & { hint?: string }; toast({ kind: 'error', text: x.message, hint: x.hint }); } finally { setBusy(false); }
  };
  const onKey = (e: KeyboardEvent) => { if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); void submit(); } };

  return (
    <aside className="dir" aria-label="Director">
      <div className="dir-head"><Icon name="spark" width={18} height={18} style={{ color: 'var(--c-teal)' }} /><h3 style={{ fontSize: 'var(--t-lg)' }}>Director</h3></div>
      <div className="dir-log" role="log" aria-live="polite" aria-relevant="additions">
        {log.length === 0 && <div className="empty"><b>Quiet on set</b>Edits from the terminal, the director and this studio show up here as they happen.</div>}
        {log.map(l => <div key={l.id} className={`log-row ${l.kind}`}><small>{KIND_LABEL[l.kind]}{l.sub ? ` · ${l.sub}` : ''}</small>{l.text}</div>)}
      </div>
      <form className="dir-input" onSubmit={submit}>
        <textarea ref={area} value={text} onChange={e => setText(e.target.value)} onKeyDown={onKey} placeholder="Describe a scene, or ask for a change…" aria-label="Message to the director" disabled={!sid} />
        <Button type="submit" variant="primary" icon="send" iconOnly aria-label="Send" tip="Send (Enter)" disabled={!text.trim() || busy} />
      </form>
    </aside>
  );
}
