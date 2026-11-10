import { Link } from 'react-router'
import { FoodList } from '../FoodList.tsx'
import { PickupDayList } from '../PickupDayList.tsx'
import { useAccount } from '../me.ts'
import { showDay } from '../time.ts'
import { PageHeading } from '../PageHeading.tsx'

export function Home() {
  const account = useAccount()

  return (
    <>
      {account?.kind === 'student' && account.password_reset_at !== null && (
        // R4: so a student notices if someone else reset their password.
        <p className="notice">
          Your password was reset on {showDay(account.password_reset_at)}. If that wasn't you, please tell a
          volunteer at the counter.
        </p>
      )}
      <section className="hero">
        <PageHeading>Campus Food Bank</PageHeading>
        <p>
          Free food for MUN students. Book a pickup time, choose your food, and collect your bag at the counter. All
          times are Newfoundland time.
        </p>
        <p className="actions">
          {account === null && (
            <>
              <Link className="button" to="/login">
                Log in to book
              </Link>
              <Link className="button ghost" to="/setup">
                First time? Set up your account
              </Link>
            </>
          )}
          {account?.kind === 'student' && (
            <Link className="button" to="/book">
              Book a pickup, or see your booking
            </Link>
          )}
          {account?.kind === 'staff' && (
            <Link className="button" to="/counter">
              Go to the counter
            </Link>
          )}
        </p>
      </section>
      <PickupDayList />
      <FoodList />
    </>
  )
}
