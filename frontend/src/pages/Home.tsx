import { FoodList } from '../FoodList.tsx'
import { PickupDayList } from '../PickupDayList.tsx'
import { useAccount } from '../me.ts'
import { showDay } from '../time.ts'

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
      <h1>Pickup days and food</h1>
      <p className="lead">
        A read-only look at the pickup days, their slots and the food, straight from the database. Nothing can be
        booked here yet. All times are Newfoundland time.
      </p>
      {account?.kind === 'student' && (
        <p className="notice">You're logged in. Booking comes in a later step.</p>
      )}
      <PickupDayList />
      <FoodList />
    </>
  )
}
