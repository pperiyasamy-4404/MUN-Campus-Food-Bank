import { useEffect, useEffectEvent, useState } from 'react'
import { createPortal } from 'react-dom'
import logoWhite from '../assets/logo-full-white.png'
import { prefersLessMotion } from './hooks.ts'

const SHOWN_MS = 1500
const LEAVING_MS = 240
// The goodbye after Log out (13 Nov night) waits a little longer, so the words can be read.
const GOODBYE_SHOWN_MS = 1700
const GOODBYE_LEAVING_MS = 420

/**
 * The welcome screen after logging in (13 Nov): the claret screen, the MUN mark
 * growing in, a white line drawing across, and a greeting. Then it fades away
 * and onDone opens the person's page.
 *
 * With `goodbye`, the same screen says goodbye after logging out: a soft wave
 * of the logo, the line drawing back in, and a slower fade.
 *
 * Anyone whose phone asks for less movement goes straight to their page.
 */
export function WelcomeSplash({
  words,
  sub,
  goodbye = false,
  onDone,
}: {
  words: string
  sub?: string
  goodbye?: boolean
  onDone: () => void
}) {
  const [leaving, setLeaving] = useState(false)
  // The latest onDone, without restarting the timers each time the page above re-renders.
  const finish = useEffectEvent(onDone)

  useEffect(() => {
    if (prefersLessMotion()) {
      finish()
      return
    }
    const shown = goodbye ? GOODBYE_SHOWN_MS : SHOWN_MS
    const fade = window.setTimeout(() => setLeaving(true), shown)
    const done = window.setTimeout(() => finish(), shown + (goodbye ? GOODBYE_LEAVING_MS : LEAVING_MS))
    return () => {
      window.clearTimeout(fade)
      window.clearTimeout(done)
    }
  }, [goodbye])

  // On the page body itself, so nothing on the page can change its size or place.
  return createPortal(
    <div className={['splash', goodbye && 'goodbye', leaving && 'leaving'].filter(Boolean).join(' ')} role="status" aria-live="polite">
      <img className="splash-mark" src={logoWhite} alt="" width="560" height="358" />
      <span className="splash-line" aria-hidden="true" />
      <p className="splash-words">{words}</p>
      {sub && <p className="splash-sub">{sub}</p>}
    </div>,
    document.body,
  )
}
