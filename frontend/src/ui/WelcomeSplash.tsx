import { useEffect, useEffectEvent, useState } from 'react'
import { createPortal } from 'react-dom'
import logoWhite from '../assets/logo-full-white.png'
import { prefersLessMotion } from './hooks.ts'

const SHOWN_MS = 1500
const LEAVING_MS = 240

/**
 * The welcome screen after logging in (13 Nov): the claret screen, the MUN mark
 * growing in, a white line drawing across, and a greeting. Then it fades away
 * and onDone opens the person's page.
 *
 * Anyone whose phone asks for less movement goes straight to their page.
 */
export function WelcomeSplash({ words, sub, onDone }: { words: string; sub?: string; onDone: () => void }) {
  const [leaving, setLeaving] = useState(false)
  // The latest onDone, without restarting the timers each time the page above re-renders.
  const finish = useEffectEvent(onDone)

  useEffect(() => {
    if (prefersLessMotion()) {
      finish()
      return
    }
    const fade = window.setTimeout(() => setLeaving(true), SHOWN_MS)
    const done = window.setTimeout(() => finish(), SHOWN_MS + LEAVING_MS)
    return () => {
      window.clearTimeout(fade)
      window.clearTimeout(done)
    }
  }, [])

  // On the page body itself, so nothing on the page can change its size or place.
  return createPortal(
    <div className={leaving ? 'splash leaving' : 'splash'} role="status" aria-live="polite">
      <img className="splash-mark" src={logoWhite} alt="" width="560" height="358" />
      <span className="splash-line" aria-hidden="true" />
      <p className="splash-words">{words}</p>
      {sub && <p className="splash-sub">{sub}</p>}
    </div>,
    document.body,
  )
}
