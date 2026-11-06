import { Link } from 'react-router'
import type { Me } from '../api.ts'
import { useMe } from '../me.ts'

/**
 * Shown on the login and setup pages when someone is already logged in here.
 *
 * Mostly for the counter laptop: a student who sets up their account on it
 * would replace the volunteer's login with their own, and stay logged in on a
 * shared laptop for 30 days. Their own phone is the place for that (R1).
 */
export function AlreadyLoggedIn({ me }: { me: Me }) {
  const { logOut } = useMe()
  const staff = me.kind === 'staff'
  return (
    <div className="narrow">
      <h1>You're logged in</h1>
      {staff ? (
        <>
          <p>
            <strong>{me.username}</strong> is logged in on this device.
          </p>
          <p className="muted">
            Students: please set up your account or log in on your own phone, not on the food bank's laptop.
          </p>
        </>
      ) : (
        <p>You're logged in on this device.</p>
      )}
      <p className="actions">
        <Link className="button" to={staff ? '/counter' : '/book'}>
          Carry on
        </Link>
        <button type="button" className="secondary" onClick={logOut}>
          Log out
        </button>
      </p>
    </div>
  )
}
