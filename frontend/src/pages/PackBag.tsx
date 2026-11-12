import { useCallback, useEffect, useState, type ReactNode } from 'react'
import { Link, useParams } from 'react-router'
import { send, type Answer, type Bag, type BagFood, type BagSubstitute, type PackingPlan, type WhoIsPacking } from '../api.ts'
import { Problem } from '../forms.tsx'
import { useMe } from '../me.ts'
import { showClock, showDate } from '../time.ts'
import {
  foodKey,
  forgetProgress,
  foundAfterAll,
  keepProgress,
  lookedKey,
  needsALook,
  outcomeWords,
  startingProgress,
  STATUS_WORDS,
  stillToTick,
  substituteKey,
  withMissing,
  withNotOnShelf,
  withPicked,
  type Findings,
  type Picked,
} from './packingTools.ts'
import { PageHeading } from '../PageHeading.tsx'

// Packing one bag (U4-U8). The volunteer taps "Picked" as each thing goes in the
// bag, and "Out of stock" for anything that isn't there. After each Out of stock
// the server works out what goes in instead (the refill rule) and what to write on
// the sticky note. Nothing is saved until Packed, so a wrong tap is just tapped
// again. Packed waits until every line is Picked or Out of stock (decided 11 Nov).
// Food another volunteer marked out of stock opens marked, but needs one look:
// Still out of stock, or Found it (decided 12 Nov). Found it takes the warning
// off every other bag too, once this one is Packed (decided 12 Nov, later).
// Every tap is kept on this phone until Packed, so a reload doesn't lose them.

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
      <PageHeading>
        Bag <span className="bag-code">{bag.code}</span>
      </PageHeading>
      <p className="lead">
        Pickup {showDate(bag.pickup_date)} at {showClock(bag.starts_at)} · {STATUS_WORDS[bag.status] ?? bag.status}
      </p>
      {notice && <p className="notice">{notice}</p>}
      {bag.status === 'booked' && bag.can_pack ? (
        <SomeoneElseFirst key={bag.id} bag={bag} onChanged={askAgain} onLoggedOut={forget}>
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
        </SomeoneElseFirst>
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

// ---------- who is packing it (decided 12 Nov) ----------

type Start = { state: 'asking' } | { state: 'yours' } | { state: 'someone else'; who: WhoIsPacking }

/**
 * Tells the server this volunteer is packing the bag, so the queue says
 * "Sam is packing". If someone else opened it first, it warns before showing
 * the packing page, so nobody fills a second bag for the same booking.
 */
function SomeoneElseFirst({
  bag,
  onChanged,
  onLoggedOut,
  children,
}: {
  bag: Bag
  onChanged: () => void
  onLoggedOut: () => void
  children: ReactNode
}) {
  const [start, setStart] = useState<Start>({ state: 'asking' })
  const [problem, setProblem] = useState<string | null>(null)

  function answered(answer: Answer<WhoIsPacking>) {
    if (answer.ok) {
      return setStart(answer.data.yours ? { state: 'yours' } : { state: 'someone else', who: answer.data })
    }
    if (answer.status === 401) return onLoggedOut()
    // 409: packed already, by someone else. Show the bag as it is now.
    if (answer.status === 409) return onChanged()
    setProblem(answer.message)
  }

  // Once, when the bag opens.
  useEffect(() => {
    let stillWanted = true
    send<WhoIsPacking>(`/api/packing/bags/${bag.id}/start`, { anyway: false }).then((answer) => {
      if (!stillWanted) return
      // The same as answered() below, written out: an effect may only use what it lists.
      if (answer.ok) {
        return setStart(answer.data.yours ? { state: 'yours' } : { state: 'someone else', who: answer.data })
      }
      if (answer.status === 401) return onLoggedOut()
      if (answer.status === 409) return onChanged()
      setProblem(answer.message)
    })
    return () => {
      stillWanted = false
    }
  }, [bag.id, onChanged, onLoggedOut])

  async function packAnyway() {
    answered(await send<WhoIsPacking>(`/api/packing/bags/${bag.id}/start`, { anyway: true }))
  }

  if (problem) return <p className="problem">{problem}</p>
  if (start.state === 'asking') return <p className="muted">Asking the server...</p>
  if (start.state === 'yours') return <>{children}</>
  const { who } = start
  return (
    <section className="undo-box card" role="alert">
      <h2 className="in-card">{who.by} is packing this bag</h2>
      <p>
        {/* No full stop after the time: it ends in "p.m." already. */}
        {who.by} opened it at {showClock(who.since)} Check with {who.by} before you pack it, so the student doesn't
        get two bags' worth of food.
      </p>
      <p className="actions">
        <button type="button" className="danger" onClick={() => void packAnyway()}>
          Pack it anyway
        </button>
        <Link to="/packing">Back to the queue</Link>
      </p>
    </section>
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
  // The taps kept on this phone if the page reloaded, or a fresh start.
  const [start] = useState(() => startingProgress(bag))
  const [findings, setFindings] = useState<Findings>(start.findings)
  // What's in the bag so far. Not sent to the server, so ticking asks for no new plan.
  const [picked, setPicked] = useState<Picked>(start.picked)
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

  // Every tap is kept on this phone until Packed, so a reload doesn't lose it.
  useEffect(() => keepProgress(bag.id, findings, picked), [bag.id, findings, picked])

  // Packed only goes with a plan worked out for exactly what's on screen.
  const current = plan !== null && plan.for === findings ? plan.plan : null

  const toTick = current === null ? null : stillToTick(bag, findings, current, picked)

  // A line that changes between Picked and Out of stock is unticked: whatever
  // the volunteer finds next, they tap again.
  function change(next: Findings, untick: string) {
    setProblem(null)
    setFindings(next)
    setPicked((old) => withPicked(old, untick, false))
  }

  /** A change to a booked food line. Any change means the volunteer has looked at the shelf. */
  function changeFood(next: Findings, varietyId: number) {
    change(next, foodKey(varietyId))
    setPicked((old) => withPicked(old, lookedKey(varietyId), true))
  }

  function tick(key: string, on: boolean) {
    setProblem(null)
    setPicked((old) => withPicked(old, key, on))
  }

  async function packed() {
    if (current === null) return
    setSending(true)
    const answer = await send<Bag>(`/api/packing/bags/${bag.id}/packed`, {
      ...findings,
      uses: current.uses,
      found: foundAfterAll(bag, findings),
    })
    setSending(false)
    if (answer.ok) {
      forgetProgress(bag.id)
      return onPacked(answer.data)
    }
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
        <p className="muted">Tap "Picked" as each thing goes in the bag, or "Out of stock" if it isn't there.</p>
        <ul className="pack-list">
          {bag.food.map((line) => (
            <FoodRow
              key={line.variety_id}
              line={line}
              missing={howManyMissing(line)}
              picked={picked.has(foodKey(line.variety_id))}
              toLook={needsALook(line, findings, picked)}
              onPicked={(on) => tick(foodKey(line.variety_id), on)}
              onStillOut={() => tick(lookedKey(line.variety_id), true)}
              onChange={(howMany) => changeFood(withMissing(findings, line.variety_id, howMany), line.variety_id)}
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
                picked={picked.has(substituteKey(line.variety_id))}
                onPicked={(on) => tick(substituteKey(line.variety_id), on)}
                onNone={(none) =>
                  change(withNotOnShelf(findings, line.variety_id, none), substituteKey(line.variety_id))
                }
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
            {toTick !== null && toTick > 0 && (
              <>
                {' '}
                <strong>
                  {toTick === 1 ? '1 line' : `${toTick} lines`} still to tick, then press Packed.
                </strong>
              </>
            )}
          </p>
        )}
        <button type="button" onClick={packed} disabled={current === null || toTick !== 0 || sending}>
          {sending ? 'Saving...' : 'Packed'}
        </button>
      </div>
    </>
  )
}

/**
 * Ticks a line as in the bag. It's a toggle, so a screen reader says "pressed"
 * once it's ticked, and tapping again unticks it.
 */
function PickedButton({ name, picked, onPicked }: { name: string; picked: boolean; onPicked: (on: boolean) => void }) {
  return (
    <button
      type="button"
      className={picked ? undefined : 'secondary'}
      aria-pressed={picked}
      aria-label={`Picked: ${name}`}
      onClick={() => onPicked(!picked)}
    >
      {picked && <span aria-hidden="true">✓ </span>}
      Picked
    </button>
  )
}

function FoodRow({
  line,
  missing,
  picked,
  toLook,
  onPicked,
  onStillOut,
  onChange,
}: {
  line: BagFood
  missing: number
  picked: boolean
  // Another volunteer marked it out of stock, and nobody has looked on this bag yet.
  toLook: boolean
  onPicked: (on: boolean) => void
  onStillOut: () => void
  onChange: (howMany: number) => void
}) {
  const onShelf = line.quantity - missing
  const allOut = missing === line.quantity
  const rowClass = allOut || (missing > 0 && !picked) ? 'pack-row pack-row-missing' : picked ? 'pack-row pack-row-use' : 'pack-row'
  return (
    <li className={rowClass}>
      <span className="pack-name">
        <strong>{line.variety}</strong>
        <span className="muted">{line.item}</span>
        {line.quantity > 1 && <span>× {line.quantity}</span>}
        {picked && !allOut && <span className="pack-state pack-state-use">In the bag</span>}
        {missing > 0 && (
          <span className="pack-state">
            {toLook ? 'Marked out of stock earlier' : allOut ? 'Out of stock' : `${missing} out of stock`}
          </span>
        )}
      </span>
      {line.quantity === 1 ? (
        allOut ? (
          <span className="pack-buttons">
            {toLook && <StillOutButton name={line.variety} onStillOut={onStillOut} />}
            <button type="button" className="secondary" aria-label={`Found it: ${line.variety}`} onClick={() => onChange(0)}>
              Found it
            </button>
          </span>
        ) : (
          <span className="pack-buttons">
            <PickedButton name={line.variety} picked={picked} onPicked={onPicked} />
            {!picked && (
              <button
                type="button"
                className="secondary"
                aria-label={`Out of stock: ${line.variety}`}
                onClick={() => onChange(1)}
              >
                Out of stock
              </button>
            )}
          </span>
        )
      ) : (
        <span className="pack-buttons">
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
          {toLook && <StillOutButton name={line.variety} onStillOut={onStillOut} />}
          {onShelf > 0 && <PickedButton name={line.variety} picked={picked} onPicked={onPicked} />}
        </span>
      )}
      {line.ran_out_at && (
        <span className="hint pack-hint">
          {/* No full stop after the time: it ends in "a.m." or "p.m." already. */}
          A volunteer marked this out of stock at {showClock(line.ran_out_at)}{' '}
          {toLook
            ? line.quantity === 1
              ? 'Have a quick look on the shelf, then tap Still out of stock or Found it.'
              : 'Have a quick look on the shelf, then tap Still out of stock or choose how many are there.'
            : missing === 0
              ? 'You found it, so Packed takes this warning off every other bag too.'
              : line.quantity === 1
                ? 'If there is some, tap Found it.'
                : 'If there is some, choose how many are on the shelf.'}
        </span>
      )}
    </li>
  )
}

/** For food someone else marked out of stock: "I looked, and there's still none." */
function StillOutButton({ name, onStillOut }: { name: string; onStillOut: () => void }) {
  return (
    <button type="button" className="secondary" aria-label={`Still out of stock: ${name}`} onClick={onStillOut}>
      Still out of stock
    </button>
  )
}

function SubstituteRow({
  line,
  plan,
  picked,
  onPicked,
  onNone,
}: {
  line: BagSubstitute
  plan: PackingPlan | null
  picked: boolean
  onPicked: (on: boolean) => void
  onNone: (none: boolean) => void
}) {
  const planned = plan?.substitutes.find((substitute) => substitute.variety_id === line.variety_id)
  const outcome = planned?.outcome
  const goesIn = outcome === 'use'
  // Picked earlier, but the plan changed (say the booked food was found after all).
  const takeOut = picked && planned !== undefined && !goesIn
  const rowClass = takeOut || outcome === 'not_on_shelf' ? 'pack-row-missing' : goesIn ? 'pack-row-use' : undefined
  return (
    <li className={rowClass}>
      <span className="pack-name">
        <strong>{line.variety}</strong>
        <span className="muted">{line.item}</span>
        {takeOut ? (
          <span className="pack-state">Not needed now: take it out of the bag</span>
        ) : (
          planned && (
            <span className={goesIn ? 'pack-state pack-state-use' : 'pack-state pack-state-skip'}>
              {goesIn && picked ? `In the bag, for ${planned.replaces}` : outcomeWords(planned.outcome, line.item, planned.replaces)}
            </span>
          )
        )}
      </span>
      {goesIn && (
        <span className="pack-buttons">
          <PickedButton name={line.variety} picked={picked} onPicked={onPicked} />
          {!picked && (
            <button
              type="button"
              className="secondary"
              aria-label={`Out of stock: ${line.variety}`}
              onClick={() => onNone(true)}
            >
              Out of stock
            </button>
          )}
        </span>
      )}
      {takeOut && (
        <button type="button" className="secondary" onClick={() => onPicked(false)}>
          Taken out
        </button>
      )}
      {outcome === 'not_on_shelf' && (
        <button type="button" className="secondary" aria-label={`Found it: ${line.variety}`} onClick={() => onNone(false)}>
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
                    {line.missing === line.quantity ? 'Out of stock' : `${line.missing} out of stock`}
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
