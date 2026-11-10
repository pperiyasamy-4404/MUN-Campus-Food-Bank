import { useState, type FormEvent } from 'react'
import { send, type BookingStatus, type ClosedDay, type CoordinatorDay, type DaysPage } from '../api.ts'
import { Field, Problem } from '../forms.tsx'
import { useMe } from '../me.ts'
import { showClock, showDate, showDayAndClock } from '../time.ts'
import { CoordinatorNav } from './CoordinatorParts.tsx'
import { count, forTimeBox, sayWeekdays, todayInStJohns, useStaffData } from './coordinatorTools.ts'
import { PageHeading } from '../PageHeading.tsx'

// The coordinator's pickup days: close a day for a holiday, bad weather or the
// Christmas break (S7), open it again, or move when booking opens and closes
// for one day (S9). Every change is logged with who made it.

const STATUS_TEXT: Record<BookingStatus, string> = {
  not_open_yet: 'Booking not open yet',
  open: 'Booking open',
  booking_over: 'Booking over',
  day_closed: 'Closed',
}

export function ManageDays() {
  const { forget } = useMe()
  const [version, setVersion] = useState(0)
  const load = useStaffData<DaysPage>('/api/coordinator/days', version, forget)
  // What to tell the coordinator after a change, like "Monday, November 23 is closed. 3 bookings were cancelled."
  const [said, setSaid] = useState<string | null>(null)

  if (load.state === 'loading') return <p className="muted">Asking the server...</p>
  if (load.state === 'failed') return <p className="problem">Could not get the pickup days. Is the server running?</p>
  const page = load.data

  function changed(message: string) {
    setSaid(message)
    setVersion((old) => old + 1)
  }

  return (
    <div>
      <CoordinatorNav />
      <PageHeading>Pickup days</PageHeading>
      <p className="lead">
        Close a day for a holiday, bad weather or the Christmas break, or move when booking opens and closes for one
        day. Days are made a week ahead. Every change is logged with your name.
      </p>
      {said && (
        <div className="done-box" role="status">
          {said}
        </div>
      )}
      {page.days.length === 0 && <p className="muted">No pickup days are coming up.</p>}
      {page.days.map((day) => (
        <DayCard key={day.pickup_date} day={day} onChanged={changed} onLoggedOut={forget} />
      ))}
      <CloseLater page={page} onChanged={changed} onLoggedOut={forget} />
    </div>
  )
}

function DayCard({
  day,
  onChanged,
  onLoggedOut,
}: {
  day: CoordinatorDay
  onChanged: (message: string) => void
  onLoggedOut: () => void
}) {
  // Which form is open under the day, if any.
  const [open, setOpen] = useState<'close' | 'move' | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const closed = day.closed_reason !== null

  // The card stays when the list comes back, so close its form here.
  function done(message: string) {
    setOpen(null)
    onChanged(message)
  }

  async function reopen() {
    setProblem(null)
    setSending(true)
    const answer = await send<CoordinatorDay>(`/api/coordinator/days/${day.pickup_date}/reopen`)
    setSending(false)
    if (answer.ok) return onChanged(`${showDate(day.pickup_date)} is open again.`)
    if (answer.status === 401) return onLoggedOut()
    setProblem(answer.message)
  }

  return (
    <article className="card">
      <header className="card-header">
        <h2 className="in-card">{showDate(day.pickup_date)}</h2>
        <span className={`status status-${day.booking_status}`}>{STATUS_TEXT[day.booking_status]}</span>
      </header>
      {closed && (
        <p>
          <strong>Closed:</strong> {day.closed_reason}
        </p>
      )}
      <dl className="day-facts">
        <dt>Booking</dt>
        <dd>
          {showDayAndClock(day.booking_opens_at)} until {showDayAndClock(day.booking_closes_at)}
        </dd>
        <dt>Pickup</dt>
        <dd>
          {showClock(day.pickup_starts_at)} to {showClock(day.pickup_ends_at)}, no-shows at {showClock(day.no_show_at)}
        </dd>
        {!closed && (
          <>
            <dt>Booked</dt>
            <dd>
              {count(day.booked, 'booking')}
              {day.packed > 0 && `, ${day.packed} packed`}
            </dd>
          </>
        )}
      </dl>
      <Problem message={problem} />

      {open === 'close' ? (
        <CloseForm day={day} onClosed={done} onCancel={() => setOpen(null)} onLoggedOut={onLoggedOut} />
      ) : open === 'move' ? (
        <MoveForm day={day} onMoved={done} onCancel={() => setOpen(null)} onLoggedOut={onLoggedOut} />
      ) : (
        <p className="actions">
          {!day.why_not_close && (
            <button type="button" className="danger" onClick={() => setOpen('close')}>
              Close this day
            </button>
          )}
          {!day.why_not_move && (
            <button type="button" className="secondary" onClick={() => setOpen('move')}>
              Move booking times
            </button>
          )}
          {closed && !day.why_not_reopen && (
            <button type="button" className="secondary" onClick={reopen} disabled={sending}>
              {sending ? 'Opening...' : 'Open it again'}
            </button>
          )}
          {closed && day.why_not_reopen && <span className="muted">{day.why_not_reopen}</span>}
        </p>
      )}
    </article>
  )
}

