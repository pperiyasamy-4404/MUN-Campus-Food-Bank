import { useState, type FormEvent } from 'react'
import { send, type CounterPage, type WalkInCheck, type WalkInDone } from '../api.ts'
import { Field, Problem } from '../forms.tsx'
import { useMe } from '../me.ts'
import { showDate } from '../time.ts'
import { useValues } from '../useValues.ts'
import { CounterNav, ExtrasPicker, ShelfPicker } from './CounterParts.tsx'
import { asChoices, total, useCounterPage, type Chosen } from './counterTools.ts'
import { PageHeading } from '../PageHeading.tsx'

// A walk-in (W1, W3, W4): a student served without a booking, in their own line.
// 1. Check their MUN card: the pickup gap, with no exception.
// 2. Choose what they take from the shelf, and any extras.
// 3. Record it. Their next pickup is 30 days from today, online or in person.

export function WalkIn() {
  const { forget } = useMe()
  const [version, setVersion] = useState(0)
  const load = useCounterPage(version, forget)
  const { values, set, clear } = useValues({ id_number: '', again: '' })
  const [checked, setChecked] = useState<WalkInCheck | null>(null)
  const [done, setDone] = useState<WalkInDone | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [sending, setSending] = useState(false)

  async function check(event: FormEvent) {
    event.preventDefault()
    setProblem(null)
    setFields({})
    // Typed twice: a typo would record the walk-in under someone else's number,
    // and block them for 30 days instead of this student.
    if (values.id_number.replace(/[\s-]/g, '') !== values.again.replace(/[\s-]/g, '')) {
      setProblem('Please fix the boxes marked in red.')
      setFields({ again: "The two numbers aren't the same. Check the card again." })
      return
    }
    setSending(true)
    const answer = await send<WalkInCheck>('/api/walk-ins/check', { id_number: values.id_number })
    setSending(false)
    if (answer.ok) return setChecked(answer.data)
    if (answer.status === 401) return forget()
    setProblem(answer.message)
    setFields(answer.fields)
  }

  function nextStudent() {
    // The number leaves the screen, and the shelf is asked for again.
    clear()
    setChecked(null)
    setDone(null)
    setProblem(null)
    setFields({})
    setVersion((old) => old + 1)
  }

  if (load.state === 'loading') return <p className="muted">Asking the server...</p>
  if (load.state === 'failed') return <p className="problem">Could not get the counter. Is the server running?</p>
  const { page } = load

  return (
    <div>
      <CounterNav />
      <PageHeading>Walk-in</PageHeading>
      <p className="lead">A student without a booking. They take what's on the shelf that nobody booked.</p>
      {!page.walk_ins_open && <p className="notice">{page.walk_ins_why_not}</p>}

      {done ? (
        <div className="code-box narrow-wide" role="status">
          <h2>Walk-in recorded</h2>
          <p>
            {done.things} {done.things === 1 ? 'thing' : 'things'}
            {done.extras > 0 && ` and ${done.extras} ${done.extras === 1 ? 'extra' : 'extras'}`}.
            {done.new_account && ' An account was made for their card. Give them a setup code if they want to book online.'}
          </p>
          {done.cancelled && (
            <p>
              Their booking for {showDate(done.cancelled.pickup_date)} (bag {done.cancelled.code}) was cancelled.
            </p>
          )}
          <p>Their next pickup can be on {showDate(done.next_pickup_on)}.</p>
          <button type="button" onClick={nextStudent}>
            Next student
          </button>
        </div>
      ) : checked === null ? (
        <form className="narrow" onSubmit={check} noValidate autoComplete="off">
          <Problem message={problem} />
          <Field
            label="ID number on their MUN card"
            hint="Type it from the card itself. No card, no food: a student who lost it gets a new MUN card first."
            inputMode="numeric"
            value={values.id_number}
            onChange={set('id_number')}
            error={fields.id_number}
          />
          <Field label="Re-enter ID number" inputMode="numeric" value={values.again} onChange={set('again')} error={fields.again} />
          <button type="submit" disabled={sending || !page.walk_ins_open}>
            {sending ? 'Checking...' : 'Check the card'}
          </button>
        </form>
      ) : !checked.can_serve ? (
        <div className="refused-box narrow-wide" role="alert">
          <h2>Can't be served today</h2>
          <p>{checked.why_not}</p>
          <button type="button" onClick={nextStudent}>
            Next student
          </button>
        </div>
      ) : (
        <TakeFood
          idNumber={values.id_number}
          checked={checked}
          page={page}
          onDone={setDone}
          onStartAgain={nextStudent}
          onLoggedOut={forget}
        />
      )}
    </div>
  )
}

function TakeFood({
  idNumber,
  checked,
  page,
  onDone,
  onStartAgain,
  onLoggedOut,
}: {
  idNumber: string
  checked: WalkInCheck
  page: CounterPage
  onDone: (done: WalkInDone) => void
  onStartAgain: () => void
  onLoggedOut: () => void
}) {
  const [food, setFood] = useState<Chosen>({})
  const [extras, setExtras] = useState<Record<number, number>>({})
  const [cancelBooking, setCancelBooking] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const nothing = total(food) === 0 && Object.keys(extras).length === 0

  async function record() {
    setProblem(null)
    setSending(true)
    const answer = await send<WalkInDone>('/api/walk-ins', {
      id_number: idNumber,
      food: asChoices(food),
      extras: Object.values(extras),
      cancel_booking: cancelBooking,
    })
    setSending(false)
    if (answer.ok) return onDone(answer.data)
    if (answer.status === 401) return onLoggedOut()
    setProblem(answer.message)
  }

  return (
    <>
      <div className="done-box" role="status">
        They can be served.
        {checked.new_account && ' This is their first visit: recording it makes an account for their card.'}
      </div>
      {checked.cancels && (
        <div className="notice">
          <p>
            They have a booking for {showDate(checked.cancels.pickup_date)} (bag {checked.cancels.code}). Serving them now
            cancels it, and its food and time go back for someone else.
          </p>
          <label className="check">
            <input type="checkbox" checked={cancelBooking} onChange={(event) => setCancelBooking(event.target.checked)} />
            Cancel that booking and serve them now
          </label>
        </div>
      )}

      <section className="card">
        <h2 className="in-card">What they take</h2>
        <ShelfPicker
          lines={page.food}
          chosen={food}
          onChange={setFood}
          room={page.limits.item_limit}
          maxPerItem={page.limits.max_per_item}
        />
      </section>
      <section className="card">
        <h2 className="in-card">Extras</h2>
        <p className="muted">One of each.</p>
        <ExtrasPicker lines={page.extras} chosen={extras} onChange={setExtras} />
      </section>

      <div className="book-bar">
        <Problem message={problem} />
        <p className="actions">
          <button
            type="button"
            onClick={record}
            disabled={sending || nothing || (checked.cancels !== null && !cancelBooking)}
          >
            {sending ? 'Saving...' : 'Record the walk-in'}
          </button>
          <button type="button" className="link-button" onClick={onStartAgain}>
            Start again
          </button>
        </p>
      </div>
    </>
  )
}
