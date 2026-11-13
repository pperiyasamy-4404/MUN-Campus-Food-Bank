import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { send, type BagAtCounter, type HandedOver, type ShelfFood } from '../api.ts'
import { Field, Problem } from '../forms.tsx'
import { useMe } from '../me.ts'
import { showClock, showDate } from '../time.ts'
import { CounterNav, ExtrasPicker, ShelfPicker } from './CounterParts.tsx'
import { asChoices, total, useCounterPage, type Chosen } from './counterTools.ts'
import { PageHeading } from '../PageHeading.tsx'
import { Loading } from '../ui/Loading.tsx'

// Handing over a booked bag (P5, B3, U6, E3). The student says their code, the
// volunteer finds the bag, adds any extras they ask for, types the number on
// their MUN card, and hands the bag over. The server checks the card matches.
// No code (a dead phone, say)? The bag can be found by the card instead (decided 12 Nov).

export function HandOver() {
  const { forget } = useMe()
  const [version, setVersion] = useState(0)
  const load = useCounterPage(version, forget)
  const [code, setCode] = useState('')
  const [byCard, setByCard] = useState(false)
  const [card, setCard] = useState('')
  // The card the bag was found by: already typed, so the hand-over box starts with it.
  const [foundByCard, setFoundByCard] = useState('')
  const [bag, setBag] = useState<BagAtCounter | null>(null)
  const [done, setDone] = useState<HandedOver | null>(null)
  const [problem, setProblem] = useState<string | null>(null)
  const [finding, setFinding] = useState(false)

  async function find(event: FormEvent) {
    event.preventDefault()
    setProblem(null)
    setBag(null)
    setFinding(true)
    const answer = byCard
      ? await send<BagAtCounter>('/api/counter/find-by-card', { id_number: card })
      : await send<BagAtCounter>('/api/counter/find', { code })
    setFinding(false)
    if (answer.ok) {
      setFoundByCard(byCard ? card : '')
      return setBag(answer.data)
    }
    if (answer.status === 401) return forget()
    setProblem(answer.fields.code ?? answer.fields.id_number ?? answer.message)
  }

  function switchWay() {
    setByCard(!byCard)
    setProblem(null)
    setBag(null)
  }

  function nextStudent() {
    setCode('')
    setCard('')
    setFoundByCard('')
    setByCard(false)
    setBag(null)
    setDone(null)
    setProblem(null)
    // The shelf changed: ask for it again.
    setVersion((old) => old + 1)
  }

  if (load.state === 'loading') return <Loading shape="page" />
  if (load.state === 'failed') return <p className="problem">Could not get the counter. Is the server running?</p>
  const { page } = load

  return (
    <div>
      <CounterNav />
      <PageHeading>Hand over a bag</PageHeading>
      {!page.is_open && <p className="notice">{page.why_not}</p>}

      {done ? (
        <div className="code-box narrow-wide" role="status">
          <h2>Bag {done.code} handed over</h2>
          <p>Their next pickup can be on {showDate(done.next_pickup_on)}.</p>
          <button type="button" onClick={nextStudent}>
            Next student
          </button>
        </div>
      ) : (
        <>
          <form className="find-form" onSubmit={find} noValidate autoComplete="off">
            <Problem message={problem} />
            {byCard ? (
              <Field
                key="card"
                label="MUN card number"
                hint="From the student's card, when they don't have their code. No card, no food: a student who lost it gets a new MUN card first."
                inputMode="numeric"
                value={card}
                onChange={setCard}
                maxLength={12}
              />
            ) : (
              <Field
                key="code"
                label="Booking code"
                hint="The student says it, like K3P."
                className="code-input"
                value={code}
                onChange={(value) => setCode(value.toUpperCase())}
                maxLength={10}
              />
            )}
            <span className="actions">
              <button type="submit" disabled={finding || (byCard ? card : code).trim() === ''}>
                {finding ? 'Finding...' : 'Find the bag'}
              </button>
              <button type="button" className="link-button" onClick={switchWay}>
                {byCard ? 'Use the booking code instead' : 'No code? Use their MUN card'}
              </button>
            </span>
          </form>
          {bag && (
            <TheBag
              key={bag.id}
              bag={bag}
              food={page.food}
              extras={page.extras}
              maxPerItem={page.limits.max_per_item}
              cardTyped={foundByCard}
              onDone={setDone}
              onChanged={setBag}
              onLoggedOut={forget}
            />
          )}
        </>
      )}
    </div>
  )
}

