import { useCallback, useEffect, useRef, useState } from 'react'
import { send, type BookingDetails, type BookingStatus, type Food, type HeldTime, type MyBooking, type PickupDay, type Slot } from '../api.ts'
import { Problem } from '../forms.tsx'
import { useMe } from '../me.ts'
import { showClock, showDate, showDayAndClock } from '../time.ts'
import { ChooseFood } from './ChooseFood.tsx'
import { PageHeading } from '../PageHeading.tsx'
import { BookingSteps } from '../ui/BookingSteps.tsx'
import { Empty } from '../ui/Empty.tsx'
import { prefersLessMotion, useNow } from '../ui/hooks.ts'
import { Icon } from '../ui/Icon.tsx'
import { Loading } from '../ui/Loading.tsx'
import { untilText } from '../ui/timing.ts'
import { useToast } from '../ui/toast.ts'

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
  // True right after pressing Book: the booking page celebrates once (13 Nov).
  const [justBooked, setJustBooked] = useState(false)
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

  if (data.state === 'loading') return <Loading shape="days" label="Getting the pickup days" />
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
          celebrate={justBooked}
          onCancelled={() => {
            setJustBooked(false)
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
            setJustBooked(true)
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
          cancelledDays={mine.cancelled_days}
          holdMinutes={mine.limits.hold_minutes}
          onHeld={() => {
            setNotice(null)
            reload()
          }}
          onTaken={reload}
          onOpened={reload}
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
  cancelledDays,
  holdMinutes,
  onHeld,
  onTaken,
  onOpened,
  onLoggedOut,
}: {
  days: PickupDay[]
  allowedOn: string | null
  cancelledDays: MyBooking['cancelled_days']
  holdMinutes: number
  onHeld: () => void
  onTaken: () => void
  onOpened: () => void
  onLoggedOut: () => void
}) {
  // A refusal, shown in the card of the day that was tapped, where the student is looking (13 Nov).
  const [problem, setProblem] = useState<{ date: string; message: string } | null>(null)
  // The slot being held right now: it shows a spinner, and the others wait.
  const [holding, setHolding] = useState<number | null>(null)

  async function hold(day: PickupDay, slot: Slot) {
    setProblem(null)
    setHolding(slot.id)
    const answer = await send<HeldTime>('/api/holds', { slot_id: slot.id })
    setHolding(null)
    if (answer.ok) return onHeld()
    if (answer.status === 401) return onLoggedOut()
    setProblem({ date: day.pickup_date, message: answer.message })
    if (answer.status === 409) onTaken() // someone else took it: show the times as they are now
  }

  return (
    <>
      <BookingSteps current={1} />
      <PageHeading>Book a pickup</PageHeading>
      <p className="lead">
        Choose a time first. It's kept for you for {holdMinutes} minutes while you choose your food. All times are
        Newfoundland time.
      </p>
      {days.length === 0 && (
        <Empty icon="calendar" title="No pickup days coming up">
          New days appear a week ahead. Check back soon.
        </Empty>
      )}
      {days.map((day) => (
        <article className="card" key={day.pickup_date}>
          <header className="card-header">
            <h2 className="in-card">{showDate(day.pickup_date)}</h2>
            <span className={`status status-${day.booking_status}`}>{STATUS_TEXT[day.booking_status]}</span>
          </header>
          <DayChoices
            day={day}
            allowedOn={allowedOn}
            cancelled={cancelledDays.find((one) => one.pickup_date === day.pickup_date) ?? null}
            problem={problem?.date === day.pickup_date ? problem.message : null}
            holding={holding}
            onChoose={(slot) => hold(day, slot)}
            onOpened={onOpened}
          />
        </article>
      ))}
    </>
  )
}

