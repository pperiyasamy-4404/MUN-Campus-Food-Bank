import { NavLink } from 'react-router'
import type { ShelfFood } from '../api.ts'
import { FoodCard, FoodRow, StockNote } from '../FoodCards.tsx'
import { byItem, total, whyNotMore, type Chosen } from './counterTools.ts'

// Pieces the counter pages share.

/** The things done at the counter. */
export function CounterNav() {
  return (
    <nav className="sub-nav" aria-label="Counter">
      <NavLink to="/counter" end>
        Hand over a bag
      </NavLink>
      <NavLink to="/counter/walk-in">Walk-in</NavLink>
      <NavLink to="/counter/setup-code">Setup code</NavLink>
      <NavLink to="/counter/fix">Fix a pickup</NavLink>
    </nav>
  )
}

/**
 * Food taken from the shelf: a walk-in's food (W1), or a student's choice for a
 * gap in their bag (U6). Only food nobody booked is listed, with how many are left.
 */
export function ShelfPicker({
  lines,
  chosen,
  onChange,
  room,
  maxPerItem,
  alreadyByItem = {},
}: {
  lines: ShelfFood[]
  chosen: Chosen
  onChange: (chosen: Chosen) => void
  room: number
  maxPerItem: number
  // What they have already of each item, by item id: a bag's contents.
  alreadyByItem?: Record<number, number>
}) {
  function change(line: ShelfFood, by: number) {
    onChange({ ...chosen, [line.variety_id]: Math.max(0, (chosen[line.variety_id] ?? 0) + by) })
  }

  if (lines.length === 0) return <p className="muted">Nothing is left on the shelf that nobody booked.</p>
  return (
    <div className="shelf">
      <p className="shelf-count" role="status">
        {total(chosen)} of {room} chosen
      </p>
      <div className="food-grid food-grid-small">
        {byItem(lines).map((group) => {
          const ofItem = group.lines.reduce((sum, line) => sum + (chosen[line.variety_id] ?? 0), 0)
          return (
            <FoodCard
              key={group.itemId}
              name={group.item}
              photoUrl={group.lines[0].photo_url}
              highlighted={ofItem > 0}
              badge={ofItem > 0 ? `✓ ${ofItem}` : undefined}
            >
              {group.lines.map((line) => {
                const count = chosen[line.variety_id] ?? 0
                const whyNot = whyNotMore(line, chosen, lines, room, maxPerItem, alreadyByItem[line.item_id] ?? 0)
                return (
                  <FoodRow
                    key={line.variety_id}
                    name={line.variety}
                    dim={count === 0 && whyNot !== null}
                    note={<StockNote stock={line.stock} fewLeft={line.few_left} />}
                  >
                    {count === 0 && whyNot !== null ? (
                      <span className="why-not">{whyNot}</span>
                    ) : (
                      <span className="choose-controls">
                        {count > 0 && (
                          <>
                            <button type="button" className="secondary" onClick={() => change(line, -1)}>
                              −<span className="visually-hidden"> one {line.variety}</span>
                            </button>
                            <span className="count">{count}</span>
                          </>
                        )}
                        <button
                          type="button"
                          className={count === 0 ? 'add-button' : 'secondary'}
                          onClick={() => change(line, 1)}
                          disabled={whyNot !== null}
                        >
                          {count === 0 ? 'Add' : '+'}
                          <span className="visually-hidden"> {line.variety}</span>
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
    </div>
  )
}

/** Extras the student asks for: one of each extra item, like one bread (E3). Tap again to take it off. */
export function ExtrasPicker({
  lines,
  chosen,
  onChange,
}: {
  lines: ShelfFood[]
  chosen: Record<number, number>
  onChange: (chosen: Record<number, number>) => void
}) {
  if (lines.length === 0) return <p className="muted">No extras today.</p>
  return (
    <div className="food-grid food-grid-small">
      {byItem(lines).map((group) => {
        const pickedId = chosen[group.itemId]
        return (
          <FoodCard
            key={group.itemId}
            name={group.item}
            photoUrl={group.lines[0].photo_url}
            highlighted={pickedId !== undefined}
            badge={pickedId !== undefined ? '✓ 1' : undefined}
          >
            {group.lines.map((line) => {
              const picked = pickedId === line.variety_id
              return (
                <FoodRow key={line.variety_id} name={line.variety} note={<StockNote stock={line.stock} fewLeft={line.few_left} />}>
                  <button
                    type="button"
                    className={picked ? 'chosen-button' : 'add-button'}
                    aria-pressed={picked}
                    onClick={() => {
                      const next = { ...chosen }
                      if (picked) delete next[group.itemId]
                      else next[group.itemId] = line.variety_id
                      onChange(next)
                    }}
                  >
                    {picked ? '✓ Added' : 'Add'}
                    <span className="visually-hidden"> {line.variety}</span>
                  </button>
                </FoodRow>
              )
            })}
          </FoodCard>
        )
      })}
    </div>
  )
}