function TheBag({
  bag,
  food,
  extras,
  maxPerItem,
  cardTyped,
  onDone,
  onChanged,
  onLoggedOut,
}: {
  bag: BagAtCounter
  food: ShelfFood[]
  extras: ShelfFood[]
  maxPerItem: number
  // The card the bag was found by, if it was. Empty otherwise.
  cardTyped: string
  onDone: (done: HandedOver) => void
  onChanged: (bag: BagAtCounter) => void
  onLoggedOut: () => void
}) {
  const [choices, setChoices] = useState<Chosen>({})
  const [chosenExtras, setChosenExtras] = useState<Record<number, number>>({})
  const [card, setCard] = useState(cardTyped)
  const [problem, setProblem] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [sending, setSending] = useState(false)

  const alreadyByItem: Record<number, number> = {}
  for (const thing of bag.contents) alreadyByItem[thing.item_id] = (alreadyByItem[thing.item_id] ?? 0) + thing.quantity

  async function handOver(event: FormEvent) {
    event.preventDefault()
    setProblem(null)
    setFields({})
    setSending(true)
    const answer = await send<HandedOver>('/api/counter/pickups', {
      code: bag.code,
      id_number: card,
      choices: asChoices(choices),
      extras: Object.values(chosenExtras),
    })
    setSending(false)
    if (answer.ok) return onDone(answer.data)
    if (answer.status === 401) return onLoggedOut()
    setProblem(answer.message)
    setFields(answer.fields)
    // 409: the bag changed (picked up already, or someone took the last of an extra). Show it as it is now.
    if (answer.status === 409) {
      const again = await send<BagAtCounter>('/api/counter/find', { code: bag.code })
      if (again.ok) onChanged(again.data)
    }
  }

  return (
    <section className="card">
      <header className="card-header">
        <h2 className="in-card">
          Bag <span className="bag-code">{bag.code}</span>
        </h2>
        <span className="muted">
          {showClock(bag.starts_at)}
          {bag.packed_by && ` · packed by ${bag.packed_by}`}
        </span>
      </header>

      {bag.why_not && (
        <p className="notice">
          {bag.why_not}{' '}
          {bag.status === 'booked' && <Link to={`/packing/${bag.id}`}>Pack it now</Link>}
        </p>
      )}

      <h3>In the bag</h3>
      <ul className="pack-list">
        {bag.contents.map((thing) => (
          <li key={`${thing.item_id}-${thing.variety}`} className="pack-row">
            <span className="pack-name">
              <strong>{thing.variety}</strong>
              <span className="muted">{thing.item}</span>
              {thing.quantity > 1 && <span>× {thing.quantity}</span>}
            </span>
          </li>
        ))}
      </ul>
      {bag.given_at_counter.length > 0 && (
        <>
          <h3>Also given at the counter</h3>
          <ul className="pack-list">
            {bag.given_at_counter.map((thing) => (
              <li key={thing.variety} className="pack-row">
                <span className="pack-name">
                  <strong>{thing.variety}</strong>
                  <span className="muted">{thing.is_extra ? `${thing.item}, an extra` : thing.item}</span>
                  {thing.quantity > 1 && <span>× {thing.quantity}</span>}
                </span>
              </li>
            ))}
          </ul>
        </>
      )}
      {bag.sticky_note.length > 0 && (
        <>
          <p className="muted">The sticky note on the bag says:</p>
          <div className="sticky-note">
            {bag.sticky_note.map((line, n) => (
              <p key={n}>{line}</p>
            ))}
          </div>
        </>
      )}

      {bag.why_not === null && (
        <form onSubmit={handOver} noValidate autoComplete="off">
          {bag.short > 0 && (
            <>
              <h3>
                The bag is {bag.short} short: they choose {bag.short === 1 ? 'something' : `${bag.short} things`} from the
                shelf
              </h3>
              <ShelfPicker
                lines={food}
                chosen={choices}
                onChange={setChoices}
                room={bag.short}
                maxPerItem={maxPerItem}
                alreadyByItem={alreadyByItem}
              />
            </>
          )}

          <h3>Extras they ask for</h3>
          <p className="muted">One of each.</p>
          <ExtrasPicker lines={extras} chosen={chosenExtras} onChange={setChosenExtras} />

          <h3>Check their MUN card</h3>
          <Problem message={problem} />
          <Field
            label="ID number on their MUN card"
            hint="Type it from the card itself. It must match the booking. If it doesn't, or there's no card, don't hand over the bag."
            inputMode="numeric"
            value={card}
            onChange={setCard}
            error={fields.id_number}
          />
          <button type="submit" disabled={sending || card.trim() === ''} aria-busy={sending}>
            {sending
              ? 'Saving...'
              : `Hand over bag ${bag.code}${total(choices) + Object.keys(chosenExtras).length > 0 ? ' with the extra food' : ''}`}
          </button>
        </form>
      )}
    </section>
  )
}
