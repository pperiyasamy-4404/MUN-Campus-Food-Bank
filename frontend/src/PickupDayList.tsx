import { useState } from 'react'
import { useServerData, type BookingStatus, type PickupDay, type Slot } from './api.ts'
import { showClock, showDate, showDayAndClock } from './time.ts'
import { Empty } from './ui/Empty.tsx'
import { useNow } from './ui/hooks.ts'
import { Loading } from './ui/Loading.tsx'
import { untilText } from './ui/timing.ts'

const STATUS_TEXT: Record<BookingStatus, string> = {
  not_open_yet: 'Booking not open yet',
  open: 'Booking open',
  booking_over: 'Booking over',
  day_closed: 'Day closed',
}

export function PickupDayList() {
  const days = useServerData<PickupDay[]>('/api/pickup-days')

  return (
    <section>
      <h2>Pickup days</h2>
      {days.state === 'loading' && <Loading shape="days" label="Getting the pickup days" />}
      {days.state === 'failed' && (
        <p className="problem">Could not get the pickup days. Is the server running?</p>
      )}
      {days.state === 'ready' && days.data.length === 0 && (
        <Empty icon="calendar" title="No pickup days coming up">
          New days appear a week ahead. Check back soon.
        </Empty>
      )}
      {days.state === 'ready' &&
        days.data.map((day) => <PickupDayCard key={day.pickup_date} day={day} />)}
    </section>
  )
}

function PickupDayCard({ day }: { day: PickupDay }) {
  return (
    <article className="card">
      <header className="card-header">
        <h3>{showDate(day.pickup_date)}</h3>
        <span className={`status status-${day.booking_status}`}>
          {STATUS_TEXT[day.booking_status]}
        </span>
      </header>
      {day.closed_reason !== null ? (
        <p>This day is closed: {day.closed_reason}</p>
      ) : (
        <>
          {/* No full stop at the end: the time already ends in one ("12:00 p.m."). */}
          <p className="muted">
            Booking opens {showDayAndClock(day.booking_opens_at)} and closes{' '}
            {showDayAndClock(day.booking_closes_at)}
            {day.booking_status === 'not_open_yet' && (
              <OpensIn key={day.seconds_until_booking_opens} seconds={day.seconds_until_booking_opens} />
            )}
          </p>
          <ul className="slots">
            {day.slots.map((slot) => (
              <SlotChip key={slot.starts_at} slot={slot} bookable={day.booking_status === 'open'} />
            ))}
          </ul>
        </>
      )}
    </article>
  )
}

// Green "1 place" only while booking is open. Before it opens or after it
// closes, the places show in grey, since nobody can take them right now.
function SlotChip({ slot, bookable }: { slot: Slot; bookable: boolean }) {
  const full = slot.places_left === 0
  const className = full ? 'slot slot-full' : bookable ? 'slot' : 'slot slot-not-bookable'
  return (
    <li className={className}>
      <span className="slot-time">{showClock(slot.starts_at)}</span>
      <span className="slot-places">
        {full ? 'Full' : `${slot.places_left} ${slot.places_left === 1 ? 'place' : 'places'}`}
      </span>
    </li>
  )
}

/**
 * " (opens in 2 h 14 min)", counting down while the page is open (13 Nov). It
 * starts from the server's count, not the phone's clock, which may be wrong.
 */
function OpensIn({ seconds }: { seconds: number }) {
  const [loadedAt] = useState(() => Date.now())
  const now = useNow(1000)
  const left = seconds * 1000 - (now - loadedAt)
  if (left <= 0) return <span className="countdown"> (open now: refresh to book)</span>
  return (
    <>
      {' '}
      (opens <span className="countdown">{untilText(left)}</span>)
    </>
  )
}
