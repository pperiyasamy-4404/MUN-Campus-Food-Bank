import { useEffect, useState } from 'react'
import type { CounterPage, FixPage, ShelfFood } from '../api.ts'

// What the counter pages share: the shelf from the server, and the picking rules.

export type CounterLoad = { state: 'loading' } | { state: 'failed' } | { state: 'ready'; page: CounterPage }

/** Today's shelf and whether the counter is open. A new version asks the server again. */
export function useCounterPage(version: number, onLoggedOut: () => void): CounterLoad {
  const [load, setLoad] = useState<CounterLoad>({ state: 'loading' })
  useEffect(() => {
    let stillWanted = true
    fetch('/api/counter')
      .then(async (response) => {
        if (response.status === 401) {
          if (stillWanted) onLoggedOut()
          return
        }
        if (!response.ok) throw new Error(`The server answered ${response.status}`)
        const page = (await response.json()) as CounterPage
        if (stillWanted) setLoad({ state: 'ready', page })
      })
      .catch(() => {
        if (stillWanted) setLoad({ state: 'failed' })
      })
    return () => {
      stillWanted = false
    }
  }, [version, onLoggedOut])
  return load
}

/** How many of each variety was chosen, by variety id. */
export type Chosen = Record<number, number>

/** The shelf, one group per item, in the server's order. */
export function byItem(lines: ShelfFood[]): { itemId: number; item: string; lines: ShelfFood[] }[] {
  const groups: { itemId: number; item: string; lines: ShelfFood[] }[] = []
  for (const line of lines) {
    const group = groups.find((existing) => existing.itemId === line.item_id)
    if (group) group.lines.push(line)
    else groups.push({ itemId: line.item_id, item: line.item, lines: [line] })
  }
  return groups
}

export function total(chosen: Chosen): number {
  return Object.values(chosen).reduce((sum, count) => sum + count, 0)
}

/**
 * Why one more of this can't be taken, or null if it can. The same limits as
 * booking (I3): the room left, and the per-item limit counting what they have.
 * The server checks it all again.
 */
export function whyNotMore(
  line: ShelfFood,
  chosen: Chosen,
  lines: ShelfFood[],
  room: number,
  maxPerItem: number,
  alreadyOfItem: number,
): string | null {
  const have = chosen[line.variety_id] ?? 0
  if (have >= line.stock) return 'No more left'
  const ofItem =
    alreadyOfItem +
    lines.filter((other) => other.item_id === line.item_id).reduce((sum, other) => sum + (chosen[other.variety_id] ?? 0), 0)
  if (ofItem >= maxPerItem) return maxPerItem === 1 ? `One ${line.item} only` : `${maxPerItem} ${line.item} at most`
  if (total(chosen) >= room) return "That's all they can take"
  return null
}

/** The chosen food, as the server wants it. */
export function asChoices(chosen: Chosen): { variety_id: number; quantity: number }[] {
  return Object.entries(chosen)
    .filter(([, quantity]) => quantity > 0)
    .map(([id, quantity]) => ({ variety_id: Number(id), quantity }))
}

export type FixLoad = { state: 'loading' } | { state: 'failed' } | { state: 'ready'; page: FixPage }

/** The fix page for one pickup day, or the newest one. A new version asks the server again. */
export function useFixPage(day: string | null, version: number, onLoggedOut: () => void): FixLoad {
  const [load, setLoad] = useState<FixLoad>({ state: 'loading' })
  useEffect(() => {
    let stillWanted = true
    fetch(day ? `/api/fixes?day=${day}` : '/api/fixes')
      .then(async (response) => {
        if (response.status === 401) {
          if (stillWanted) onLoggedOut()
          return
        }
        if (!response.ok) throw new Error(`The server answered ${response.status}`)
        const page = (await response.json()) as FixPage
        if (stillWanted) setLoad({ state: 'ready', page })
      })
      .catch(() => {
        if (stillWanted) setLoad({ state: 'failed' })
      })
    return () => {
      stillWanted = false
    }
  }, [day, version, onLoggedOut])
  return load
}
