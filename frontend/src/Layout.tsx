import { useState, ViewTransition, type ReactNode } from 'react'
import { Link, Navigate, NavLink, Outlet, useLocation, useNavigate } from 'react-router'
import { useMe } from './me.ts'
import logoMark from './assets/logo-mark-white.png'
import { useOnline } from './ui/hooks.ts'
import { Loading } from './ui/Loading.tsx'
import { WelcomeSplash } from './ui/WelcomeSplash.tsx'

// Browsers that can't do a smooth change between pages (React's <ViewTransition>)
// get the old fade-in on each new page instead.
const smoothPageChanges = typeof document !== 'undefined' && 'startViewTransition' in document
// How long the goodbye screen takes to cover the page (its fade in is 140 ms).
const GOODBYE_COVERS_MS = 250

/** The bar at the top of every page, and the page under it. */
export function Layout() {
  const { me, logOut } = useMe()
  const navigate = useNavigate()
  const location = useLocation()
  const online = useOnline()
  const account = me.state === 'ready' ? me.me : null
  // On the Log in and Set up pages, the Log in button up top would only point at the page itself.
  const onLogInPage = /^\/(staff\/)?(login|setup)$/.test(location.pathname)
  // Logging out shows a goodbye screen (13 Nov night), so it feels like something happened.
  const [leaving, setLeaving] = useState(false)

  // The goodbye screen covers everything first; only then does the logging out
  // happen underneath it, so the page never jumps to Log in before the goodbye.
  // Under the cover it goes straight to the pickup days, then logs out there, so the
  // Log in page never shows on the way (13 Nov night).
  function logOutAndLeave() {
    setLeaving(true)
    window.setTimeout(() => {
      navigate('/')
      void logOut()
    }, GOODBYE_COVERS_MS)
  }

  return (
    <>
      {/* A claret bar (decided 12 Nov night): the name, the tabs with icons like the
          my.mun.ca portal, and the account links on the right, in one row. */}
      <header className="top">
        <div className={account?.kind === 'staff' ? 'top-inner top-staff' : 'top-inner'}>
          {/* The food bank's logo, in white so it shows on the claret bar (13 Nov). Only the
              MUN shape: its small "Campus Food Bank" lettering can't be read this size, so
              the name stays as text. alt="" because the words next to it say it already. */}
          <Link to="/" className="brand">
            <img className="brand-mark" src={logoMark} alt="" width="80" height="45" />
            {/* Staff have six tabs: on a narrower screen the name hides (still read out). */}
            <span className="brand-name">Campus Food Bank</span>
          </Link>
          <nav aria-label="Account" className="account-links">
            {/* Only Log in up here (13 Nov night): setting up an account is a one-time
                thing, so its link lives on the Log in page instead. */}
            {account === null && me.state !== 'loading' && !onLogInPage && (
              <NavLink to="/login" className="header-login">
                Log in
              </NavLink>
            )}
            {account !== null && (
              <>
                {account.kind === 'staff' && <span className="who">{account.username}</span>}
                <button type="button" className="header-logout" onClick={logOutAndLeave} disabled={leaving}>
                  Log out
                </button>
              </>
            )}
          </nav>
          <nav aria-label="Main" className="tabs">
            <Tab to="/" end shape="calendar">
              Pickup days
            </Tab>
            {account?.kind === 'student' && (
              <Tab to="/book" shape="bag">
                Book
              </Tab>
            )}
            {account?.kind === 'staff' && (
              <Tab to="/counter" shape="card">
                Counter
              </Tab>
            )}
            {account?.kind === 'staff' && (
              <Tab to="/walk-in" shape="person">
                Walk-in
              </Tab>
            )}
            {account?.kind === 'staff' && (
              <Tab to="/setup-code" shape="key">
                Setup code
              </Tab>
            )}
            {account?.kind === 'staff' && (
              <Tab to="/packing" shape="box">
                Packing
              </Tab>
            )}
            {account?.kind === 'staff' && (
              <Tab to="/stock" shape="list">
                Stock
              </Tab>
            )}
            {account?.kind === 'staff' && account.role === 'coordinator' && (
              <Tab to="/coordinator" shape="sliders">
                Coordinator
              </Tab>
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
      {/* Changing page (13 Nov night): the old page fades and lifts away, and the new one
          rises in (React's <ViewTransition>, styled as "page" in motion.css). The header
          stays put. The key makes each address a fresh page. */}
      <ViewTransition default="page">
        <main>
          <div key={location.pathname} className={smoothPageChanges ? undefined : 'page-enter'}>
            <Outlet />
          </div>
        </main>
      </ViewTransition>
      {leaving && (
        <WelcomeSplash
          goodbye
          words="See you soon"
          sub="You're logged out"
          onDone={() => setLeaving(false)}
        />
      )}
    </>
  )
}

/**
 * One tab in the header. The white line under the tab you're on slides across
 * to the new tab when you change page (a shared <ViewTransition> name, 13 Nov night).
 */
function Tab({ to, end = false, shape, children }: { to: string; end?: boolean; shape: TabShape; children: ReactNode }) {
  return (
    <NavLink to={to} end={end}>
      {({ isActive }) => (
        <>
          <TabIcon shape={shape} />
          {children}
          {isActive ? (
            <ViewTransition name="tab-bar" share="tab-bar">
              <span className="tab-bar" aria-hidden="true" />
            </ViewTransition>
          ) : (
            <span className="tab-bar tab-bar-hover" aria-hidden="true" />
          )}
        </>
      )}
    </NavLink>
  )
}

type TabShape = 'calendar' | 'bag' | 'card' | 'person' | 'key' | 'box' | 'list' | 'sliders'

/**
 * A small line drawing for each tab, like the icons in the portal's tabs. Drawn
 * here, so no icon package is needed. Hidden from screen readers: the tab's words say it.
 */
function TabIcon({ shape }: { shape: TabShape }) {
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
    person: (
      <>
        <circle cx="12" cy="7" r="4" />
        <path d="M4 21a8 8 0 0 1 16 0" />
      </>
    ),
    key: (
      <>
        <circle cx="7.5" cy="15.5" r="4.5" />
        <path d="m10.7 12.3 9.8-9.8M17 6l3 3M14.5 8.5l2 2" />
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
