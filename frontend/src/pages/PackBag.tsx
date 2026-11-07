import { useCallback, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router'
import { send, type Bag, type BagFood, type BagSubstitute, type PackingPlan } from '../api.ts'
import { Problem } from '../forms.tsx'
import { useMe } from '../me.ts'
import { showClock, showDate } from '../time.ts'
import {
  outcomeWords,
  startingFindings,
  STATUS_WORDS,
  withMissing,
  withNotOnShelf,
  type Findings,
} from './packingTools.ts'

// Packing one bag (U4-U8). The volunteer puts in the booked food and taps
// "None on the shelf" for anything that isn't there. After each tap the server
// works out what goes in instead (the refill rule) and what to write on the
// sticky note. Nothing is saved until Packed, so a wrong tap is just tapped again.

type Load = { state: 'loading' } | { state: 'failed'; message: string } | { state: 'ready'; bag: Bag }

export function PackBag() {
  const { bookingId } = useParams()
  const { forget } = useMe()
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [version, setVersion] = useState(0)
  // Something to tell the volunteer after the bag changes, like "Packed is undone."
  const [notice, setNotice] = useState<string | null>(null)
  const askAgain = useCallback(() => setVersion((old) => old + 1), [])

  useEffect(() => {
    let stillWanted = true
    fetch(`/api/packing/bags/${bookingId}`)
      .then(async (response) => {
        if (response.status === 401) return stillWanted && forget()
        if (response.status === 404) throw new Error("There's no bag with that number.")
        if (!response.ok) throw new Error('Could not get the bag. Is the server running?')
        const bag = (await response.json()) as Bag
        if (stillWanted) setLoad({ state: 'ready', bag })
      })
      .catch((error: Error) => {
        if (stillWanted) setLoad({ state: 'failed', message: error.message })
      })
    return () => {
      stillWanted = false
    }
  }, [bookingId, version, forget])

  if (load.state === 'loading') return <p className="muted">Asking the server...</p>
  if (load.state === 'failed') {
    return (
      <div>
        <BackToQueue />
        <p className="problem">{load.message}</p>
      </div>
    )
  }

  const { bag } = load
  return (
    <div>
      <BackToQueue />
      <h1>
        Bag <span className="bag-code">{bag.code}</span>
      </h1>
      <p className="lead">
        Pickup {showDate(bag.pickup_date)} at {showClock(bag.starts_at)} · {STATUS_WORDS[bag.status] ?? bag.status}
      </p>
      {notice && <p className="notice">{notice}</p>}
      {bag.status === 'booked' && bag.can_pack ? (
        <Packer
          key={bag.id}
          bag={bag}
          onPacked={(packed) => {
            setNotice(null)
            setLoad({ state: 'ready', bag: packed })
          }}
          onChanged={askAgain}
          onLoggedOut={forget}
        />
      ) : (
        <BagAsItIs
          bag={bag}
          onUnpacked={(unpacked) => {
            setNotice(
              'Packed is undone. Take the substitutes out and put them back on the shelf, and throw away the ' +
                'sticky note. The bag is back in the queue, to pack again.',
            )
            setLoad({ state: 'ready', bag: unpacked })
            // The message is at the top, and the Undo button was at the bottom.
            window.scrollTo(0, 0)
          }}
          onLoggedOut={forget}
        />
      )}
    </div>
  )
}

function BackToQueue() {
  return (
    <p className="back">
      <Link to="/packing">← Packing queue</Link>
    </p>
  )
}

// ---------- packing it ----------

function Packer({
  bag,
  onPacked,
  onChanged,
  onLoggedOut,
}: {
  bag: Bag
  onPacked: (bag: Bag) => void
  onChanged: () => void
  onLoggedOut: () => void
}) {
  const [findings, setFindings] = useState<Findings>(() => startingFindings(bag))
  // The server's plan, and which findings it was worked out for.
  const [plan, setPlan] = useState<{ for: Findings; plan: PackingPlan } | null>(null)
  const [planVersion, setPlanVersion] = useState(0)
  const [problem, setProblem] = useState<string | null>(null)
  const [sending, setSending] = useState(false)

  // Each change asks the server what goes in instead. If the volunteer taps
  // quickly, only the answer for the latest findings is kept.
  useEffect(() => {
    let stillWanted = true
    send<PackingPlan>(`/api/packing/bags/${bag.id}/plan`, findings).then((answer) => {
      if (!stillWanted) return
      if (answer.ok) return setPlan({ for: findings, plan: answer.data })
      if (answer.status === 401) return onLoggedOut()
      setProblem(answer.message)
      // 409: someone else packed this bag. Show it as it is now.
      if (answer.status === 409) onChanged()
    })
    return () => {
      stillWanted = false
    }
  }, [bag.id, findings, planVersion, onLoggedOut, onChanged])

  // Packed only goes with a plan worked out for exactly what's on screen.
  const current = plan !== null && plan.for === findings ? plan.plan : null

  function change(next: Findings) {
    setProblem(null)
    setFindings(next)
  }

  async function packed() {
    if (current === null) return
    setSending(true)
    const answer = await send<Bag>(`/api/packing/bags/${bag.id}/packed`, { ...findings, uses: current.uses })
    setSending(false)
    if (answer.ok) return onPacked(answer.data)
    if (answer.status === 401) return onLoggedOut()
    setProblem(answer.message)
    // 409: the plan changed (another bag took the last of a substitute), or someone else
    // packed this bag. Ask again: the new plan says what to put in now, or the bag shows as packed.
    if (answer.status === 409) {
      setPlanVersion((old) => old + 1)
      onChanged()
    }
  }

  const howManyMissing = (line: BagFood) =>
    findings.missing.find((missing) => missing.variety_id === line.variety_id)?.how_many ?? 0

  return (
    <>
      <section className="card">
        <h2 className="in-card">1. Put in the food</h2>
        <p className="muted">Tap "None on the shelf" for anything that isn't there.</p>
        <ul className="pack-list">
          {bag.food.map((line) => (
            <FoodRow
              key={line.variety_id}
              line={line}
              missing={howManyMissing(line)}
              onChange={(howMany) => change(withMissing(findings, line.variety_id, howMany))}
            />
          ))}
        </ul>
      </section>

      <section className="card">
        <h2 className="in-card">2. Substitutes, best first</h2>
        {bag.substitutes.length === 0 ? (
          <p className="muted">The student didn't list any.</p>
        ) : (
          <ol className="ranked">
            {bag.substitutes.map((line) => (
              <SubstituteRow
                key={line.variety_id}
                line={line}
                plan={current}
                onNone={(none) => change(withNotOnShelf(findings, line.variety_id, none))}
              />
            ))}
          </ol>
        )}
      </section>

      <section className="card">
        <h2 className="in-card">3. The sticky note</h2>
        <StickyNote plan={current} />
      </section>

      <div className="book-bar">
        <Problem message={problem} />
        {current && (
          <p className="muted">
            {current.in_bag} of {current.booked} things in the bag.
          </p>
        )}
        <button type="button" onClick={packed} disabled={current === null || sending}>
          {sending ? 'Saving...' : 'Packed'}
        </button>
      </div>
    </>
  )
}

function FoodRow({ line, missing, onChange }: { line: BagFood; missing: number; onChange: (howMany: number) => void }) {
  const onShelf = line.quantity - missing
  return (
    <li className={missing > 0 ? 'pack-row pack-row-missing' : 'pack-row'}>
      <span className="pack-name">
        <strong>{line.variety}</strong>
        <span className="muted">{line.item}</span>
        {line.quantity > 1 && <span>× {line.quantity}</span>}
        {missing > 0 && (
          <span className="pack-state">{missing === line.quantity ? 'None on the shelf' : `${missing} missing`}</span>
        )}
      </span>
      {line.quantity === 1 ? (
        <button type="button" className="secondary" onClick={() => onChange(missing > 0 ? 0 : 1)}>
          {missing > 0 ? 'Found it' : 'None on the shelf'}
        </button>
      ) : (
        <label className="on-shelf">
          On the shelf{' '}
          <select value={onShelf} onChange={(event) => onChange(line.quantity - Number(event.target.value))}>
            {Array.from({ length: line.quantity + 1 }, (_, n) => line.quantity - n).map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </label>
      )}
      {line.ran_out_at && (
        <span className="hint pack-hint">
          {/* No full stop after the time: it ends in "a.m." or "p.m." already. */}
          A volunteer found none on the shelf at {showClock(line.ran_out_at)} If there is some, tap Found it.
        </span>
      )}
    </li>
  )
}

function SubstituteRow({
  line,
  plan,
  onNone,
}: {
  line: BagSubstitute
  plan: PackingPlan | null
  onNone: (none: boolean) => void
}) {
  const planned = plan?.substitutes.find((substitute) => substitute.variety_id === line.variety_id)
  const outcome = planned?.outcome
  return (
    <li className={outcome === 'use' ? 'pack-row-use' : outcome === 'not_on_shelf' ? 'pack-row-missing' : undefined}>
      <span className="pack-name">
        <strong>{line.variety}</strong>
        <span className="muted">{line.item}</span>
        {planned && (
          <span className={outcome === 'use' ? 'pack-state pack-state-use' : 'pack-state pack-state-skip'}>
            {outcomeWords(planned.outcome, line.item, planned.replaces)}
          </span>
        )}
      </span>
      {outcome === 'use' && (
        <button type="button" className="secondary" onClick={() => onNone(true)}>
          None on the shelf
        </button>
      )}
      {outcome === 'not_on_shelf' && (
        <button type="button" className="secondary" onClick={() => onNone(false)}>
          Found it
        </button>
      )}
    </li>
  )
}

function StickyNote({ plan }: { plan: PackingPlan | null }) {
  if (plan === null) return <p className="muted">Working it out...</p>
  if (plan.sticky_note.length === 0) return <p>Nothing was swapped, so the bag needs no note.</p>
  const short = plan.booked - plan.in_bag
  return (
    <>
      <p>Write this on a sticky note and put it on the bag:</p>
      <NoteLines lines={plan.sticky_note} />
      {short > 0 && (
        <p className="notice">
          The substitutes ran out too, so the bag is {short} short. At pickup, the student chooses{' '}
          {short === 1 ? 'something' : `${short} things`} from the shelf instead.
        </p>
      )}
    </>
  )
}

function NoteLines({ lines }: { lines: string[] }) {
  return (
    <div className="sticky-note">
      {lines.map((line, n) => (
        <p key={n}>{line}</p>
      ))}
    </div>
  )
}

// ---------- packed already, or can't be packed yet ----------

function BagAsItIs({
  bag,
  onUnpacked,
  onLoggedOut,
}: {
  bag: Bag
  onUnpacked: (bag: Bag) => void
  onLoggedOut: () => void
}) {
  const packed = bag.packed_at !== null
  return (
    <>
      {packed && bag.packed_at && (
        <p className="done-box" role="status">
          {/* No full stop: the time ends in "p.m." already. */}
          Packed by {bag.packed_by} at {showClock(bag.packed_at)}
        </p>
      )}
      {!packed && bag.why_not && <p className="notice">{bag.why_not}</p>}

      <section className="card">
        <h2 className="in-card">Food</h2>
        <ul className="pack-list">
          {bag.food.map((line) => (
            <li key={line.variety_id} className={line.missing > 0 ? 'pack-row pack-row-missing' : 'pack-row'}>
              <span className="pack-name">
                <strong>{line.variety}</strong>
                <span className="muted">{line.item}</span>
                {line.quantity > 1 && <span>× {line.quantity}</span>}
                {line.missing > 0 && (
                  <span className="pack-state">
                    {line.missing === line.quantity ? "Wasn't on the shelf" : `${line.missing} weren't on the shelf`}
                  </span>
                )}
              </span>
            </li>
          ))}
        </ul>
      </section>

      {bag.substitutes.length > 0 && (
        <section className="card">
          <h2 className="in-card">Substitutes</h2>
          <ol className="ranked">
            {bag.substitutes.map((line) => (
              <li key={line.variety_id} className={line.replaced ? 'pack-row-use' : undefined}>
                <span className="pack-name">
                  <strong>{line.variety}</strong>
                  <span className="muted">{line.item}</span>
                  {line.replaced && <span className="pack-state pack-state-use">Went in, for {line.replaced}</span>}
                </span>
              </li>
            ))}
          </ol>
        </section>
      )}

      {packed && (
        <section className="card">
          <h2 className="in-card">The sticky note</h2>
          {bag.sticky_note.length === 0 ? <p>Nothing was swapped.</p> : <NoteLines lines={bag.sticky_note} />}
        </section>
      )}

      <p>
        <Link className="button" to="/packing">
          Back to the packing queue
        </Link>
      </p>

      {bag.can_unpack && <UndoPacked bag={bag} onUnpacked={onUnpacked} onLoggedOut={onLoggedOut} />}
    </>
  )
}

/** Packed the wrong bag? Undo it, until the bag is handed over (decided 7 Nov). Asks first. */
function UndoPacked({
  bag,
  onUnpacked,
  onLoggedOut,
}: {
  bag: Bag
  onUnpacked: (bag: Bag) => void
  onLoggedOut: () => void
}) {
  const [asking, setAsking] = useState(false)
  const [sending, setSending] = useState(false)
  const [problem, setProblem] = useState<string | null>(null)

  async function undo() {
    setSending(true)
    const answer = await send<Bag>(`/api/packing/bags/${bag.id}/unpack`)
    setSending(false)
    if (answer.ok) return onUnpacked(answer.data)
    if (answer.status === 401) return onLoggedOut()
    setProblem(answer.message)
  }

  if (!asking) {
    return (
      <p className="after-form">
        Pressed Packed on the wrong bag?{' '}
        <button type="button" className="link-button" onClick={() => setAsking(true)}>
          Undo Packed
        </button>
      </p>
    )
  }
  return (
    <div className="card undo-box">
      <p>
        <strong>Undo Packed on bag {bag.code}?</strong> It goes back to the queue, to pack again. Its substitutes go
        back on the shelf. This is logged with your name.
      </p>
      <Problem message={problem} />
      <p className="actions">
        <button type="button" className="danger" onClick={undo} disabled={sending}>
          {sending ? 'Undoing...' : 'Yes, undo Packed'}
        </button>
        <button type="button" className="link-button" onClick={() => setAsking(false)}>
          Cancel
        </button>
      </p>
    </div>
  )
}
