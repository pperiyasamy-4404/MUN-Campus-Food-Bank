import type { ReactNode } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useMe } from './me.ts'
import logoMark from './assets/logo-mark-white.png'
import { useOnline } from './ui/hooks.ts'
import { Loading } from './ui/Loading.tsx'
import { useToast } from './ui/toast.ts'

/** The bar at the top of every page, and the page under it. */
export function Layout() {
  const { me, logOut } = useMe()
  const navigate = useNavigate()
  const location = useLocation()
  const online = useOnline()
  const toast = useToast()
  const account = me.state === 'ready' ? me.me : null

  async function logOutAndLeave() {
    await logOut()
    navigate('/')
    toast("You're logged out. See you soon.")
  }

  return (
    <>
      {/* A claret bar (decided 12 Nov night): the name, the tabs with icons like the
          my.mun.ca portal, and the account links on the right, in one row. */}
      <header className="top">
        <div className="top-inner">
          {/* The food bank's logo, in white so it shows on the claret bar (13 Nov). Only the
              MUN shape: its small "Campus Food Bank" lettering can't be read this size, so
              the name stays as text. alt="" because the words next to it say it already. */}
          <Link to="/" className="brand">
            <img className="brand-mark" src={logoMark} alt="" width="80" height="45" />
            Campus Food Bank
          </Link>
          <nav aria-label="Account" className="account-links">
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
          <nav aria-label="Main" className="tabs">
            <NavLink to="/" end>
              <TabIcon shape="calendar" />
              Pickup days
            </NavLink>
            {account?.kind === 'student' && (
              <NavLink to="/book">
                <TabIcon shape="bag" />
                Book
              </NavLink>
            )}
            {account?.kind === 'staff' && (
              <NavLink to="/counter">
                <TabIcon shape="card" />
                Counter
              </NavLink>
            )}
            {account?.kind === 'staff' && (
              <NavLink to="/packing">
                <TabIcon shape="box" />
                Packing
              </NavLink>
            )}
            {account?.kind === 'staff' && (
              <NavLink to="/stock">
                <TabIcon shape="list" />
                Stock
              </NavLink>
            )}
            {account?.kind === 'staff' && account.role === 'coordinator' && (
              <NavLink to="/coordinator">
                <TabIcon shape="sliders" />
                Coordinator
              </NavLink>
            )}
          </nav>
        </div>
      </header>
      {!online && (
        <p className="offline-banner" role="status">
          You're offline. Nothing can be saved until your connection is back.
        </p>
      )}
      {me.state === 'failed' && online && (
        <p className="problem banner">Could not reach the server. Is it running?</p>
      )}
      <main>
        {/* A new page fades in. The key starts the animation again on each address. */}
        <div key={location.pathname} className="page-enter">
          <Outlet />
        </div>
      </main>
    </>
  )
}

/**
 * A small line drawing for each tab, like the icons in the portal's tabs. Drawn
 * here, so no icon package is needed. Hidden from screen readers: the tab's words say it.
 */
function TabIcon({ shape }: { shape: 'calendar' | 'bag' | 'card' | 'box' | 'list' | 'sliders' }) {
  const lines = {
    calendar: (
      <>
        <rect x="3" y="4" width="18" height="17" rx="2" />
        <path d="M16 2v4M8 2v4M3 10h18" />
      </>
    ),
    bag: (
      <>
        <path d="M6 2 3 6v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2V6l-3-4z" />
        <path d="M3 6h18M16 10a4 4 0 0 1-8 0" />
      </>
    ),
    card: (
      <>
        <rect x="2" y="5" width="20" height="14" rx="2" />
        <circle cx="8" cy="12" r="2" />
        <path d="M13 10h5M13 14h5" />
      </>
    ),
    box: (
      <>
        <path d="M21 8 12 3 3 8v8l9 5 9-5z" />
        <path d="m3 8 9 5 9-5M12 13v8" />
      </>
    ),
    list: <path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01" />,
    sliders: <path d="M4 21v-7M4 10V3M12 21v-9M12 8V3M20 21v-5M20 12V3M1 14h6M9 8h6M17 16h6" />,
  }[shape]
  return (
    <svg
      className="tab-icon"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {lines}
    </svg>
  )
}

/** Only a logged-in student sees what's inside. Anyone else is sent to the student login page. */
export function StudentOnly({ children }: { children: ReactNode }) {
  const { me } = useMe()
  if (me.state === 'loading') return <Loading label="Checking who's logged in" />
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
  if (me.state === 'loading') return <Loading label="Checking who's logged in" />
  if (me.state === 'failed') return null
  if (me.me?.kind !== 'staff') return <Navigate to="/staff/login" replace />
  if (coordinator && me.me.role !== 'coordinator') {
    return <p className="problem">Only a coordinator can see this page.</p>
  }
  return children
}
