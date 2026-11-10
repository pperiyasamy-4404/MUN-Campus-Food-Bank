import type { Shown, TotalsPage } from '../api.ts'
import { useMe } from '../me.ts'
import { showDate } from '../time.ts'
import { CoordinatorNav } from './CoordinatorParts.tsx'
import { useStaffData } from './coordinatorTools.ts'

// Weekly totals for the coordinator (P12): only numbers, by week. Any number
// under 5 arrives from the server as "fewer than 5", so the page never has
// the real small number to show.

export function Totals() {
  const { forget } = useMe()
  const load = useStaffData<TotalsPage>('/api/totals', 0, forget)

  if (load.state === 'loading') return <p className="muted">Asking the server...</p>
  if (load.state === 'failed') return <p className="problem">Could not get the totals. Is the server running?</p>
  const { weeks } = load.data

  return (
    <div>
      <CoordinatorNav />
      <h1>Weekly totals</h1>
      <p className="lead">
        What each week added up to, Monday to Sunday. A pickup day counts once it's over, at its no-show time. Any number
        under 5 shows as “fewer than 5”, so nobody can be picked out. Weeks with no bookings and no walk-ins aren't
        listed.
      </p>
      {weeks.length === 0 ? (
        <p className="muted">No totals yet: they start once the first pickup day is over.</p>
      ) : (
        <div className="table-scroll">
          <table className="people totals">
            <thead>
              <tr>
                <th scope="col">Week of</th>
                <th scope="col">Bags picked up</th>
                <th scope="col">Walk-ins</th>
                <th scope="col">No-shows</th>
                <th scope="col">Cancelled</th>
                <th scope="col">Food given out</th>
              </tr>
            </thead>
            <tbody>
              {weeks.map((week) => (
                <tr key={week.week_starts_on}>
                  <th scope="row">{showDate(week.week_starts_on)}</th>
                  <td>
                    <Count value={week.picked_up} />
                  </td>
                  <td>
                    <Count value={week.walk_ins} />
                  </td>
                  <td>
                    <Count value={week.no_shows} />
                  </td>
                  <td>
                    <Count value={week.cancelled} />
                  </td>
                  <td>
                    {week.items.length === 0 ? (
                      <span className="muted">Nothing</span>
                    ) : (
                      <details>
                        <summary>{week.items.length === 1 ? '1 item' : `${week.items.length} items`}</summary>
                        <ul className="item-totals">
                          {week.items.map((line) => (
                            <li key={line.item}>
                              <span>{line.item}</span>
                              <Count value={line.given_out} />
                            </li>
                          ))}
                        </ul>
                      </details>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}

function Count({ value }: { value: Shown }) {
  return typeof value === 'number' ? <span className="total">{value}</span> : <span className="muted">{value}</span>
}