/** Close one day, with the reason students will see. Says first what it will cancel. */
function CloseForm({
  day,
  onClosed,
  onCancel,
  onLoggedOut,
}: {
  day: CoordinatorDay
  onClosed: (message: string) => void
  onCancel: () => void
  onLoggedOut: () => void
}) {
  const [reason, setReason] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  async function close(event: FormEvent) {
    event.preventDefault()
    setProblem(null)
    setSending(true)
    const answer = await send<ClosedDay>(`/api/coordinator/days/${day.pickup_date}/close`, { reason })
    setSending(false)
    if (answer.ok) return onClosed(closedMessage(answer.data))
    if (answer.status === 401) return onLoggedOut()
    setProblem(answer.message)
  }

  return (
    <form className="undo-box card" onSubmit={close}>
      <Field
        label="Why is it closed?"
        hint="Students see this, like “Snow storm” or “Christmas break”. Don't put anyone's name in it."
        value={reason}
        onChange={setReason}
        maxLength={200}
        required
      />
      {day.booked > 0 ? (
        <p>
          <strong>
            This cancels {count(day.booked, 'booking')}
            {day.packed > 0 && `, ${day.packed} of them packed`}.
          </strong>{' '}
          {day.packed > 0 && 'Unpack those bags: their food goes back on the stock count. '}
          Those students can book another day. A day that cancelled bookings can't be opened again.
        </p>
      ) : (
        <p>Nobody has booked it yet, so it can be opened again later if you change your mind.</p>
      )}
      <Problem message={problem} />
      <p className="actions">
        <button type="submit" className="danger" disabled={sending}>
          {sending ? 'Closing...' : `Close ${showDate(day.pickup_date)}`}
        </button>
        <button type="button" className="link-button" onClick={onCancel}>
          Cancel
        </button>
      </p>
    </form>
  )
}

function closedMessage(closed: ClosedDay): string {
  const said = `${showDate(closed.day.pickup_date)} is closed.`
  if (closed.cancelled === 0) return said
  const packed = closed.were_packed > 0 ? ` Unpack the ${count(closed.were_packed, 'packed bag')}.` : ''
  return `${said} ${count(closed.cancelled, 'booking was', 'bookings were')} cancelled.${packed}`
}

/** Move when booking opens and closes for this day only (S9). Times are St. John's time. */
function MoveForm({
  day,
  onMoved,
  onCancel,
  onLoggedOut,
}: {
  day: CoordinatorDay
  onMoved: (message: string) => void
  onCancel: () => void
  onLoggedOut: () => void
}) {
  const [opensAt, setOpensAt] = useState(forTimeBox(day.booking_opens_at))
  const [closesAt, setClosesAt] = useState(forTimeBox(day.booking_closes_at))
  const [problem, setProblem] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [sending, setSending] = useState(false)

  async function move(event: FormEvent) {
    event.preventDefault()
    setProblem(null)
    setSending(true)
    const answer = await send<CoordinatorDay>(
      `/api/coordinator/days/${day.pickup_date}/booking-times`,
      { opens_at: opensAt, closes_at: closesAt },
      'PUT',
    )
    setSending(false)
    if (answer.ok) {
      const moved = answer.data
      return onMoved(
        `Booking for ${showDate(day.pickup_date)} now opens ${showDayAndClock(moved.booking_opens_at)} and closes ${showDayAndClock(moved.booking_closes_at)}.`,
      )
    }
    if (answer.status === 401) return onLoggedOut()
    setFields(answer.fields)
    setProblem(answer.message)
  }

  return (
    <form className="undo-box card" onSubmit={move}>
      <p>
        For this day only. The settings, and the other days, stay as they are. Bookings already made stay. Times are St.
        John's time.
      </p>
      <div className="two-fields">
        <Field
          label="Booking opens"
          type="datetime-local"
          value={opensAt}
          onChange={setOpensAt}
          error={fields.opens_at && 'Enter a date and time.'}
          required
        />
        <Field
          label="Booking closes"
          hint={`By ${showClock(day.pickup_starts_at)}, when pickup starts`}
          type="datetime-local"
          value={closesAt}
          onChange={setClosesAt}
          error={fields.closes_at && 'Enter a date and time.'}
          required
        />
      </div>
      <Problem message={problem} />
      <p className="actions">
        <button type="submit" disabled={sending}>
          {sending ? 'Saving...' : 'Save the new times'}
        </button>
        <button type="button" className="link-button" onClick={onCancel}>
          Cancel
        </button>
      </p>
    </form>
  )
}

/** Close a date further ahead than the days made so far, like the Christmas break. */
function CloseLater({
  page,
  onChanged,
  onLoggedOut,
}: {
  page: DaysPage
  onChanged: (message: string) => void
  onLoggedOut: () => void
}) {
  const [date, setDate] = useState('')
  const [reason, setReason] = useState('')
  const [problem, setProblem] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  async function close(event: FormEvent) {
    event.preventDefault()
    setProblem(null)
    setSending(true)
    const answer = await send<ClosedDay>(`/api/coordinator/days/${date}/close`, { reason })
    setSending(false)
    if (answer.ok) {
      setDate('')
      setReason('')
      return onChanged(closedMessage(answer.data))
    }
    if (answer.status === 401) return onLoggedOut()
    setProblem(answer.message)
  }

  return (
    <section className="card">
      <h2 className="in-card">Close a later date</h2>
      <p className="muted">
        For a date further ahead, up to a year, like the Christmas break. Pickups are on{' '}
        {sayWeekdays(page.pickup_weekdays)}. The date is closed now, and stays closed when its time comes.
      </p>
      <form className="narrow" onSubmit={close}>
        <Field
          label="Date"
          type="date"
          value={date}
          onChange={setDate}
          min={todayInStJohns()}
          max={page.close_until}
          required
        />
        <Field
          label="Why is it closed?"
          hint="Students see this. Don't put anyone's name in it."
          value={reason}
          onChange={setReason}
          maxLength={200}
          required
        />
        <Problem message={problem} />
        <button type="submit" className="danger" disabled={sending}>
          {sending ? 'Closing...' : 'Close that date'}
        </button>
      </form>
    </section>
  )
}
