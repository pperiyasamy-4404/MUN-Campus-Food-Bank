// The packing page's rules that live in the browser: what still needs a tap before
// Packed, and one look at food someone else marked out of stock (U7, decided 12 Nov).
import { describe, expect, it } from 'vitest'
import type { Bag, BagFood, PackingPlan } from '../api.ts'
import {
  foodKey,
  foundAfterAll,
  lookedKey,
  startingFindings,
  stillToTick,
  substituteKey,
  withMissing,
  withPicked,
  type Picked,
} from './packingTools.ts'

function food(varietyId: number, variety: string, ranOutAt: string | null = null): BagFood {
  return { variety_id: varietyId, variety, item: variety, quantity: 1, missing: 0, ran_out_at: ranOutAt }
}

function bag(...lines: BagFood[]): Bag {
  return {
    id: 1, code: 'K3P', pickup_date: '2026-11-16', starts_at: '2026-11-16T15:30:00-03:30', status: 'booked',
    packed_at: null, packed_by: null, can_pack: true, why_not: null, can_unpack: false,
    food: lines, substitutes: [], sticky_note: [],
  }
}

const NO_SUBSTITUTES: PackingPlan = { substitutes: [], sticky_note: [], in_bag: 0, booked: 0, uses: [] }
const NOTHING: Picked = new Set()

describe('stillToTick', () => {
  it('counts every line until it is Picked', () => {
    const oats = food(1, 'Quick oats')
    const rice = food(2, 'White rice')
    const findings = startingFindings(bag(oats, rice))

    expect(stillToTick(bag(oats, rice), findings, NO_SUBSTITUTES, NOTHING)).toBe(2)
    expect(stillToTick(bag(oats, rice), findings, NO_SUBSTITUTES, withPicked(NOTHING, foodKey(1), true))).toBe(1)
  })

  it('counts a line marked Out of stock as done', () => {
    const oil = food(3, 'Sunflower oil')
    const findings = withMissing(startingFindings(bag(oil)), 3, 1)

    expect(stillToTick(bag(oil), findings, NO_SUBSTITUTES, NOTHING)).toBe(0)
  })

  it('wants a substitute the plan puts in to be Picked, and one it no longer needs taken out', () => {
    const oil = food(3, 'Sunflower oil')
    const findings = withMissing(startingFindings(bag(oil)), 3, 1)
    const riceGoesIn: PackingPlan = {
      ...NO_SUBSTITUTES,
      substitutes: [{ rank: 1, variety_id: 9, outcome: 'use', replaces: 'Sunflower oil' }],
    }
    const riceNotNeeded: PackingPlan = {
      ...NO_SUBSTITUTES,
      substitutes: [{ rank: 1, variety_id: 9, outcome: 'not_needed', replaces: null }],
    }
    const ricePicked = withPicked(NOTHING, substituteKey(9), true)

    expect(stillToTick(bag(oil), findings, riceGoesIn, NOTHING)).toBe(1)
    expect(stillToTick(bag(oil), findings, riceGoesIn, ricePicked)).toBe(0)
    // The oil turned up after all: the rice in the bag has to come out (Taken out).
    expect(stillToTick(bag(oil), findings, riceNotNeeded, ricePicked)).toBe(1)
  })
})

describe('food someone else marked out of stock', () => {
  const peanutButter = food(5, 'Smooth peanut butter', '2026-11-16T12:26:00-03:30')

  it('opens as out of stock, so the substitutes show straight away', () => {
    expect(startingFindings(bag(peanutButter)).missing).toEqual([{ variety_id: 5, how_many: 1 }])
  })

  it('still needs one look before Packed: one wrong tap must not spread to every bag', () => {
    const findings = startingFindings(bag(peanutButter))

    expect(stillToTick(bag(peanutButter), findings, NO_SUBSTITUTES, NOTHING)).toBe(1)
    const stillOut = withPicked(NOTHING, lookedKey(5), true)
    expect(stillToTick(bag(peanutButter), findings, NO_SUBSTITUTES, stillOut)).toBe(0)
  })

  it('is sent with Packed as found when the volunteer taps Found it', () => {
    const findings = withMissing(startingFindings(bag(peanutButter)), 5, 0)

    expect(foundAfterAll(bag(peanutButter), findings)).toEqual([5])
    expect(foundAfterAll(bag(peanutButter), startingFindings(bag(peanutButter)))).toEqual([])
  })
})
