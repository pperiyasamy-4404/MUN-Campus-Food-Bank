import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { send, type Me } from './api.ts'
import { MeContext, type MeState } from './me.ts'

/** Asks the server who is logged in when the page opens, and shares the answer with every page. */
export function MeProvider({ children }: { children: ReactNode }) {
  const [me, setMe] = useState<MeState>({ state: 'loading' })

  useEffect(() => {
    let stillWanted = true
    fetch('/api/me')
      .then((response) => {
        if (!response.ok) throw new Error(`The server answered ${response.status}`)
        return response.json() as Promise<Me | null>
      })
      .then((answer) => {
        if (stillWanted) setMe({ state: 'ready', me: answer })
      })
      .catch(() => {
        if (stillWanted) setMe({ state: 'failed' })
      })
    return () => {
      stillWanted = false
    }
  }, [])

  const loggedIn = useCallback((answer: Me) => setMe({ state: 'ready', me: answer }), [])
  const forget = useCallback(() => setMe({ state: 'ready', me: null }), [])
  const logOut = useCallback(async () => {
    await send('/api/logout')
    setMe({ state: 'ready', me: null })
  }, [])

  return <MeContext value={{ me, loggedIn, logOut, forget }}>{children}</MeContext>
}
