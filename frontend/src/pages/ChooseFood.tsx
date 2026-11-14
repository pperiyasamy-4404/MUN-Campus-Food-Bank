import { useEffect, useId, useRef, useState } from 'react'
import { send, type BookingDetails, type Food, type HeldTime, type Limits, type Variety } from '../api.ts'
import { FoodCard, FoodRow, StockNote } from '../FoodCards.tsx'
import { FoodGrid } from '../FoodList.tsx'
import { Problem } from '../forms.tsx'
import { showDayAndClock } from '../time.ts'
import { PageHeading } from '../PageHeading.tsx'
import { countVarieties, filterFood, type Diet } from '../foodFilter.ts'
import { BookingSteps } from '../ui/BookingSteps.tsx'
import { DietFilters } from '../ui/DietFilters.tsx'
import { Empty } from '../ui/Empty.tsx'
import { Icon } from '../ui/Icon.tsx'
import { holdLevel, holdShare } from '../ui/timing.ts'

// Stage 2 of booking: the time is held, a countdown runs, and the student
// chooses food and substitutes, then presses Book (S8, I3, U2).
//
// The limits are checked here so the buttons can say no straight away, and
// again on the server, which is what really decides.

type Line = { variety: Variety; item: string; itemKey: string }

export function ChooseFood({
  hold,
  limits,
  food,
  onBooked,
  onTimeUp,
  onStartOver,
  onFoodChanged,
  onLoggedOut,
}: {
  hold: HeldTime
  limits: Limits
  food: Food
  onBooked: () => void
  onTimeUp: () => void
  onStartOver: () => void
  onFoodChanged: () => void
  onLoggedOut: () => void
}) {
  const secondsLeft = useCountdown(hold.seconds_left, onTimeUp)
  // How many of each variety, by variety id.
  const [chosen, setChosen] = useState<Record<number, number>>({})
  // Variety ids, best first.
  const [substitutes, setSubstitutes] = useState<number[]>([])
  const [problem, setProblem] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  // "Ready to book?" (13 Nov night): Book opens a check first, so a stray tap never books.
  const [confirming, setConfirming] = useState(false)
  // The diet filters (13 Nov). They only change what's shown: chosen food stays chosen.
  const [diets, setDiets] = useState<Diet[]>([])
  const shown = filterFood(food.bookable, diets)

  // Every bookable variety, with its item, in the order the server sent them (A to Z).
  const lines: Line[] = food.bookable.flatMap((category) =>
    category.items.flatMap((item) =>
      item.varieties.map((variety) => ({ variety, item: item.name, itemKey: `${category.name}/${item.name}` })),
    ),
  )
  const total = Object.values(chosen).reduce((sum, count) => sum + count, 0)
  const ofItem = (itemKey: string) =>
    lines.filter((line) => line.itemKey === itemKey).reduce((sum, line) => sum + (chosen[line.variety.id] ?? 0), 0)

  function change(line: Line, by: number) {
    const now = chosen[line.variety.id] ?? 0
    const next = Math.max(0, now + by)
    setChosen((old) => {
      const updated = { ...old }
      if (next === 0) delete updated[line.variety.id]
      else updated[line.variety.id] = next
      return updated
    })
    // Something on the list can't also be a substitute (U2).
    if (next > 0) setSubstitutes((old) => old.filter((id) => id !== line.variety.id))
  }

  /** Why one more of this can't be added, or null if it can. */
  function whyNotMore(line: Line): string | null {
    const have = chosen[line.variety.id] ?? 0
    // No number (null): any number of students can book it (decided 12 Nov).
    if (line.variety.stock !== null && line.variety.stock <= have) return have === 0 ? 'Out of stock' : 'No more left'
    if (ofItem(line.itemKey) >= limits.max_per_item) {
      return limits.max_per_item === 1 ? `One ${line.item} only` : `${limits.max_per_item} ${line.item} at most`
    }
    if (total >= limits.item_limit) return 'Your list is full'
    return null
  }

  async function book() {
    setSending(true)
    const answer = await send<BookingDetails>('/api/bookings', {
      items: Object.entries(chosen).map(([id, quantity]) => ({ variety_id: Number(id), quantity })),
      substitutes,
    })
    setSending(false)
    if (answer.ok) return onBooked()
    setConfirming(false)
    if (answer.status === 401) return onLoggedOut()
    // 410: the held time is gone, so back to choosing a time.
    if (answer.status === 410) return onTimeUp()
    setProblem(answer.message)
    // 409: something changed while they chose, like food running out. Show the page as it is
    // now: their list stays, and if they turn out to be booked already, the booking shows.
    if (answer.status === 409) onFoodChanged()
  }

  async function startOver() {
    const answer = await send('/api/holds', {}, 'DELETE')
    if (!answer.ok && answer.status === 401) return onLoggedOut()
    onStartOver()
  }

  const substituteChoices = lines.filter(
    (line) => !(line.variety.id in chosen) && !substitutes.includes(line.variety.id) && line.variety.stock !== 0,
  )
  return (
    <div>
      <BookingSteps current={2} />
      <PageHeading>Choose your food</PageHeading>
      {/* One slim bar since 13 Nov night (it was three lines and a link): the time, the
          minutes left, the count, and a thin line that runs down. It stays at the top.
          Not a live region: it changes every second, and a screen reader would read
          every change. The hidden line below speaks only at a few moments. */}
      <div className={`hold-bar ${holdLevel(secondsLeft)}`}>
        <p className="visually-hidden" role="status">
          {timeLeftToSay(secondsLeft, limits.hold_minutes)}
        </p>
        <div className="hold-row">
          <span className="hold-when">
            <Icon name="clock" className="hold-icon" />
            <span>
              <strong>{showDayAndClock(hold.starts_at)}</strong>
              <span className="hold-left">
                {' '}
                · kept{' '}
                <strong className={secondsLeft < 60 ? 'time-short' : undefined}>{asMinutes(secondsLeft)}</strong>
              </span>
            </span>
          </span>
          <span className="hold-count">
            {total}/{limits.item_limit} food · {substitutes.length}/{limits.substitute_limit} substitutes
          </span>
          <button type="button" className="link-button hold-change" onClick={startOver}>
            Change time
          </button>
        </div>
        <div className="hold-meter" aria-hidden="true">
          <div
            className={`hold-meter-fill ${holdLevel(secondsLeft)}`}
            style={{ width: `${holdShare(secondsLeft, limits.hold_minutes) * 100}%` }}
          />
        </div>
      </div>

      <p className="muted choose-rules">
        Up to {limits.item_limit} things, and {limits.max_per_item === 1 ? 'one' : `up to ${limits.max_per_item}`} of
        each kind of food, counting all its varieties together.
      </p>

      <DietFilters
        chosen={diets}
        onChange={setDiets}
        showing={countVarieties(shown)}
        of={countVarieties(food.bookable)}
      />
      {shown.length === 0 && (
        <Empty icon="search" title="Nothing fits all of those">
          Try fewer filters. What you've already added stays on your list.
        </Empty>
      )}

      {shown.map((category) => (
        <section key={category.name} className="food-section">
          <h2 className="food-section-title">{category.name}</h2>
          <div className="food-grid">
            {category.items.map((item) => {
              const itemKey = `${category.name}/${item.name}`
              const chosenOfItem = ofItem(itemKey)
              return (
                <FoodCard
                  key={item.id}
                  name={item.name}
                  photoUrl={item.photo_url}
                  highlighted={chosenOfItem > 0}
                  badge={chosenOfItem > 0 ? `✓ ${chosenOfItem} chosen` : undefined}
                >
                  {item.varieties.map((variety) => {
                    const line = { variety, item: item.name, itemKey }
                    const have = chosen[variety.id] ?? 0
                    const notMore = whyNotMore(line)
                    return (
                      <FoodRow
                        key={variety.id}
                        name={variety.name}
                        tags={variety.tags}
                        dim={have === 0 && notMore !== null}
                        note={<StockNote stock={variety.stock} fewLeft={variety.few_left} />}
                      >
                        {limits.max_per_item === 1 ? (
                          have > 0 ? (
                            <button type="button" className="chosen-button" onClick={() => change(line, -1)}>
                              ✓ Added<span className="visually-hidden">. Remove {variety.name}</span>
                            </button>
                          ) : variety.stock === 0 ? null : notMore !== null ? (
                            // A reason, not a button: it can't be pressed, so it shouldn't look like it can.
                            <span className="why-not">{notMore}</span>
                          ) : (
                            <button type="button" className="add-button" onClick={() => change(line, 1)}>
                              Add<span className="visually-hidden"> {variety.name}</span>
                            </button>
                          )
                        ) : (
                          <span className="choose-controls">
                            <button type="button" className="secondary" disabled={have === 0} onClick={() => change(line, -1)} aria-label={`One less ${variety.name}`}>
                              −
                            </button>
                            <span className="count">{have}</span>
                            <button type="button" className="secondary" disabled={notMore !== null} onClick={() => change(line, 1)} aria-label={`One more ${variety.name}`}>
                              +
                            </button>
                          </span>
                        )}
                      </FoodRow>
                    )
                  })}
                </FoodCard>
              )
            })}
          </div>
        </section>
      ))}

      <Substitutes
        limit={limits.substitute_limit}
        ranked={substitutes.map((id) => lines.find((line) => line.variety.id === id)).filter((line) => line !== undefined)}
        choices={substituteChoices}
        onChange={setSubstitutes}
      />

      {/* The extras with their photos, like on the home page (13 Nov night): not booked,
          but the student sees what they can ask for at the counter. */}
      {food.extras.length > 0 && (
        <section className="food-section">
          <h2 className="food-section-title">Extras</h2>
          <p className="muted">Not booked online. Ask at the counter when you pick up your bag: one of each, while they last.</p>
          <FoodGrid categories={food.extras} empty="No extras today." extras />
        </section>
      )}

      {/* Slim since 13 Nov night: a small hint until something is chosen, then the
          count and one button. The button opens "Ready to book?" first. */}
      <div className={total === 0 ? 'book-bar book-bar-empty' : 'book-bar'}>
        <Problem message={problem} />
        {total === 0 ? (
          <p className="book-hint">Add food to your list, then book it here.</p>
        ) : (
          <div className="book-row">
            <span className="book-summary">
              <strong>
                {total} {total === 1 ? 'thing' : 'things'}
              </strong>
              {substitutes.length > 0 &&
                ` · ${substitutes.length} ${substitutes.length === 1 ? 'substitute' : 'substitutes'}`}
            </span>
            <button type="button" onClick={() => setConfirming(true)}>
              Book {total} {total === 1 ? 'thing' : 'things'}
            </button>
          </div>
        )}
      </div>

      {confirming && (
        <ConfirmBooking
          when={showDayAndClock(hold.starts_at)}
          timeLeft={asMinutes(secondsLeft)}
          food={lines
            .filter((line) => line.variety.id in chosen)
            .map((line) => ({ ...line, quantity: chosen[line.variety.id] }))}
          substitutes={substitutes
            .map((id) => lines.find((line) => line.variety.id === id))
            .filter((line) => line !== undefined)}
          sending={sending}
          onConfirm={book}
          onBack={() => setConfirming(false)}
        />
      )}
    </div>
  )
}

