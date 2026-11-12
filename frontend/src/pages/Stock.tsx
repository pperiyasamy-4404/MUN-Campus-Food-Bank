import { useEffect, useId, useState, type FormEvent } from 'react'
import type { StockItem, StockPage, StockVariety } from '../api.ts'
import { useMe } from '../me.ts'
import { showDate, showDayAndClock } from '../time.ts'
import { AddFood, AddVariety, CategoriesAndTags, ItemPhotoEditor, Rename, VarietyEditor } from './StockForms.tsx'
import { change, needsCounting, withVariety, type StockTools } from './stockTools.ts'
import { PageHeading } from '../PageHeading.tsx'

// The staff stock page (I8, R2): check the shelf before booking opens, and add
// new food when donations come in. Every staff member can do everything here,
// categories, tags and names too (decided 7 Nov). Most food has no number: it's
// In stock or Few left. Only food worth sharing out exactly is counted (decided 12 Nov).

type Load = { state: 'loading' } | { state: 'failed' } | { state: 'ready'; page: StockPage }

export function Stock() {
  const { forget } = useMe()
  const [load, setLoad] = useState<Load>({ state: 'loading' })
  const [version, setVersion] = useState(0)
  const [onlyToCount, setOnlyToCount] = useState(false)

  useEffect(() => {
    let stillWanted = true
    fetch('/api/stock')
      .then(async (response) => {
        if (response.status === 401) return stillWanted && forget()
        if (!response.ok) throw new Error(`The server answered ${response.status}`)
        const page = (await response.json()) as StockPage
        if (stillWanted) setLoad({ state: 'ready', page })
      })
      .catch(() => {
        if (stillWanted) setLoad({ state: 'failed' })
      })
    return () => {
      stillWanted = false
    }
  }, [version, forget])

  if (load.state === 'loading') return <p className="muted">Asking the server...</p>
  if (load.state === 'failed') return <p className="problem">Could not get the stock. Is the server running?</p>

  const { page } = load
  const tools: StockTools = {
    tags: page.tags,
    reload: () => setVersion((old) => old + 1),
    counted: (variety) =>
      setLoad((old) => (old.state === 'ready' ? { state: 'ready', page: withVariety(old.page, variety) } : old)),
    loggedOut: forget,
  }
  const shown = page.categories.flatMap((category) =>
    category.items.flatMap((item) => item.varieties.filter((variety) => variety.shown)),
  )
  const toCount = shown.filter((variety) => needsCounting(variety, page.last_pickup_ended_at))

  return (
    <div>
      <PageHeading>Food and stock</PageHeading>
      <p className="lead">
        Most food needs no number: tap <strong>In stock</strong> or <strong>Few left</strong>, and any number of
        students can book it. Count only food you want shared out exactly, like 6 jars from one donation: the first
        6 students get one, and then it shows as out of stock. Food that's booked but not packed yet is taken off a
        count for you.
      </p>

      <div className="notice stock-notice">
        <p>{whenBookingOpens(page)}</p>
        <p>
          {toCount.length === 0
            ? 'Nothing needs checking.'
            : // In brackets, so the time's "p.m." isn't followed by a second full stop.
              `${toCount.length} of ${shown.length} ${shown.length === 1 ? 'food needs' : 'foods need'} checking: marked out of stock while packing, or counted before the last pickup${
                page.last_pickup_ended_at ? ` (it ended ${showDayAndClock(page.last_pickup_ended_at)})` : ''
              }.`}
        </p>
        <label className="check">
          <input type="checkbox" checked={onlyToCount} onChange={(event) => setOnlyToCount(event.target.checked)} />
          Only show food that needs checking
        </label>
      </div>

      <Section title="Food to book" isExtra={false} page={page} tools={tools} onlyToCount={onlyToCount} />
      <Section title="Extras" isExtra page={page} tools={tools} onlyToCount={onlyToCount} />
      <CategoriesAndTags tools={tools} />
    </div>
  )
}

function whenBookingOpens(page: StockPage): string {
  const next = page.next_booking
  if (next === null) return 'No pickup days are coming up.'
  const day = showDate(next.pickup_date)
  if (next.booking_status === 'open') {
    return `Booking for ${day} is open until ${showDayAndClock(next.booking_closes_at)}`
  }
  // The time comes last: it ends in "p.m." already, so no full stop is added.
  return `Check the shelf before booking for ${day} opens, ${showDayAndClock(next.booking_opens_at)}`
}

