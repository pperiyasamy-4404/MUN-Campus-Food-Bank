import { useCallback, useRef, useState, type ReactNode } from 'react'
import { Icon } from './Icon.tsx'
import { ToastContext, type Toast, type ToastKind } from './toast.ts'

const SHOWN_FOR_MS = 4500

/**
 * Shows toasts at the bottom of the screen. The list is a polite live region,
 * so a screen reader says each one once, without interrupting.
 */
export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)

  const dismiss = useCallback((id: number) => setToasts((old) => old.filter((toast) => toast.id !== id)), [])

  const show = useCallback(
    (text: string, kind: ToastKind = 'success') => {
      const id = nextId.current++
      // At most 3 at once: the oldest goes first.
      setToasts((old) => [...old.slice(-2), { id, text, kind }])
      window.setTimeout(() => dismiss(id), SHOWN_FOR_MS)
    },
    [dismiss],
  )

  return (
    <ToastContext value={show}>
      {children}
      <div className="toasts" role="status" aria-live="polite">
        {toasts.map((toast) => (
          <div key={toast.id} className={`toast toast-${toast.kind}`}>
            <Icon name={toast.kind === 'success' ? 'check' : 'info'} className="toast-icon" />
            <span className="toast-text">{toast.text}</span>
            <button type="button" onClick={() => dismiss(toast.id)} aria-label="Dismiss">
              ×
            </button>
          </div>
        ))}
      </div>
    </ToastContext>
  )
}