/**
 * "Ready to book?" (13 Nov night): the time, the food and the substitutes, once
 * more, with Confirm booking and Go back. The browser's own <dialog>, so Escape
 * or a tap outside means Go back, and the keyboard stays inside it.
 */
function ConfirmBooking({
  when,
  timeLeft,
  food,
  substitutes,
  sending,
  onConfirm,
  onBack,
}: {
  when: string
  timeLeft: string
  food: (Line & { quantity: number })[]
  substitutes: Line[]
  sending: boolean
  onConfirm: () => void
  onBack: () => void
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const title = useId()

  useEffect(() => {
    const box = dialog.current
    if (box && !box.open) box.showModal()
  }, [])

  return (
    <dialog
      ref={dialog}
      className="confirm-dialog"
      aria-labelledby={title}
      // While it's booking, Escape and a tap outside wait for the answer.
      onCancel={(event) => {
        if (sending) event.preventDefault()
      }}
      onClose={onBack}
      onClick={(event) => {
        if (event.target === dialog.current && !sending) dialog.current?.close()
      }}
    >
      <div className="confirm-body">
        <h2 id={title}>Ready to book?</h2>
        <p className="confirm-when">
          <Icon name="calendar" className="hold-icon" />
          <span>
            <strong>{when}</strong>
            <span className="muted"> · still kept for {timeLeft}</span>
          </span>
        </p>

        <h3>Your food</h3>
        <ul className="confirm-list">
          {food.map((line) => (
            <li key={line.variety.id}>
              <span>
                {line.variety.name}
                {line.quantity > 1 && ` × ${line.quantity}`}
              </span>
              <span className="muted">{line.item}</span>
            </li>
          ))}
        </ul>

        {substitutes.length > 0 ? (
          <>
            <h3>If something runs out, use these, in order</h3>
            <ol className="confirm-list confirm-ranked">
              {substitutes.map((line) => (
                <li key={line.variety.id}>
                  <span>{line.variety.name}</span>
                  <span className="muted">{line.item}</span>
                </li>
              ))}
            </ol>
          </>
        ) : (
          <p className="muted">No substitutes: if something runs out, you can choose something else from the shelf at the counter.</p>
        )}

        <p className="confirm-note">You can still cancel later on your booking page, until booking closes.</p>

        <div className="confirm-actions">
          <button type="button" className="secondary" disabled={sending} onClick={() => dialog.current?.close()}>
            Go back
          </button>
          <button type="button" disabled={sending} aria-busy={sending} onClick={onConfirm}>
            {sending ? 'Booking...' : 'Confirm booking'}
          </button>
        </div>
      </div>
    </dialog>
  )
}

/** Up to the limit of substitutes, ranked: if something is gone at packing, these fill the gap in order (U2, U4). */
function Substitutes({
  limit,
  ranked,
  choices,
  onChange,
}: {
  limit: number
  ranked: Line[]
  choices: Line[]
  onChange: (ids: number[]) => void
}) {
  const box = useId()
  const ids = ranked.map((line) => line.variety.id)
  const move = (from: number, to: number) => {
    const reordered = [...ids]
    const [moved] = reordered.splice(from, 1)
    reordered.splice(to, 0, moved)
    onChange(reordered)
  }

  return (
    <section className="card">
      <h2 className="in-card">Substitutes (if something runs out)</h2>
      <p className="muted">
        If something you chose is gone when your bag is packed, the volunteer uses these instead, in this order.
        Nothing else is ever put in your bag.
      </p>
      {ranked.length > 0 && (
        <ol className="ranked">
          {ranked.map((line, index) => (
            <li key={line.variety.id}>
              <span>
                {line.variety.name} <span className="muted">({line.item})</span>
              </span>
              <span className="choose-controls">
                <button type="button" className="secondary" disabled={index === 0} onClick={() => move(index, index - 1)} aria-label={`Move ${line.variety.name} up`}>
                  ↑
                </button>
                <button type="button" className="secondary" disabled={index === ranked.length - 1} onClick={() => move(index, index + 1)} aria-label={`Move ${line.variety.name} down`}>
                  ↓
                </button>
                <button type="button" className="link-button" onClick={() => onChange(ids.filter((id) => id !== line.variety.id))}>
                  Remove
                </button>
              </span>
            </li>
          ))}
        </ol>
      )}
      {ranked.length < limit && choices.length > 0 && (
        <div className="field">
          <label htmlFor={box}>Add a substitute</label>
          <select
            id={box}
            value=""
            onChange={(event) => event.target.value && onChange([...ids, Number(event.target.value)])}
          >
            <option value="">Choose one</option>
            {choices.map((line) => (
              <option key={line.variety.id} value={line.variety.id}>
                {line.variety.name} ({line.item})
              </option>
            ))}
          </select>
        </div>
      )}
    </section>
  )
}

/** Seconds left, counted down once a second from what the server said. Calls timeUp at 0. */
function useCountdown(fromServer: number, timeUp: () => void): number {
  const [left, setLeft] = useState(fromServer)
  useEffect(() => {
    const started = Date.now()
    const timer = setInterval(() => {
      const now = Math.max(0, fromServer - Math.floor((Date.now() - started) / 1000))
      setLeft(now)
      if (now === 0) {
        clearInterval(timer)
        timeUp()
      }
    }, 1000)
    return () => clearInterval(timer)
  }, [fromServer, timeUp])
  return left
}

/**
 * What a screen reader says about the time left. It changes only a few times
 * (at the start, then at 5, 2 and 1 minutes left), so it's read only then.
 */
function timeLeftToSay(seconds: number, holdMinutes: number): string {
  if (seconds <= 60) return 'Less than 1 minute left to book.'
  if (seconds <= 120) return 'Less than 2 minutes left to book.'
  if (seconds <= 300) return 'Less than 5 minutes left to book.'
  return `Your time is kept for ${holdMinutes} minutes while you choose.`
}

/** 125 seconds as "2:05". */
function asMinutes(seconds: number): string {
  return `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`
}
