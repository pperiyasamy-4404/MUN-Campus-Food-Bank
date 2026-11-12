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
