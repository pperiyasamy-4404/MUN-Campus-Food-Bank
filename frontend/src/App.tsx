import { FoodList } from './FoodList.tsx'
import { PickupDayList } from './PickupDayList.tsx'

function App() {
  return (
    <main>
      <p className="eyebrow">Campus Food Bank</p>
      <h1>What's in the database</h1>
      <p className="lead">
        A read-only look at the pickup days, their slots and the food, straight from the
        database. Nothing can be booked here yet. All times are Newfoundland time.
      </p>
      <PickupDayList />
      <FoodList />
    </main>
  )
}

export default App
