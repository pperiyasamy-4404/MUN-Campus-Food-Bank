import type { ReactNode } from 'react'
import { Link, Navigate, NavLink, Outlet, useNavigate } from 'react-router'
import { useMe } from './me.ts'

/** The bar at the top of every page, and the page under it. */
export function Layout() {
  const { me, logOut } = useMe()
  const navigate = useNavigate()
  const account = me.state === 'ready' ? me.me : null

  async function logOutAndLeave() {
    await logOut()
    navigate('/')
  }

  return (
    <>
      <header className="top">
        <nav aria-label="Main">
          <Link to="/" className="brand">
            Campus Food Bank
          </Link>
          <NavLink to="/" end>
            Pickup days
          </NavLink>
          {account?.kind === 'student' && <NavLink to="/book">Book</NavLink>}
          {account?.kind === 'staff' && <NavLink to="/counter">Counter</NavLink>}
          {account?.kind === 'staff' && <NavLink to="/stock">Stock</NavLink>}
          {account?.kind === 'staff' && account.role === 'coordinator' && (
            <NavLink to="/volunteers">Volunteers</NavLink>
          )}
          <span className="spacer" />
          {account === null && me.state !== 'loading' && (
            <>
              <NavLink to="/setup">Set up your account</NavLink>
              <NavLink to="/login">Log in</NavLink>
            </>
          )}
          {account !== null && (
            <>
              {account.kind === 'staff' && <span className="who">{account.username}</span>}
              <button type="button" className="link-button" onClick={logOutAndLeave}>
                Log out
              </button>
            </>
          )}
        </nav>
      </header>
      {me.state === 'failed' && (
        <p className="problem banner">Could not reach the server. Is it running?</p>
      )}
      <main>
        <Outlet />
      </main>
      <footer className="bottom">
        <Link to="/staff/login">Staff log in</Link>
      </footer>
    </>
  )
}

/** Only a logged-in student sees what's inside. Anyone else is sent to the student login page. */
export function StudentOnly({ children }: { children: ReactNode }) {
  const { me } = useMe()
  if (me.state === 'loading') return <p className="muted">Checking who's logged in...</p>
  if (me.state === 'failed') return null
  if (me.me?.kind !== 'student') return <Navigate to="/login" replace />
  return children
}

/**
 * Only staff see what's inside. Anyone else is sent to the staff login page.
 *
 * This only decides what the page shows. The server checks every request on its
 * own, so changing the page in the browser gets nobody any further.
 */
export function StaffOnly({ coordinator = false, children }: { coordinator?: boolean; children: ReactNode }) {
  const { me } = useMe()
  if (me.state === 'loading') return <p className="muted">Checking who's logged in...</p>
  if (me.state === 'failed') return null
  if (me.me?.kind !== 'staff') return <Navigate to="/staff/login" replace />
  if (coordinator && me.me.role !== 'coordinator') {
    return <p className="problem">Only the coordinator can see this page.</p>
  }
  return children
}
