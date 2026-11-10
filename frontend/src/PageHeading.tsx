import { useEffect, useRef, type ReactNode } from 'react'

const SITE = 'Campus Food Bank'

/**
 * A page's main heading. When it appears, it names the browser tab, like
 * "Pickup days · Campus Food Bank", and takes the keyboard and screen reader
 * focus, so someone who can't see the screen hears that a new page or stage
 * opened (WCAG 2.4.2 and 2.4.3).
 *
 * It only takes the focus when nothing else has it: never from a box someone
 * is typing in, or a button they're on.
 */
export function PageHeading({ children }: { children: ReactNode }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => {
    const text = heading.current?.textContent?.trim() ?? ''
    document.title = text && text !== SITE ? `${text} · ${SITE}` : SITE
    const focused = document.activeElement
    const nothingFocused = !focused || focused === document.body || focused.closest('header.top') !== null
    if (nothingFocused) heading.current?.focus({ preventScroll: true })
  }, [])
  // tabIndex -1: it can take the focus from code, but Tab still skips it.
  return (
    <h1 ref={heading} tabIndex={-1}>
      {children}
    </h1>
  )
}
