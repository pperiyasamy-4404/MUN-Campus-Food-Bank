import { useState } from 'react'
import { send, type FixBag } from '../api.ts'
import { Problem } from '../forms.tsx'
import { useMe } from '../me.ts'
import { showClock, showDate, showDayAndClock } from '../time.ts'
import { CounterNav } from './CounterParts.tsx'
import { useFixPage } from './counterTools.ts'
import { PageHeading } from '../PageHeading.tsx'

// Fixing a pickup marked wrong, once the day is over (B6). A bag handed over
// without pressing Hand over is a no-show at 6 pm: mark it picked up. A bag
// marked picked up that the student never took: mark it a no-show. Every fix
// is logged with who made it.

export function FixPickup() {
  const { forget } = useMe()
  const [day, setDay] = useState<string | null>(null)
  const [version, setVersion] = useState(0)
  const load = useFixPage(day, version, forget)
  // What to tell the volunteer after a fix, like "Bag K3P is now picked up."
  const [said, setSaid] = useState<string | null>(null)

  if (load.state === 'loading') return <p className="muted">Asking the server...</p>
  if (load.state === 'failed') return <p className="problem">Could not get the pickups. Is the server running?</p>
  const { page } = load

  function fixed(bag: FixBag) {
    const now = `Bag ${bag.code} is now ${bag.status === 'picked_up' ? 'picked up' : 'a no-show'}.`
    // A later booking, now too soon after this pickup, was cancelled (decided 12 Nov).
    setSaid(bag.cancelled ? `${now} ${bag.cancelled}` : now)
    setVersion((old) => old + 1)
  }

  return (
    <div>
      <CounterNav />
      <PageHeading>Fix a pickup</PageHeading>
      <p className="lead">
        For a mistake found after the day is over: a bag handed over without pressing Hand over, or one marked picked up
        that the student never took. Every fix is logged with your name.
      </p>
      {page.fix_before && (
        <p className="notice">
          Fix mistakes before {showDayAndClock(page.fix_before)}, when booking opens for the next pickup day. Then the
          stock count and the pickup gap are right in time.
        </p>
      )}
      {said && (
        <div className="done-box" role="status">
          {said}
        </div>
      )}

      {page.day === null ? (
        <p className="muted">Nothing to fix yet: pickups can be fixed once their day is over, at 6 pm.</p>
      ) : (
        <>
          {page.days.length > 1 && (
            <div className="field narrow">
              <label>
                Pickup day
                <select
                  value={page.day}
                  onChange={(event) => {
                    setSaid(null)
                    setDay(event.target.value)
                  }}
                >
                  {page.days.map((date) => (
                    <option key={date} value={date}>
                      {showDate(date)}
                    </option>
                  ))}
                </select>
              </label>
            </div>
          )}
          <section className="card">
            <h2 className="in-card">{showDate(page.day)}</h2>
            <ul className="pack-list">
              {page.bags.map((bag) => (
                <FixRow key={bag.id} bag={bag} onFixed={fixed} onLoggedOut={forget} />
              ))}
            </ul>
          </section>
        </>
      )}
    </div>
  )
}

function FixRow({
  bag,
  onFixed,
  onLoggedOut,
}: {
  bag: FixBag
  onFixed: (bag: FixBag) => void
  onLoggedOut: () => void
}) {
  const [asking, setAsking] = useState(false)
  const [sending, setSending] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const toPickedUp = bag.status === 'no_show'

  async function fix() {
    setProblem(null)
    setSending(true)
    const answer = await send<FixBag>(`/api/fixes/${bag.id}/${toPickedUp ? 'picked-up' : 'no-show'}`)
    setSending(false)
    if (answer.ok) {
      // The row stays when the list comes back, so close the question here.
      setAsking(false)
      return onFixed(answer.data)
    }
    if (answer.status === 401) return onLoggedOut()
    setProblem(answer.message)
  }

  return (
    <li className="pack-row">
      <span className="pack-name">
        <span className="bag-code">{bag.code}</span>
        <span className="muted">{showClock(bag.starts_at)}</span>
        {bag.status === 'picked_up' ? (
          <span>
            Picked up{bag.picked_up_at && ` at ${showClock(bag.picked_up_at)}`}
            {bag.picked_up_by && ` by ${bag.picked_up_by}`}
          </span>
        ) : (
          <span className="pack-state">No-show</span>
        )}
      </span>
      {bag.why_not ? (
        <span className="muted">{bag.why_not}</span>
      ) : asking ? (
        <div className="card undo-box">
          {toPickedUp ? (
            <p>
              <strong>Mark bag {bag.code} picked up?</strong> Its food comes off the stock count again, and the pickup
              gap counts from this pickup day. This is logged with your name.
            </p>
          ) : (
            <p>
              <strong>Mark bag {bag.code} a no-show?</strong> Its food, and anything given with it at the counter, goes
              back on the stock count. This is logged with your name.
            </p>
          )}
          <Problem message={problem} />
          <p className="actions">
            <button type="button" className="danger" onClick={fix} disabled={sending}>
              {sending ? 'Saving...' : toPickedUp ? 'Yes, they took it' : "Yes, they didn't take it"}
            </button>
            <button type="button" className="link-button" onClick={() => setAsking(false)}>
              Cancel
            </button>
          </p>
        </div>
      ) : (
        <button type="button" className="link-button" onClick={() => setAsking(true)}>
          {toPickedUp ? 'They did take it' : "They didn't take it"}
        </button>
      )}
    </li>
  )
}
