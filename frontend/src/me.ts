import { createContext, useContext } from 'react'
import type { Me } from './api.ts'

// Who is logged in, asked once when the page opens and kept for every page.
//
// The login itself is a cookie the page can't read (HttpOnly), so the page asks
// the server: GET /api/me answers with the account, or null if nobody is.

export type MeState =
  | { state: 'loading' }
  | { state: 'failed' }
  | { state: 'ready'; me: Me | null }

export type MeTools = {
  me: MeState
  /** After logging in: the server's answer says who it is. */
  loggedIn: (me: Me) => void
  /** Log out on the server, then here. */
  logOut: () => Promise<void>
  /** The server said "Please log in." (a staff login ran out after 12 hours, say). */
  forget: () => void
}

export const MeContext = createContext<MeTools | null>(null)

export function useMe(): MeTools {
  const tools = useContext(MeContext)
  if (tools === null) throw new Error('useMe() needs <MeProvider> around the page')
  return tools
}

/** The logged-in account, or null if nobody is (or we don't know yet). */
export function useAccount(): Me | null {
  const { me } = useMe()
  return me.state === 'ready' ? me.me : null
}