function Section({
  title,
  isExtra,
  page,
  tools,
  onlyToCount,
}: {
  title: string
  isExtra: boolean
  page: StockPage
  tools: StockTools
  onlyToCount: boolean
}) {
  const wanted = (variety: StockVariety) => !onlyToCount || needsCounting(variety, page.last_pickup_ended_at)
  const categories = page.categories
    .map((category) => ({
      ...category,
      items: category.items.filter((item) => item.is_extra === isExtra && item.varieties.some(wanted)),
    }))
    .filter((category) => category.items.length > 0)

  return (
    <section>
      <h2>{title}</h2>
      {isExtra && <p className="muted">Not booked online. Students see them as "may be available" when there are some left.</p>}
      {categories.length === 0 && <p className="muted">{onlyToCount ? 'Nothing here needs checking.' : 'Nothing yet.'}</p>}
      {categories.map((category) => (
        <article className="card" key={category.id}>
          <header className="card-header">
            <h3>{category.name}</h3>
            <Rename tools={tools} path={`/api/categories/${category.id}`} current={category.name} />
          </header>
          {category.items.map((item) => (
            <ItemBlock key={item.id} item={item} tools={tools} wanted={wanted} page={page} />
          ))}
        </article>
      ))}
      <AddFood tools={tools} categories={page.categories} isExtra={isExtra} />
    </section>
  )
}

function ItemBlock({
  item,
  tools,
  wanted,
  page,
}: {
  item: StockItem
  tools: StockTools
  wanted: (variety: StockVariety) => boolean
  page: StockPage
}) {
  return (
    <div className="item">
      <div className="item-header item-header-photo">
        <ItemPhotoEditor tools={tools} item={item}>
          <span className="item-title">
            <h4>{item.name}</h4>
            <Rename tools={tools} path={`/api/items/${item.id}`} current={item.name} />
          </span>
        </ItemPhotoEditor>
      </div>
      <ul className="stock-list">
        {item.varieties.filter(wanted).map((variety) => (
          <VarietyRow
            key={variety.id}
            variety={variety}
            isExtra={item.is_extra}
            tools={tools}
            stale={needsCounting(variety, page.last_pickup_ended_at)}
          />
        ))}
      </ul>
      <AddVariety tools={tools} itemId={item.id} itemName={item.name} />
    </div>
  )
}

const LEVELS = ['In stock', 'Few left', 'Out of stock'] as const
type Level = (typeof LEVELS)[number]

/** Which of the three buttons shows as pressed. None when the food has a number above 0. */
function levelOf(variety: StockVariety): Level | null {
  if (variety.stock === 0) return 'Out of stock'
  if (variety.stock !== null) return null
  return variety.few_left ? 'Few left' : 'In stock'
}

