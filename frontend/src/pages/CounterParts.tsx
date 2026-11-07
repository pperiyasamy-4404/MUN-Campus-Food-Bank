import { NavLink } from 'react-router'
import type { ShelfFood } from '../api.ts'
import { byItem, total, whyNotMore, type Chosen } from './counterTools.ts'

// Pieces the counter pages share.

/** The three things done at the counter. */
export function CounterNav() {
  return (
    <nav className="sub-nav" aria-label="Counter">
      <NavLink to="/counter" end>
        Hand over a bag
      </NavLink>
      <NavLink to="/counter/walk-in">Walk-in</NavLink>
      <NavLink to="/counter/setup-code">Setup code</NavLink>
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
      {byItem(lines).map((group) => (
        <div key={group.itemId} className="item">
          <h3 className="item-name">{group.item}</h3>
          <ul className="choose-list">
            {group.lines.map((line) => {
              const count = chosen[line.variety_id] ?? 0
              const whyNot = whyNotMore(line, chosen, lines, room, maxPerItem, alreadyByItem[line.item_id] ?? 0)
              return (
                <li key={line.variety_id} className={count > 0 ? 'choose-row chosen' : 'choose-row'}>
                  <span className="choose-name">
                    <strong>{line.variety}</strong>
                    <span className="muted">{line.stock} left</span>
                  </span>
                  <span className="choose-controls">
                    {whyNot && count === 0 && <span className="why-not">{whyNot}</span>}
                    {count > 0 && (
                      <>
                        <button type="button" className="secondary" onClick={() => change(line, -1)}>
                          −<span className="visually-hidden"> one {line.variety}</span>
                        </button>
                        <span className="count">{count}</span>
                      </>
                    )}
                    <button type="button" className="secondary" onClick={() => change(line, 1)} disabled={whyNot !== null}>
                      {count === 0 ? 'Add' : '+'}
                      <span className="visually-hidden"> {line.variety}</span>
                    </button>
                  </span>
                </li>
              )
            })}
          </ul>
        </div>
      ))}
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
    <div className="shelf">
      {byItem(lines).map((group) => (
        <div key={group.itemId} className="item">
          <h3 className="item-name">{group.item}</h3>
          <div className="extra-choices" role="group" aria-label={group.item}>
            {group.lines.map((line) => {
              const picked = chosen[group.itemId] === line.variety_id
              return (
                <button
                  key={line.variety_id}
                  type="button"
                  className={picked ? 'extra-choice picked' : 'extra-choice secondary'}
                  aria-pressed={picked}
                  onClick={() => {
                    const next = { ...chosen }
                    if (picked) delete next[group.itemId]
                    else next[group.itemId] = line.variety_id
                    onChange(next)
                  }}
                >
                  {line.variety} <span className="muted">({line.stock} left)</span>
                </button>
              )
            })}
          </div>
        </div>
      ))}
    </div>
  )
}
