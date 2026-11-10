import { useCallback, useEffect, useState } from 'react'
import { send, type BookingDetails, type BookingStatus, type Food, type HeldTime, type MyBooking, type PickupDay, type Slot } from '../api.ts'
import { Problem } from '../forms.tsx'
import { useMe } from '../me.ts'
import { showClock, showDate, showDayAndClock } from '../time.ts'
import { ChooseFood } from './ChooseFood.tsx'

// A student's booking page, in three stages (S8):
//   1. choose a time: it's held for them for 10 minutes
//   2. choose food, with a countdown, and press Book
//   3. their booking: the code to say at the counter, and Cancel
// The server decides which stage they're at, so a reload never loses their place.

type Data =
  | { state: 'loading' }
  | { state: 'failed' }
  | { state: 'ready'; mine: MyBooking; days: PickupDay[]; food: Food }

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(path)
  if (response.status === 401) throw new Error('logged out')
  if (!response.ok) throw new Error(`The server answered ${response.status}`)
  return (await response.json()) as T
}

export function Book() {
  const { forget } = useMe()
  const [data, setData] = useState<Data>({ state: 'loading' })
  const [version, setVersion] = useState(0)
  // Something to tell the student after the page changes stage, like "Your 10 minutes ran out."
  const [notice, setNotice] = useState<string | null>(null)
  const reload = useCallback(() => setVersion((old) => old + 1), [])

  useEffect(() => {
    let stillWanted = true
    Promise.all([
      getJson<MyBooking>('/api/my-booking'),
      getJson<PickupDay[]>('/api/pickup-days'),
      getJson<Food>('/api/food'),
    ])
      .then(([mine, days, food]) => {
        if (stillWanted) setData({ state: 'ready', mine, days, food })
      })
      .catch((error: Error) => {
        if (!stillWanted) return
        if (error.message === 'logged out') forget()
        else setData({ state: 'failed' })
      })
    return () => {
      stillWanted = false
    }
  }, [version, forget])

  const timeUp = useCallback(() => {
    setNotice('Your time ran out, so it was let go. Choose a time again.')
    reload()
  }, [reload])

  if (data.state === 'loading') return <p className="muted">Asking the server...</p>
  if (data.state === 'failed') return <p className="problem">Could not get your booking. Is the server running?</p>

  const { mine, days, food } = data
  return (
    <div>
      {notice && <p className="notice">{notice}</p>}
      {mine.closed_day && !mine.booking && (
        <div className="problem" role="status">
          <p>
            <strong>The food bank closed {showDate(mine.closed_day.pickup_date)},</strong> so your booking for that day
            was cancelled. You can book another day.
          </p>
          <p>Why: {mine.closed_day.reason}</p>
        </div>
      )}
      {mine.booking ? (
        <YourBooking
          booking={mine.booking}
          onCancelled={() => {
            setNotice('Your booking is cancelled. The food and the time went back for someone else.')
            reload()
          }}
          onLoggedOut={forget}
        />
      ) : mine.hold ? (
        <ChooseFood
          key={mine.hold.slot_id}
          hold={mine.hold}
          limits={mine.limits}
          food={food}
          onBooked={() => {
            setNotice(null)
            reload()
          }}
          onTimeUp={timeUp}
          onStartOver={() => {
            setNotice(null)
            reload()
          }}
          onFoodChanged={reload}
          onLoggedOut={forget}
        />
      ) : (
        <ChooseTime
          days={days}
          allowedOn={mine.next_pickup_allowed_on}
          holdMinutes={mine.limits.hold_minutes}
          onHeld={() => {
            setNotice(null)
            reload()
          }}
          onTaken={reload}
          onLoggedOut={forget}
        />
      )}
    </div>
  )
}

// ---------- 1. choose a time ----------

const STATUS_TEXT: Record<BookingStatus, string> = {
  not_open_yet: 'Booking not open yet',
  open: 'Booking open',
  booking_over: 'Booking over',
  day_closed: 'Day closed',
}