function VarietyRow({
  variety,
  isExtra,
  tools,
  stale,
}: {
  variety: StockVariety
  isExtra: boolean
  tools: StockTools
  stale: boolean
}) {
  const [onShelf, setOnShelf] = useState('')
  // Food with a number opens with the count box; food with none doesn't need it.
  const [counting, setCounting] = useState(variety.stock !== null && variety.stock > 0)
  const [saving, setSaving] = useState(false)
  const [message, setMessage] = useState<{ kind: 'saved' | 'problem'; text: string } | null>(null)
  const [editing, setEditing] = useState(false)
  const box = useId()
  const tagNames = tools.tags.filter((tag) => variety.tag_ids.includes(tag.id)).map((tag) => tag.name)

  async function save(event: FormEvent) {
    event.preventDefault()
    if (onShelf.trim() === '') return setMessage({ kind: 'problem', text: 'Type how many are on the shelf.' })
    setSaving(true)
    const answer = await change<{ variety: StockVariety; short_by: number }>(
      tools,
      `/api/varieties/${variety.id}/count`,
      { on_shelf: Number(onShelf) },
    )
    setSaving(false)
    if (!answer.ok) {
      return setMessage({ kind: 'problem', text: answer.fields.on_shelf ?? answer.message })
    }
    setOnShelf('')
    const short = answer.data.short_by
    setMessage({
      kind: 'saved',
      text:
        short === 0
          ? 'Saved.'
          : `Saved. ${short} booked ${short === 1 ? 'one is' : 'ones are'} missing from the shelf: ${
              short === 1 ? 'that bag' : 'those bags'
            } will need a substitute.`,
    })
    tools.counted(answer.data.variety)
  }

  /** In stock or Few left: no number (decided 12 Nov). Out of stock is a count of 0. */
  async function mark(choice: Level) {
    setSaving(true)
    const answer =
      choice === 'Out of stock'
        ? await change<{ variety: StockVariety; short_by: number }>(tools, `/api/varieties/${variety.id}/count`, {
            on_shelf: 0,
          })
        : await change<StockVariety>(tools, `/api/varieties/${variety.id}/in-stock`, { few_left: choice === 'Few left' })
    setSaving(false)
    if (!answer.ok) return setMessage({ kind: 'problem', text: answer.message })
    const newer = 'variety' in answer.data ? answer.data.variety : answer.data
    const short = 'short_by' in answer.data ? answer.data.short_by : 0
    setMessage({
      kind: 'saved',
      text:
        short === 0
          ? `Saved: ${choice.toLowerCase()}.`
          : `Saved: out of stock. ${short} booked ${short === 1 ? 'one is' : 'ones are'} missing from the shelf: ${
              short === 1 ? 'that bag' : 'those bags'
            } will need a substitute.`,
    })
    if (choice !== 'Out of stock') setCounting(false)
    tools.counted(newer)
  }

  const level = levelOf(variety)

  const classes = ['stock-row', stale && 'stock-row-stale', !variety.shown && 'stock-row-hidden']
  return (
    <li className={classes.filter(Boolean).join(' ')}>
      <div className="stock-about">
        <p className="stock-name">
          <strong>{variety.name}</strong>
          {!variety.shown && <span className="tag">Hidden</span>}
          {tagNames.map((name) => (
            <span key={name} className="tag">
              {name}
            </span>
          ))}
        </p>
        <p className="stock-numbers">
          {variety.stock === null ? (
            <>
              <strong className={variety.few_left ? 'stock-few' : undefined}>
                {variety.few_left ? 'Few left' : 'In stock'}
              </strong>{' '}
              · no number
            </>
          ) : variety.stock === 0 ? (
            <strong className="stock-out">Out of stock</strong>
          ) : (
            <>
              {/* Extras aren't booked online (E1): their number is just what's left. */}
              <strong>{variety.stock}</strong> {isExtra ? 'left' : 'can be booked'}
            </>
          )}
          {variety.booked_not_packed > 0 && ` · ${variety.booked_not_packed} booked, not packed yet`}
        </p>
        <p className={stale ? 'stock-age stock-age-stale' : 'stock-age'}>
          {variety.counted_at
            ? `${variety.stock === null ? 'Checked' : 'Counted'} ${showDayAndClock(variety.counted_at)} by ${variety.counted_by}`
            : 'Never checked'}
        </p>
        {variety.ran_out_at && (
          <p className="stock-age stock-ran-out">
            Marked out of stock while packing, {showDayAndClock(variety.ran_out_at)}. Tap In stock, or count it, to
            take the flag off other bags.
          </p>
        )}
      </div>
      <div className="stock-controls">
        <div className="level-buttons" role="group" aria-label={`How much ${variety.name} is on the shelf`}>
          {LEVELS.map((choice) => (
            <button
              key={choice}
              type="button"
              className={level === choice ? 'level-button level-button-on' : 'level-button'}
              aria-pressed={level === choice}
              disabled={saving}
              onClick={() => mark(choice)}
            >
              {choice}
            </button>
          ))}
        </div>
        <div className="count-controls">
          <button type="button" className="link-button" onClick={() => setCounting(!counting)} aria-expanded={counting}>
            {counting ? 'Close count' : 'Count it'}
          </button>
          <button type="button" className="link-button" onClick={() => setEditing(!editing)} aria-expanded={editing}>
            {editing ? 'Close' : 'Edit'}
          </button>
        </div>
        {counting && (
          <form className="count-form" onSubmit={save} noValidate>
            <label htmlFor={box}>On the shelf now</label>
            <div className="count-controls">
              <input
                id={box}
                type="number"
                inputMode="numeric"
                min={0}
                max={999}
                value={onShelf}
                onChange={(event) => setOnShelf(event.target.value)}
              />
              <button type="submit" disabled={saving}>
                {saving ? 'Saving...' : 'Save'}
              </button>
            </div>
          </form>
        )}
      </div>
      {message && (
        <p className={message.kind === 'saved' ? 'count-saved' : 'field-error'} role="status">
          {message.text}
        </p>
      )}
      {editing && <VarietyEditor tools={tools} variety={variety} />}
    </li>
  )
}
