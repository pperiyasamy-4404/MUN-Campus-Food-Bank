// Small rules the pages check before asking the server (the server checks them again).
import { describe, expect, it } from 'vitest'
import type { ShelfFood, StockVariety } from './api.ts'
import { NO_OLD_SYSTEM_ANSWER, oldSystemAnswer, oldSystemProblem } from './oldSystem.ts'
import { asChoices, whyNotMore } from './pages/counterTools.ts'
import { count, forTimeBox, sayWeekdays } from './pages/coordinatorTools.ts'
import { needsCounting } from './pages/stockTools.ts'
import { showClock, showDate, showDay, showDayAndClock } from './time.ts'

describe('Newfoundland time, wherever the browser is (T1)', () => {
  it('shows a moment in St. John’s time, half hour and all', () => {
    // 19:00 UTC on 16 November is 3:30 p.m. in St. John's (UTC−3:30 in winter).
    expect(showClock('2026-11-16T19:00:00Z')).toBe('3:30 p.m.')
    expect(showDayAndClock('2026-11-15T20:30:00Z')).toBe('Sunday, November 15 at 5:00 p.m.')
  })

  it('knows summer time (UTC−2:30)', () => {
    expect(showClock('2026-07-06T18:00:00Z')).toBe('3:30 p.m.')
  })

  it('shows a late evening on its own Newfoundland date, not the UTC one', () => {
    // 01:00 UTC on 17 November is still 9:30 p.m. on Monday the 16th in St. John's.
    expect(showDay('2026-11-17T01:00:00Z')).toBe('Monday, November 16')
  })

  it('never moves a pickup date to the day before', () => {
    expect(showDate('2026-11-16')).toBe('Monday, November 16')
  })
})

describe('the counter: the same limits as booking (I3)', () => {
  const oats = (varietyId: number, variety: string, stock: number | null): ShelfFood => ({
    variety_id: varietyId, variety, item_id: 1, item: 'Oats', photo_url: null, stock, few_left: false,
  })
  const quick = oats(1, 'Quick oats', null)
  const steelCut = oats(2, 'Steel-cut oats', 3)
  const shelf = [quick, steelCut]

  it('allows one of each item, counting all its kinds together', () => {
    expect(whyNotMore(steelCut, {}, shelf, 13, 1, 0)).toBeNull()
    expect(whyNotMore(steelCut, { 1: 1 }, shelf, 13, 1, 0)).toBe('One Oats only')
  })

  it('counts what is in the bag already', () => {
    expect(whyNotMore(quick, {}, shelf, 13, 1, 1)).toBe('One Oats only')
  })

  it('stops at what is left, but food with no number never runs out here', () => {
    expect(whyNotMore(steelCut, { 2: 3 }, shelf, 13, 5, 0)).toBe('No more left')
    expect(whyNotMore(quick, { 1: 4 }, shelf, 13, 5, 0)).toBeNull()
  })

  it('stops at the room left in the bag', () => {
    expect(whyNotMore(quick, { 2: 1 }, shelf, 1, 5, 0)).toBe("That's all they can take")
  })

  it('sends only what was chosen', () => {
    expect(asChoices({ 1: 1, 2: 0 })).toEqual([{ variety_id: 1, quantity: 1 }])
  })
})

describe('the last pickup in the old system (decided 12 Nov)', () => {
  it('must be answered, one way or the other', () => {
    expect(oldSystemProblem(NO_OLD_SYSTEM_ANSWER)).toMatch(/^Choose their last pickup/)
    expect(oldSystemProblem({ on: '2026-11-12', never: false })).toBeNull()
    expect(oldSystemProblem({ on: '', never: true })).toBeNull()
  })

  it('sends no date when there was no pickup', () => {
    expect(oldSystemAnswer({ on: '2026-11-12', never: true })).toEqual({
      never_in_old_system: true,
      old_system_pickup_on: null,
    })
    expect(oldSystemAnswer({ on: '2026-11-12', never: false }).old_system_pickup_on).toBe('2026-11-12')
  })
})

describe('what needs checking on the Stock page', () => {
  const variety = (changes: Partial<StockVariety>): StockVariety => ({
    id: 1, name: 'Quick oats', shown: true, stock: null, few_left: false, booked_not_packed: 0, tag_ids: [],
    counted_at: null, counted_by: null, ran_out_at: null, found_at: null, ...changes,
  })
  const lastPickupEnded = '2026-11-16T20:00:00-03:30'

  it('never food with no number, unless it ran out while packing', () => {
    expect(needsCounting(variety({}), lastPickupEnded)).toBe(false)
    expect(needsCounting(variety({ ran_out_at: '2026-11-16T12:26:00-03:30' }), lastPickupEnded)).toBe(true)
    expect(needsCounting(variety({ found_at: '2026-11-16T12:40:00-03:30' }), lastPickupEnded)).toBe(true)
  })

  it('food with a number counted before the last pickup ended', () => {
    expect(needsCounting(variety({ stock: 6, counted_at: '2026-11-16T11:00:00-03:30' }), lastPickupEnded)).toBe(true)
    expect(needsCounting(variety({ stock: 6, counted_at: '2026-11-17T10:00:00-03:30' }), lastPickupEnded)).toBe(false)
  })

  it('never hidden food', () => {
    expect(needsCounting(variety({ shown: false, ran_out_at: '2026-11-16T12:26:00-03:30' }), lastPickupEnded)).toBe(false)
  })
})

describe('the coordinator pages', () => {
  it('say weekdays and counts in words', () => {
    expect(sayWeekdays([1, 4])).toBe('Monday and Thursday')
    expect(sayWeekdays([1, 3, 4])).toBe('Monday, Wednesday and Thursday')
    expect(count(1, 'booking')).toBe('1 booking')
    expect(count(3, 'booking')).toBe('3 bookings')
  })

  it('put the St. John’s time from the server straight into a time box', () => {
    expect(forTimeBox('2026-11-08T17:00:00-03:30')).toBe('2026-11-08T17:00')
  })
})
