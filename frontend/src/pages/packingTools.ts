import type { Bag, BagFood, Outcome, PackingPlan } from '../api.ts'

/** A bag's status, in words. */
export const STATUS_WORDS: Record<string, string> = {
  booked: 'To pack',
  packed: 'Packed',
  picked_up: 'Picked up',
  no_show: 'No-show',
  cancelled: 'Cancelled',
}

/** What the volunteer found while packing one bag. Nothing is saved until Packed. */
export type Findings = {
  // Booked food that isn't on the shelf, in the order they found out.
  missing: { variety_id: number; how_many: number }[]
  // Substitutes they looked for and found none of.
  not_on_shelf: number[]
}

/**
 * Where a bag starts: food another volunteer already found none of is marked
 * missing, so the substitutes show straight away (U7). It still needs one look
 * (needsALook): a wrong tap shouldn't spread to every bag (decided 12 Nov).
 */
export function startingFindings(bag: Bag): Findings {
  return {
    missing: bag.food
      .filter((line) => line.ran_out_at !== null)
      .map((line) => ({ variety_id: line.variety_id, how_many: line.quantity })),
    not_on_shelf: [],
  }
}

/**
 * Food someone else marked out of stock that this volunteer found after all
 * (Found it). Sent with Packed, it takes the flag off every other bag (decided 12 Nov).
 */
export function foundAfterAll(bag: Bag, findings: Findings): number[] {
  return bag.food
    .filter((line) => line.ran_out_at !== null && !findings.missing.some((m) => m.variety_id === line.variety_id))
    .map((line) => line.variety_id)
}

/** The findings with this much of one food missing. 0 takes it off the list; a new one goes last. */
export function withMissing(findings: Findings, varietyId: number, howMany: number): Findings {
  const others = findings.missing.filter((line) => line.variety_id !== varietyId)
  const position = findings.missing.findIndex((line) => line.variety_id === varietyId)
  if (howMany === 0) return { ...findings, missing: others }
  const updated = { variety_id: varietyId, how_many: howMany }
  const missing =
    position === -1
      ? [...findings.missing, updated]
      : findings.missing.map((line) => (line.variety_id === varietyId ? updated : line))
  return { ...findings, missing }
}

/**
 * What the volunteer has put in the bag so far, ticked with Picked. Only on the
 * page, like the findings: it helps them keep track, and the server doesn't need it.
 * Keys say food or substitute, so the two lists can't mix.
 */
export type Picked = ReadonlySet<string>

export const foodKey = (varietyId: number) => `food-${varietyId}`
export const substituteKey = (varietyId: number) => `substitute-${varietyId}`
/** The volunteer looked at the shelf for food someone else marked out of stock. */
export const lookedKey = (varietyId: number) => `looked-${varietyId}`

/**
 * Food another volunteer marked out of stock, that this volunteer hasn't looked
 * for yet (what-could-go-wrong problem 6, decided 12 Nov). It needs one tap:
 * Still out of stock, or Found it. Any change to the line counts as looking.
 */
export function needsALook(line: BagFood, findings: Findings, picked: Picked): boolean {
  const missing = findings.missing.find((m) => m.variety_id === line.variety_id)?.how_many ?? 0
  return line.ran_out_at !== null && missing > 0 && !picked.has(lookedKey(line.variety_id))
}

/** Picked with one line ticked, or unticked. */
export function withPicked(picked: Picked, key: string, on: boolean): Picked {
  const next = new Set(picked)
  if (on) next.add(key)
  else next.delete(key)
  return next
}

/**
 * How many lines still need a tap before Packed: booked food that is neither
 * Picked nor all out of stock, food someone else marked out of stock that
 * nobody has looked for on this bag, substitutes the plan puts in that aren't
 * Picked, and substitutes Picked earlier that the plan no longer needs (take them out).
 */
export function stillToTick(bag: Bag, findings: Findings, plan: PackingPlan, picked: Picked): number {
  const food = bag.food.filter((line) => {
    if (needsALook(line, findings, picked)) return true
    const missing = findings.missing.find((m) => m.variety_id === line.variety_id)?.how_many ?? 0
    return missing < line.quantity && !picked.has(foodKey(line.variety_id))
  }).length
  const substitutes = plan.substitutes.filter((line) => {
    const goesIn = line.outcome === 'use'
    return goesIn !== picked.has(substituteKey(line.variety_id))
  }).length
  return food + substitutes
}

