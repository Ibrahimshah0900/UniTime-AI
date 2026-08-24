import { useEffect, useId, useRef, type ReactNode } from 'react'
import { AlertCircle, CheckCircle2, Inbox, LoaderCircle, X } from 'lucide-react'

export function PageHeader({ title, description, actions }: { title: string; description?: string; actions?: ReactNode }) {
  return <header className="page-header"><div><h1>{title}</h1>{description && <p>{description}</p>}</div>{actions && <div className="page-header__actions">{actions}</div>}</header>
}

export function Section({ title, description, actions, children, className = '' }: { title?: string; description?: string; actions?: ReactNode; children: ReactNode; className?: string }) {
  return <section className={`section ${className}`}><div className="section__heading">{(title || description) && <div>{title && <h2>{title}</h2>}{description && <p>{description}</p>}</div>}{actions && <div className="section__actions">{actions}</div>}</div>{children}</section>
}

export function Metric({ label, value, hint, tone = 'neutral' }: { label: string; value: ReactNode; hint?: string; tone?: string }) {
  return <article className={`metric metric--${tone}`}><span>{label}</span><strong>{value}</strong>{hint && <small>{hint}</small>}</article>
}

export function StatusBadge({ children, tone = 'neutral' }: { children: ReactNode; tone?: string }) {
  return <span className={`status status--${tone}`}>{children}</span>
}

export function EmptyState({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <div className="empty-state"><Inbox size={28}/><h3>{title}</h3>{description && <p>{description}</p>}{action}</div>
}

export function LoadingState({ label = 'Loading' }: { label?: string }) {
  return <div className="loading-state" role="status" aria-live="polite"><LoaderCircle className="spin" size={22}/><span>{label}…</span></div>
}

export function ErrorState({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="error-state" role="alert"><AlertCircle size={22}/><div><strong>Something needs attention</strong><p>{message}</p>{retry && <button className="btn btn--secondary" onClick={retry}>Try again</button>}</div></div>
}

export function SuccessNote({ children }: { children: ReactNode }) {
  return <div className="success-note" role="status" aria-live="polite"><CheckCircle2 size={18}/>{children}</div>
}

export function ErrorNote({ children }: { children: ReactNode }) {
  return <div className="form-error" role="alert"><AlertCircle size={17}/>{children}</div>
}

export function Pagination({ total, offset, limit, onChange, label = 'items' }: { total: number; offset: number; limit: number; onChange: (offset: number) => void; label?: string }) {
  if (total <= limit && offset === 0) return null
  const first = total === 0 ? 0 : offset + 1
  const last = Math.min(offset + limit, total)
  return <nav className="pagination" aria-label={`${label} pagination`}><span>Showing {first}–{last} of {total} {label}</span><div><button className="btn btn--secondary" disabled={offset === 0} onClick={() => onChange(Math.max(0, offset - limit))}>Previous</button><button className="btn btn--secondary" disabled={offset + limit >= total} onClick={() => onChange(offset + limit)}>Next</button></div></nav>
}

export function Modal({ title, children, onClose, wide = false }: { title: string; children: ReactNode; onClose: () => void; wide?: boolean }) {
  const dialogRef = useRef<HTMLDivElement>(null)
  const onCloseRef = useRef(onClose)
  const titleId = useId()

  useEffect(() => { onCloseRef.current = onClose }, [onClose])
  useEffect(() => {
    const previousFocus = document.activeElement instanceof HTMLElement ? document.activeElement : null
    const selector = 'button:not([disabled]), [href], input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
    const focusable = () => Array.from(dialogRef.current?.querySelectorAll<HTMLElement>(selector) || []).filter((item) => !item.hasAttribute('aria-hidden'))
    focusable()[0]?.focus()

    function handleKeyDown(event: KeyboardEvent) {
      if (event.key === 'Escape') {
        event.preventDefault()
        onCloseRef.current()
        return
      }
      if (event.key !== 'Tab') return
      const items = focusable()
      if (!items.length) {
        event.preventDefault()
        dialogRef.current?.focus()
        return
      }
      const first = items[0]
      const last = items[items.length - 1]
      if (event.shiftKey && (document.activeElement === first || !dialogRef.current?.contains(document.activeElement))) {
        event.preventDefault()
        last.focus()
      } else if (!event.shiftKey && document.activeElement === last) {
        event.preventDefault()
        first.focus()
      }
    }

    document.addEventListener('keydown', handleKeyDown)
    return () => {
      document.removeEventListener('keydown', handleKeyDown)
      if (previousFocus && document.contains(previousFocus)) previousFocus.focus()
    }
  }, [])

  return <div className="modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.currentTarget === event.target) onClose() }}><div ref={dialogRef} className={`modal ${wide ? 'modal--wide' : ''}`} role="dialog" aria-modal="true" aria-labelledby={titleId} tabIndex={-1}><div className="modal__header"><h2 id={titleId}>{title}</h2><button className="icon-btn" onClick={onClose} aria-label="Close"><X size={18}/></button></div><div className="modal__body">{children}</div></div></div>
}

export function ConfirmButton({ children, message, onConfirm, className = 'btn btn--danger', disabled = false }: { children: ReactNode; message: string; onConfirm: () => void; className?: string; disabled?: boolean }) {
  return <button className={className} disabled={disabled} onClick={() => { if (window.confirm(message)) onConfirm() }}>{children}</button>
}
