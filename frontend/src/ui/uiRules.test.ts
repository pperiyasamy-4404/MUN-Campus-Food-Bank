// The small rules behind the new touches (13 Nov): countdowns, the hold bar,
// the food filters and the packing progress bar.
import { describe, expect, it } from 'vitest'
import type { Bag, Category, PackingPlan } from '../api.ts'
import { countVarieties, filterFood, fits } from '../foodFilter.ts'
import { linesToTick, startingFindings, stillToTick, substituteKey, withPicked, foodKey } from '../pages/packingTools.ts'
import { holdLevel, holdShare, untilText } from './timing.ts'

describe('untilText: "Booking opens in ..."', () => {
  it('says seconds, minutes, hours and days, rounding up so it never says "in 0 min" early', () => {
    expect(untilText(-5)).toBe('now')
    expect(untilText(40_000)).toBe('in 40 s')
    expect(untilText(61_000)).toBe('in 2 min')
    expect(untilText(60 * 60_000)).toBe('in 1 h')
    expect(untilText((2 * 60 + 14) * 60_000)).toBe('in 2 h 14 min')
    expect(untilText(24 * 60 * 60_000)).toBe('in 1 day')
    expect(untilText((26 * 60) * 60_000)).toBe('in 1 d 2 h')
  })
})

describe('the hold bar', () => {
  it('turns amber in the last 2 minutes and red in the last one', () => {
    expect(holdLevel(600)).toBe('plenty')
    expect(holdLevel(120)).toBe('soon')
    expect(holdLevel(60)).toBe('now')
  })

  it('is full at the start and empty at the end, never past either', () => {
    expect(holdShare(600, 10)).toBe(1)
    expect(holdShare(300, 10)).toBe(0.5)
    expect(holdShare(-3, 10)).toBe(0)
    expect(holdShare(700, 10)).toBe(1)
  })
})

describe('the food filters', () => {
  const food: Category[] = [
    {
      name: 'Breakfast',
      items: [
        {
          id: 1, name: 'Peanut butter', photo_url: null,
          varieties: [{ id: 11, name: 'Smooth peanut butter', stock: 8, few_left: false, tags: ['Vegetarian', 'Contains nuts'] }],
        },
        {
          id: 2, name: 'Oats', photo_url: null,
          varieties: [{ id: 21, name: 'Quick oats', stock: null, few_left: false, tags: ['Vegetarian'] }],
        },
      ],
    },
    {
      name: 'Protein',
      items: [
        {
          id: 3, name: 'Canned beans', photo_url: null,
          varieties: [{ id: 31, name: 'Black beans', stock: null, few_left: false, tags: ['Vegetarian', 'Halal', 'Gluten-free'] }],
        },
      ],
    },
  ]

  it('"Nut-free" means no "Contains nuts" tag, and the others need their tag', () => {
    expect(fits(['Vegetarian', 'Contains nuts'], ['Nut-free'])).toBe(false)
    expect(fits(['Vegetarian'], ['Nut-free', 'Vegetarian'])).toBe(true)
    expect(fits(['Vegetarian'], ['Halal'])).toBe(false)
  })

  it('keeps only what fits, and drops empty items and categories', () => {
    const halal = filterFood(food, ['Halal'])
    expect(halal.map((category) => category.name)).toEqual(['Protein'])
    expect(countVarieties(filterFood(food, ['Nut-free']))).toBe(2)
    expect(filterFood(food, [])).toBe(food)
    expect(countVarieties(food)).toBe(3)
  })
})

describe('the packing progress bar', () => {
  const bag: Bag = {
    id: 1, code: 'K3P', pickup_date: '2026-11-16', starts_at: '2026-11-16T15:30:00-03:30', status: 'booked',
    packed_at: null, packed_by: null, can_pack: true, why_not: null, can_unpack: false, substitutes: [], sticky_note: [],
    food: [
      { variety_id: 1, variety: 'Quick oats', item: 'Oats', quantity: 1, missing: 0, ran_out_at: null },
      { variety_id: 2, variety: 'Sunflower oil', item: 'Cooking oil', quantity: 1, missing: 0, ran_out_at: null },
    ],
  }
  const riceGoesIn: PackingPlan = {
    substitutes: [{ rank: 1, variety_id: 9, outcome: 'use', replaces: 'Sunflower oil' }], sticky_note: [], in_bag: 2, booked: 2, uses: [9],
  }

  it('counts the food lines and the substitutes that go in, and fills as lines are ticked', () => {
    const findings = startingFindings(bag)
    const nothing = new Set<string>()
    expect(linesToTick(bag, riceGoesIn, nothing)).toBe(3)
    const oatsAndRice = withPicked(withPicked(nothing, foodKey(1), true), substituteKey(9), true)
    const done = linesToTick(bag, riceGoesIn, oatsAndRice) - stillToTick(bag, findings, riceGoesIn, oatsAndRice)
    expect(done).toBe(2)
  })
})