function ChooseTime({
  days,
  allowedOn,
  holdMinutes,
  onHeld,
  onTaken,
  onLoggedOut,
}: {
  days: PickupDay[]
  allowedOn: string | null
  holdMinutes: number
  onHeld: () => void
  onTaken: () => void
  onLoggedOut: () => void
}) {
  const [problem, setProblem] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  async function hold(slot: Slot) {
    setSending(true)
    const answer = await send<HeldTime>('/api/holds', { slot_id: slot.id })
    setSending(false)
    if (answer.ok) return onHeld()
    if (answer.status === 401) return onLoggedOut()
    setProblem(answer.message)
    if (answer.status === 409) onTaken() // someone else took it: show the times as they are now
  }

  return (
    <>
      <h1>Book a pickup</h1>
      <p className="lead">
        Choose a time first. It's kept for you for {holdMinutes} minutes while you choose your food. All times are
        Newfoundland time.
      </p>
      <Problem message={problem} />
      {days.length === 0 && <p className="muted">No pickup days are coming up.</p>}
      {days.map((day) => (
        <article className="card" key={day.pickup_date}>
          <header className="card-header">
            <h2 className="in-card">{showDate(day.pickup_date)}</h2>
            <span className={`status status-${day.booking_status}`}>{STATUS_TEXT[day.booking_status]}</span>
          </header>
          <DayChoices day={day} allowedOn={allowedOn} sending={sending} onChoose={hold} />
        </article>
      ))}
    </>
  )
}

function DayChoices({
  day,
  allowedOn,
  sending,
  onChoose,
}: {
  day: PickupDay
  allowedOn: string | null
  sending: boolean
  onChoose: (slot: Slot) => void
}) {
  if (day.booking_status === 'day_closed') return <p>This day is closed: {day.closed_reason}</p>
  // No full stop after a time: it ends in "p.m." already.
  if (day.booking_status === 'not_open_yet') return <p className="muted">Booking opens {showDayAndClock(day.booking_opens_at)}</p>
  if (day.booking_status === 'booking_over') return <p className="muted">Booking for this day is over.</p>
  // Dates like "2026-11-09" compare correctly as text.
  if (allowedOn !== null && day.pickup_date < allowedOn) {
    return <p className="muted">Your next pickup can be on {showDate(allowedOn)} or later.</p>
  }
  return (
    <>
      <p className="muted">Booking closes {showDayAndClock(day.booking_closes_at)}</p>
      <ul className="slots">
        {day.slots.map((slot) => (
          <li key={slot.id}>
            <button
              type="button"
              className="slot-button"
              disabled={slot.places_left === 0 || sending}
              onClick={() => onChoose(slot)}
            >
              <span className="slot-time">{showClock(slot.starts_at)}</span>
              <span className="slot-places">{slot.places_left === 0 ? 'Taken' : 'Free'}</span>
            </button>
          </li>
        ))}
      </ul>
    </>
  )
}

// ---------- 3. your booking ----------

function YourBooking({
  booking,
  onCancelled,
  onLoggedOut,
}: {
  booking: BookingDetails
  onCancelled: () => void
  onLoggedOut: () => void
}) {
  const [problem, setProblem] = useState<string | null>(null)

  async function cancel() {
    const sure = window.confirm(
      `Cancel your booking for ${showDate(booking.pickup_date)}? You won't be able to book that day again, but you can book a later day.`,
    )
    if (!sure) return
    const answer = await send('/api/my-booking/cancel')
    if (answer.ok) return onCancelled()
    if (answer.status === 401) return onLoggedOut()
    setProblem(answer.message)
  }

  return (
    <div className="narrow-wide">
      <h1>Your booking</h1>
      <section className="code-box">
        <h2>Your code</h2>
        <p className="code">{booking.code}</p>
        <p>
          <strong>{showDayAndClock(booking.starts_at)}</strong>
        </p>
        <p>Say this code at the counter, and bring your MUN card: the volunteer checks it before handing over your bag.</p>
      </section>

      <h2>Your food</h2>
      <ul className="booked-list">
        {booking.items.map((line) => (
          <li key={line.variety}>
            {line.variety}
            {line.quantity > 1 && ` × ${line.quantity}`} <span className="muted">({line.item})</span>
          </li>
        ))}
      </ul>
      {booking.substitutes.length > 0 && (
        <>
          <h3>If something is gone, use these, in this order</h3>
          <ol className="booked-list">
            {booking.substitutes.map((line) => (
              <li key={line.rank}>
                {line.variety} <span className="muted">({line.item})</span>
              </li>
            ))}
          </ol>
        </>
      )}

      <h2>Can't come?</h2>
      <Problem message={problem} />
      {booking.can_cancel ? (
        <>
          <p>
            You can cancel until {showDayAndClock(booking.cancel_until)}
          </p>
          <button type="button" className="danger" onClick={cancel}>
            Cancel this booking
          </button>
        </>
      ) : (
        <p>Cancelling has closed, because the bags are being packed. If you can't come, please tell the food bank.</p>
      )}
    </div>
  )
}
