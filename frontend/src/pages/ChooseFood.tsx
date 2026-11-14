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
import { onlyIfSaying, onlyReplaces } from './backupTools.ts'

// Stage 2 of booking: the time is held, a countdown runs, and the student
// chooses food and substitutes, then presses Book (S8, I3, U2).
//
// The limits are checked here so the buttons can say no straight away, and
// again on the server, which is what really decides.

type Line = { variety: Variety; item: string; itemKey: string; photoUrl: string | null }

// What the food cards are for right now (14 Nov): adding food to the bag, or
// choosing backups (substitutes). The same cards, with different buttons.
type Mode = 'food' | 'backups'

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
  const [mode, setMode] = useState<Mode>('food')
  const switchRef = useRef<HTMLDivElement>(null)

  // Every bookable variety, with its item, in the order the server sent them (A to Z).
  const lines: Line[] = food.bookable.flatMap((category) =>
    category.items.flatMap((item) =>
      item.varieties.map((variety) => ({
        variety,
        item: item.name,
        itemKey: `${category.name}/${item.name}`,
        photoUrl: item.photo_url,
      })),
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

  // Which chosen food a substitute can only stand in for (14 Nov): none means it can replace anything.
  const replaces = (line: Line) => onlyReplaces(line, lines, chosen, limits.max_per_item)
  // 1 for the first backup, 0 if it isn't one.
  const backupNumber = (varietyId: number) => substitutes.indexOf(varietyId) + 1
  const backupsFull = substitutes.length >= limits.substitute_limit
  const rankedBackups = substitutes
    .map((id) => lines.find((line) => line.variety.id === id))
    .filter((line) => line !== undefined)

  function toggleBackup(line: Line) {
    setSubstitutes((old) =>
      old.includes(line.variety.id)
        ? old.filter((id) => id !== line.variety.id)
        : old.length >= limits.substitute_limit
          ? old
          : [...old, line.variety.id],
    )
  }

  /** Switch what the cards are for, and bring the switch into view, so the change is seen. */
  function switchTo(next: Mode) {
    setMode(next)
    const box = switchRef.current
    if (box && box.getBoundingClientRect().top < 0) box.scrollIntoView({ block: 'start' })
  }

  /** The button (or reason) on a variety's row while choosing backups. */
  function backupAction(line: Line) {
    const name = line.variety.name
    if (line.variety.id in chosen) return <span className="why-not">In your bag</span>
    const number = backupNumber(line.variety.id)
    if (number > 0) {
      return (
        <button type="button" className="chosen-button" onClick={() => toggleBackup(line)}>
          ✓ Backup {number}
          <span className="visually-hidden">. Remove {name} from your backups</span>
        </button>
      )
    }
    if (line.variety.stock === 0) return null
    if (backupsFull) return <span className="why-not">{limits.substitute_limit} backups already</span>
    return (
      <button type="button" className="backup-add" onClick={() => toggleBackup(line)}>
        <span aria-hidden="true">+ </span>Backup<span className="visually-hidden"> {name}</span>
      </button>
    )
  }
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
            {total}/{limits.item_limit} food · {substitutes.length}/{limits.substitute_limit} backups
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

      {/* My food | Backups (14 Nov, option 2 on backup-designs.html): the same cards
          either add food to the bag or choose backups for it. */}
      <div ref={switchRef} className="choose-switch" role="group" aria-label="What you're choosing">
        <button type="button" aria-pressed={mode === 'food'} onClick={() => switchTo('food')}>
          My food <span className="switch-count">{total}/{limits.item_limit}</span>
        </button>
        <button type="button" aria-pressed={mode === 'backups'} onClick={() => switchTo('backups')}>
          Backups <span className="switch-count">{substitutes.length}/{limits.substitute_limit}</span>
        </button>
      </div>

      {mode === 'food' ? (
        <p className="muted choose-rules">
          Up to {limits.item_limit} things, and {limits.max_per_item === 1 ? 'one' : `up to ${limits.max_per_item}`} of
          each kind of food, counting all its varieties together.
        </p>
      ) : (
        <BackupOrder
          ranked={rankedBackups}
          limit={limits.substitute_limit}
          replaces={replaces}
          onChange={setSubstitutes}
        />
      )}

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
              const backupNumbers = item.varieties.map((variety) => backupNumber(variety.id)).filter((n) => n > 0)
              const choosingBackups = mode === 'backups'
              return (
                <FoodCard
                  key={item.id}
                  name={item.name}
                  photoUrl={item.photo_url}
                  highlighted={choosingBackups ? backupNumbers.length > 0 : chosenOfItem > 0}
                  badge={
                    choosingBackups
                      ? backupNumbers.length > 0
                        ? `Backup ${backupNumbers.sort((a, b) => a - b).join(', ')}`
                        : chosenOfItem > 0
                          ? 'In your bag'
                          : undefined
                      : chosenOfItem > 0
                        ? `✓ ${chosenOfItem} chosen`
                        : undefined
                  }
                >
                  {item.varieties.map((variety) => {
                    const line = { variety, item: item.name, itemKey, photoUrl: item.photo_url }
                    const have = chosen[variety.id] ?? 0
                    const notMore = whyNotMore(line)
                    if (choosingBackups) {
                      const only = have === 0 ? replaces(line) : []
                      const action = backupAction(line)
                      return (
                        <FoodRow
                          key={variety.id}
                          name={variety.name}
                          tags={variety.tags}
                          dim={have > 0 || (backupNumber(variety.id) === 0 && (variety.stock === 0 || backupsFull))}
                          note={
                            <>
                              <StockNote stock={variety.stock} fewLeft={variety.few_left} />
                              {only.length > 0 && <span className="backup-only">Used {onlyIfSaying(only)}</span>}
                            </>
                          }
                        >
                          {action}
                        </FoodRow>
                      )
                    }
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

      {/* At the end of the food, so nobody scrolls past backups without knowing about them. */}
      {mode === 'food' && (
        <section className="card backup-invite">
          <div>
            <h2 className="in-card">Backups, in case something runs out</h2>
            <p className="muted">
              {substitutes.length === 0
                ? `Choose up to ${limits.substitute_limit}. If something you chose is gone when your bag is packed, the volunteer uses these instead.`
                : `You have ${substitutes.length} of ${limits.substitute_limit}: ${rankedBackups.map((line) => line.variety.name).join(', ')}.`}
            </p>
          </div>
          <button type="button" className="secondary" onClick={() => switchTo('backups')}>
            {substitutes.length === 0 ? 'Choose backups' : 'Change backups'}
          </button>
        </section>
      )}

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
                ` · ${substitutes.length} ${substitutes.length === 1 ? 'backup' : 'backups'}`}
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
          substitutes={rankedBackups}
          replaces={replaces}
          sending={sending}
          onConfirm={book}
          onBack={() => setConfirming(false)}
          onChooseBackups={() => {
            switchTo('backups')
            // The dialog gave the focus back to Book; move it to the switch, where the student now is.
            switchRef.current?.querySelectorAll('button')[1]?.focus({ preventScroll: true })
          }}
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
  replaces,
  sending,
  onConfirm,
  onBack,
  onChooseBackups,
}: {
  when: string
  timeLeft: string
  food: (Line & { quantity: number })[]
  substitutes: Line[]
  replaces: (line: Line) => string[]
  sending: boolean
  onConfirm: () => void
  onBack: () => void
  onChooseBackups: () => void
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
            <h3>Your backups: if something runs out, use these, in order</h3>
            <ol className="confirm-list confirm-ranked">
              {substitutes.map((line) => {
                const only = replaces(line)
                return (
                  <li key={line.variety.id}>
                    <span>
                      {line.variety.name}
                      {only.length > 0 && <span className="backup-only"> {onlyIfSaying(only)}</span>}
                    </span>
                    <span className="muted">{line.item}</span>
                  </li>
                )
              })}
            </ol>
          </>
        ) : (
          // No backups (14 Nov, Prakash's idea): said here, in the check they already read,
          // not in a second "Are you sure?" pop-up, with a way straight back to choose some.
          <div className="notice confirm-no-backups">
            <p>
              <strong>No backups chosen.</strong> If something you chose runs out, your bag will be one short.
              Backups take a few seconds and keep your bag full.
            </p>
            {/* The filled button, so the easy tap is choosing backups (14 Nov, Prakash). */}
            <button
              type="button"
              disabled={sending}
              onClick={() => {
                dialog.current?.close()
                onChooseBackups()
              }}
            >
              Choose backups
            </button>
          </div>
        )}

        <p className="confirm-note">You can still cancel later on your booking page, until booking closes.</p>

        <div className="confirm-actions">
          <button type="button" className="secondary" disabled={sending} onClick={() => dialog.current?.close()}>
            Go back
          </button>
          <button
            type="button"
            className={substitutes.length === 0 ? 'secondary' : undefined}
            disabled={sending}
            aria-busy={sending}
            onClick={onConfirm}
          >
            {sending ? 'Booking...' : substitutes.length === 0 ? 'Book without backups' : 'Confirm booking'}
          </button>
        </div>
      </div>
    </dialog>
  )
}

/**
 * The backups in order, while choosing them (14 Nov, option 2): a row of small photo
 * chips, numbered. If something is gone at packing, these fill the gap in order (U2, U4).
 * The arrows change the order; ✕ takes one off. The Backup buttons on the cards add them.
 *
 * Packing never gives a second of an item (with the sample limit of 1), so another
 * variety of something chosen (Corn flakes, with Bran flakes chosen) only fills in if
 * that pick runs out. The chip says so. The rule itself doesn't change.
 */
function BackupOrder({
  ranked,
  limit,
  replaces,
  onChange,
}: {
  ranked: Line[]
  limit: number
  replaces: (line: Line) => string[]
  onChange: (ids: number[]) => void
}) {
  const ids = ranked.map((line) => line.variety.id)
  const move = (from: number, to: number) => {
    const reordered = [...ids]
    const [moved] = reordered.splice(from, 1)
    reordered.splice(to, 0, moved)
    onChange(reordered)
  }

  return (
    <section className="backup-order" aria-labelledby="backup-order-title">
      <h2 id="backup-order-title" className="backup-order-title">
        Your backups, in order
      </h2>
      <p className="muted backup-order-help">
        If something you chose is gone when your bag is packed, the volunteer uses backup 1 first, then 2, and so on.
        Tap <strong>Backup</strong> on any food below, up to {limit}.
      </p>
      {ranked.length === 0 ? (
        <p className="backup-order-empty">No backups yet.</p>
      ) : (
        <ol className="backup-chips">
          {ranked.map((line, index) => {
            const only = replaces(line)
            return (
              <li key={line.variety.id} className="backup-chip">
                <span className="backup-chip-number" aria-hidden="true">
                  {index + 1}
                </span>
                {line.photoUrl ? (
                  <img className="backup-chip-photo" src={line.photoUrl} alt="" />
                ) : (
                  <span className="backup-chip-photo" aria-hidden="true" />
                )}
                <span className="backup-chip-text">
                  <span className="backup-chip-name">{line.variety.name}</span>
                  {only.length > 0 && <span className="backup-only">{onlyIfSaying(only)}</span>}
                </span>
                <span className="backup-chip-tools">
                  <button
                    type="button"
                    className="chip-tool"
                    disabled={index === 0}
                    onClick={() => move(index, index - 1)}
                    aria-label={`Move ${line.variety.name} earlier`}
                  >
                    ‹
                  </button>
                  <button
                    type="button"
                    className="chip-tool"
                    disabled={index === ranked.length - 1}
                    onClick={() => move(index, index + 1)}
                    aria-label={`Move ${line.variety.name} later`}
                  >
                    ›
                  </button>
                  <button
                    type="button"
                    className="chip-tool"
                    onClick={() => onChange(ids.filter((id) => id !== line.variety.id))}
                    aria-label={`Remove ${line.variety.name} from your backups`}
                  >
                    ✕
                  </button>
                </span>
              </li>
            )
          })}
        </ol>
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
