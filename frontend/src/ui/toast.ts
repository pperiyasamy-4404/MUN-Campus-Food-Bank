import { createContext, useContext } from 'react'

// Toasts: a short message that slides up at the bottom of the screen, like
// "Code copied" or "You're logged out", and goes away by itself (13 Nov).
// For things that happened, not for problems to fix: those stay on the page.

export type ToastKind = 'success' | 'info'
export type Toast = { id: number; text: string; kind: ToastKind }
export type ShowToast = (text: string, kind?: ToastKind) => void

export const ToastContext = createContext<ShowToast | null>(null)

/** Show a toast. Works anywhere inside <ToastProvider>. */
export function useToast(): ShowToast {
  const show = useContext(ToastContext)
  if (show === null) throw new Error('useToast() needs <ToastProvider> around the page')
  return show
}