function DayChoices({
  day,
  allowedOn,
  cancelled,
  problem,
  holding,
  onChoose,
  onOpened,
}: {
  day: PickupDay
  allowedOn: string | null
  cancelled: MyBooking['cancelled_days'][number] | null
  problem: string | null
  holding: number | null
  onChoose: (slot: Slot) => void
  onOpened: () => void
}) {
  if (day.booking_status === 'day_closed') return <p>This day is closed: {day.closed_reason}</p>
  // No full stop after a time: it ends in "p.m." already.
  if (day.booking_status === 'not_open_yet') {
    return (
      <OpensIn
        key={day.seconds_until_booking_opens}
        opensAt={day.booking_opens_at}
        seconds={day.seconds_until_booking_opens}
        onOpened={onOpened}
      />
    )
  }
  if (day.booking_status === 'booking_over') return <p className="muted">Booking for this day is over.</p>
  // Said before any tap, instead of times that would only be refused (S6, 13 Nov).
  if (cancelled !== null) {
    return (
      <p className="muted">
        {cancelled.you_cancelled ? 'You cancelled your booking for this day' : 'Your booking for this day was cancelled'}, so
        it can't be booked again. You can book a later day.
      </p>
    )
  }
  // Dates like "2026-11-09" compare correctly as text.
  if (allowedOn !== null && day.pickup_date < allowedOn) {
    return <p className="muted">Your next pickup can be on {showDate(allowedOn)} or later.</p>
  }
  return (
    <>
      <p className="muted">Booking closes {showDayAndClock(day.booking_closes_at)}</p>
      {problem !== null && <DayProblem message={problem} />}
      <ul className="slots">
        {day.slots.map((slot) => (
          <li key={slot.id}>
            <button
              type="button"
              className="slot-button"
              disabled={slot.places_left === 0 || holding !== null}
              aria-busy={holding === slot.id}
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

/** A refusal, right above the times that were tapped, and scrolled into view so it's seen. */
function DayProblem({ message }: { message: string }) {
  const box = useRef<HTMLDivElement>(null)
  useEffect(() => {
    box.current?.scrollIntoView({ behavior: prefersLessMotion() ? 'auto' : 'smooth', block: 'center' })
  }, [message])
  return (
    <div ref={box}>
      <Problem message={message} />
    </div>
  )
}

/**
 * "Booking opens Sunday, November 15 at 5:00 p.m. (in 2 h 14 min)", counting down.
 * When the moment comes, the page asks the server again, so the times appear by themselves.
 */
function OpensIn({ opensAt, seconds, onOpened }: { opensAt: string; seconds: number; onOpened: () => void }) {
  // From the server's count, not the phone's clock, which may be wrong.
  const [loadedAt] = useState(() => Date.now())
  const now = useNow(1000)
  const left = seconds * 1000 - (now - loadedAt)
  const opened = left <= 0
  useEffect(() => {
    if (opened) onOpened()
  }, [opened, onOpened])
  return (
    <p className="muted">
      Booking opens {showDayAndClock(opensAt)} (<span className="countdown">{untilText(left)}</span>)
    </p>
  )
}

// ---------- 3. your booking ----------

function YourBooking({
  booking,
  celebrate,
  onCancelled,
  onLoggedOut,
}: {
  booking: BookingDetails
  celebrate: boolean
  onCancelled: () => void
  onLoggedOut: () => void
}) {
  const [problem, setProblem] = useState<string | null>(null)
  const toast = useToast()

  async function copyCode() {
    try {
      await navigator.clipboard.writeText(booking.code)
      toast(`Code ${booking.code} copied`)
    } catch {
      toast(`Couldn't copy it. Your code is ${booking.code}`, 'info')
    }
  }

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
      <BookingSteps current={3} />
      {celebrate ? (
        <div className="booked-hero">
          <svg className="booked-tick" viewBox="0 0 56 56" aria-hidden="true">
            <circle cx="28" cy="28" r="25" />
            <path d="M17 29l7 7 15-16" />
          </svg>
          <PageHeading>You're booked!</PageHeading>
        </div>
      ) : (
        <PageHeading>Your booking</PageHeading>
      )}
      <section className="code-box">
        <h2>Your code</h2>
        <div className="code-copy">
          <p className="code">{booking.code}</p>
          <button type="button" className="secondary" onClick={copyCode}>
            <Icon name="copy" className="button-icon" /> Copy code
          </button>
        </div>
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
