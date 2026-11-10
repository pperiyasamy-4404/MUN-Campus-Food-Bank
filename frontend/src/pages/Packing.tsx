import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import type { PackingQueue, QueueBag } from '../api.ts'
import { useMe } from '../me.ts'
import { showClock, showDate } from '../time.ts'
import { STATUS_WORDS } from './packingTools.ts'
import { PageHeading } from '../PageHeading.tsx'

// The packing queue (K1, U7): every bag for the pickup day being packed, by
// pickup time, so the earliest ones are packed first. It asks the server again
// every 30 seconds, so when another volunteer finds something has run out, the
// bags that need it get their flag without anyone reloading.

const EVERY_30_SECONDS = 30_000

type Load = { state: 'loading' } | { state: 'failed' } | { state: 'ready'; queue: PackingQueue }

export function Packing() {
  const { forget } = useMe()
  const [load, setLoad] = useState<Load>({ state: 'loading' })

  useEffect(() => {
    let stillWanted = true
    async function ask() {
      try {
        const response = await fetch('/api/packing')
        if (response.status === 401) {
          if (stillWanted) forget()
          return
        }
        if (!response.ok) throw new Error(`The server answered ${response.status}`)
        const queue = (await response.json()) as PackingQueue
        if (stillWanted) setLoad({ state: 'ready', queue })
      } catch {
        // A short network blip keeps the last answer on screen rather than blanking the page.
        if (stillWanted) setLoad((old) => (old.state === 'ready' ? old : { state: 'failed' }))
      }
    }
    ask()
    const timer = setInterval(ask, EVERY_30_SECONDS)
    return () => {
      stillWanted = false
      clearInterval(timer)
    }
  }, [forget])

  if (load.state === 'loading') return <p className="muted">Asking the server...</p>
  if (load.state === 'failed') return <p className="problem">Could not get the packing queue. Is the server running?</p>

  const { day, bags } = load.queue
  if (day === null) {
    return (
      <div>
        <PageHeading>Packing</PageHeading>
        <p className="muted">No pickup days are coming up.</p>
      </div>
    )
  }
  const toPack = bags.filter((bag) => bag.status === 'booked')
  const done = bags.filter((bag) => bag.status !== 'booked')

  return (
    <div>
      <PageHeading>Packing for {showDate(day.pickup_date)}</PageHeading>
      {/* No full stop after a time: it ends in "a.m." or "p.m." already. */}
      <p className="lead">
        Pack the earliest bags first. Packing starts when booking closes, at {showClock(day.packing_starts_at)}
        {day.pickup_starts_at && `, and pickup at ${showClock(day.pickup_starts_at)}`}
      </p>
      {day.why_not && <p className="notice">{day.why_not}</p>}

      <h2>To pack ({toPack.length})</h2>
      {toPack.length === 0 ? (
        <p className="muted">{bags.length === 0 ? 'Nobody has booked this day yet.' : 'Every bag is packed.'}</p>
      ) : (
        <ul className="bag-list">
          {toPack.map((bag) => (
            <BagRow key={bag.id} bag={bag} action={day.can_pack ? 'Pack' : 'Open'} />
          ))}
        </ul>
      )}

      {done.length > 0 && (
        <>
          <h2>Packed ({done.length})</h2>
          <ul className="bag-list">
            {done.map((bag) => (
              <BagRow key={bag.id} bag={bag} action="Open" />
            ))}
          </ul>
        </>
      )}
    </div>
  )
}

function BagRow({ bag, action }: { bag: QueueBag; action: string }) {
  const flagged = bag.ran_out.length > 0
  return (
    <li className={flagged ? 'bag-row bag-row-flagged' : 'bag-row'}>
      <span className="bag-time">{showClock(bag.starts_at)}</span>
      <span className="bag-code">{bag.code}</span>
      <span className="bag-about">
        <span>
          {bag.things} {bag.things === 1 ? 'thing' : 'things'}
          {bag.status !== 'booked' && ` · ${STATUS_WORDS[bag.status] ?? bag.status}`}
          {bag.packed_by && bag.packed_at && ` by ${bag.packed_by} at ${showClock(bag.packed_at)}`}
        </span>
        {/* U7: another volunteer found none of this, so this bag will need a substitute. */}
        {flagged && <span className="flag">Ran out: {bag.ran_out.join(', ')}</span>}
      </span>
      <Link className="button" to={`/packing/${bag.id}`}>
        {action}
        <span className="visually-hidden"> bag {bag.code}</span>
      </Link>
    </li>
  )
}