/**
 * All the lines that need a tap on this bag, for the progress bar (13 Nov): every
 * booked food line, and every substitute that goes in or was Picked. Done is
 * this minus stillToTick.
 */
export function linesToTick(bag: Bag, plan: PackingPlan, picked: Picked): number {
  const substitutes = plan.substitutes.filter(
    (line) => line.outcome === 'use' || picked.has(substituteKey(line.variety_id)),
  ).length
  return bag.food.length + substitutes
}

/** The findings with one substitute marked, or unmarked, as out of stock. */
export function withNotOnShelf(findings: Findings, varietyId: number, none: boolean): Findings {
  const others = findings.not_on_shelf.filter((id) => id !== varietyId)
  return { ...findings, not_on_shelf: none ? [...others, varietyId] : others }
}

/** What a substitute's outcome means, for the volunteer. */
export function outcomeWords(outcome: Outcome, item: string, replaces: string | null): string {
  switch (outcome) {
    case 'use':
      return `Put this in, for ${replaces}`
    case 'not_on_shelf':
      return 'Out of stock'
    case 'none_left':
      return 'Skipped: none left that nobody booked'
    case 'already_has_item':
      return `Skipped: the bag already has ${item}`
    case 'not_needed':
      return 'Not needed'
  }
}

// ---------- keeping the taps if the page reloads (what-could-go-wrong, small things) ----------

/**
 * The taps are kept in this phone's browser until Packed, so a reload (after a
 * phone call, say) doesn't lose them. Example: Jo ticked 4 of 6 lines, the
 * browser reloaded, and the 4 ticks are still there. Only this phone has them:
 * the server still sees nothing until Packed. Kept for 12 hours, like a staff login.
 */
const KEPT_FOR_MS = 12 * 60 * 60 * 1000
const PREFIX = 'packing-bag-'

type Kept = { saved_at: number; findings: Findings; picked: string[] }

/** Where a bag starts: the taps kept on this phone, if any, plus anything marked out of stock since. */
export function startingProgress(bag: Bag, now = Date.now()): { findings: Findings; picked: Picked } {
  const fresh = startingFindings(bag)
  forgetOldBags(now)
  const kept = read(bag.id)
  if (kept === null || now - kept.saved_at > KEPT_FOR_MS) return { findings: fresh, picked: new Set() }

  const food = new Set(bag.food.map((line) => line.variety_id))
  const substitutes = new Set(bag.substitutes.map((line) => line.variety_id))
  const picked: Picked = new Set(kept.picked)
  const missing = kept.findings.missing.filter((line) => food.has(line.variety_id))
  // Marked out of stock by someone else since the reload, and not looked at here yet.
  for (const line of fresh.missing) {
    if (!missing.some((m) => m.variety_id === line.variety_id) && !picked.has(lookedKey(line.variety_id))) {
      missing.push(line)
    }
  }
  const notOnShelf = kept.findings.not_on_shelf.filter((id) => substitutes.has(id))
  return { findings: { missing, not_on_shelf: notOnShelf }, picked }
}

export function keepProgress(bagId: number, findings: Findings, picked: Picked, now = Date.now()) {
  const kept: Kept = { saved_at: now, findings, picked: [...picked] }
  try {
    localStorage.setItem(PREFIX + bagId, JSON.stringify(kept))
  } catch {
    // A private window, or storage turned off: packing still works, the taps just aren't kept.
  }
}

/** Packed: the taps aren't needed any more. */
export function forgetProgress(bagId: number) {
  try {
    localStorage.removeItem(PREFIX + bagId)
  } catch {
    // Nothing was kept.
  }
}

function read(bagId: number): Kept | null {
  try {
    const text = localStorage.getItem(PREFIX + bagId)
    if (text === null) return null
    const kept = JSON.parse(text) as Kept
    const looksRight =
      typeof kept.saved_at === 'number' &&
      Array.isArray(kept.picked) &&
      Array.isArray(kept.findings?.missing) &&
      Array.isArray(kept.findings?.not_on_shelf)
    return looksRight ? kept : null
  } catch {
    return null
  }
}

/** Bags from an earlier day, or packed on another phone, are cleared away. */
function forgetOldBags(now: number) {
  try {
    for (const key of Object.keys(localStorage)) {
      if (!key.startsWith(PREFIX)) continue
      const kept = read(Number(key.slice(PREFIX.length)))
      if (kept === null || now - kept.saved_at > KEPT_FOR_MS) localStorage.removeItem(key)
    }
  } catch {
    // Storage turned off: nothing to clear.
  }
}
