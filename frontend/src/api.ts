import { useEffect, useState } from 'react'

// The shapes the server sends. They match the response models in backend/app/routes/.

export type BookingStatus = 'not_open_yet' | 'open' | 'booking_over' | 'day_closed'

export type Slot = {
  id: number
  starts_at: string // like "2026-11-09T15:30:00-03:30"
  places_left: number
}

export type PickupDay = {
  pickup_date: string // like "2026-11-09"
  booking_opens_at: string
  booking_closes_at: string
  booking_status: BookingStatus
  closed_reason: string | null
  slots: Slot[]
}

export type Variety = {
  id: number
  name: string
  stock: number | null // null for extras, which only show as "may be available"
  tags: string[]
}

export type Item = {
  id: number
  name: string
  photo_url: string | null // one photo per item, shared by its varieties
  varieties: Variety[]
}

export type Category = {
  name: string
  items: Item[]
}

export type Food = {
  bookable: Category[]
  extras: Category[]
}

export type ServerData<T> =
  | { state: 'loading' }
  | { state: 'ready'; data: T }
  | { state: 'failed' }

/** Ask the server for something once, when the component first shows. */
export function useServerData<T>(path: string): ServerData<T> {
  const [result, setResult] = useState<ServerData<T>>({ state: 'loading' })

  useEffect(() => {
    // If the component goes away before the answer comes, drop the answer.
    let stillWanted = true
    fetch(path)
      .then((response) => {
        if (!response.ok) {
          throw new Error(`The server answered ${response.status}`)
        }
        return response.json() as Promise<T>
      })
      .then((data) => {
        if (stillWanted) setResult({ state: 'ready', data })
      })
      .catch(() => {
        if (stillWanted) setResult({ state: 'failed' })
      })
    return () => {
      stillWanted = false
    }
  }, [path])

  return result
}

// ---------- accounts (backend/app/routes/login.py and accounts.py) ----------

/** Who is logged in on this browser. The server sends null if nobody is. */
export type Me =
  | { kind: 'student'; password_reset_at: string | null }
  | { kind: 'staff'; username: string; role: 'volunteer' | 'coordinator' }

/** A setup code, shown once. The server never sends it again. */
export type IssuedCode = {
  setup_code: string // like "K7QM-4TXP"
  expires_at: string
  new_account: boolean
}

export type Volunteer = {
  id: number
  username: string
  password_set: boolean
  setup_code_expires_at: string | null
  switched_off_at: string | null
}

/**
 * The server's answer to a form.
 *
 * When it says no, `message` is in words the person can read, like "That ID
 * number and password don't match.", and `fields` says which box was wrong,
 * like { id_number: "Enter the 9 digits on your MUN card." }.
 */
export type Answer<T> =
  | { ok: true; data: T }
  | { ok: false; status: number; message: string; fields: Record<string, string> }

/**
 * Send a form to the server, with the values in the body: POST to add or do
 * something, PUT to replace a list (like a variety's tags), PATCH to change a name,
 * DELETE to let go of something (like a held time).
 *
 * Never put an ID number or password in the web address: addresses end up in
 * the browser history and in server logs (P10).
 */
export async function send<T>(
  path: string,
  body: object = {},
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE' = 'POST',
): Promise<Answer<T>> {
  let response: Response
  try {
    response = await fetch(path, {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
  } catch {
    return problem(0, "Couldn't reach the server. Check your internet connection and try again.")
  }

  const answer: unknown = response.status === 204 ? null : await response.json().catch(() => null)
  if (response.ok) {
    return { ok: true, data: answer as T }
  }
  const detail = (answer as { detail?: unknown } | null)?.detail
  if (typeof detail === 'string') {
    return problem(response.status, detail)
  }
  if (Array.isArray(detail)) {
    // A form problem (422): one message per box. loc ["body", "id_number"] is
    // "id_number", and loc ["body", "first_variety", "name"] is "first_variety.name".
    const fields: Record<string, string> = {}
    for (const { loc, msg } of detail as { loc: (string | number)[]; msg: string }[]) {
      fields[loc.slice(1).join('.') || 'form'] ??= msg
    }
    return { ok: false, status: response.status, message: 'Please fix the boxes marked in red.', fields }
  }
  return problem(response.status, 'Something went wrong on the server. Please try again.')
}

function problem(status: number, message: string): Answer<never> {
  return { ok: false, status, message, fields: {} }
}

// ---------- food and stock, for staff (backend/app/routes/stock.py) ----------

export type StockVariety = {
  id: number
  name: string
  shown: boolean
  stock: number // how many more students can book it
  booked_not_packed: number // still on the shelf, already promised
  tag_ids: number[]
  counted_at: string | null
  counted_by: string | null
  ran_out_at: string | null // none on the shelf while packing. Cleared by the next count (U7).
}

export type StockItem = {
  id: number
  name: string
  is_extra: boolean
  photo_url: string | null
  varieties: StockVariety[]
}

export type StockCategory = {
  id: number
  name: string
  items: StockItem[]
}

export type TagChoice = { id: number; name: string }

export type StockPage = {
  categories: StockCategory[]
  tags: TagChoice[]
  next_booking: {
    pickup_date: string
    booking_opens_at: string
    booking_closes_at: string
    booking_status: BookingStatus
  } | null
  last_pickup_ended_at: string | null
}

// ---------- a student's booking (backend/app/routes/booking.py) ----------

export type Limits = {
  item_limit: number
  max_per_item: number
  substitute_limit: number
  hold_minutes: number
}

export type HeldTime = {
  slot_id: number
  pickup_date: string
  starts_at: string
  held_until: string
  seconds_left: number // counted by the server, so a phone with a wrong clock still counts down right
}

export type BookingDetails = {
  code: string // what the student says at the counter, like K3P
  status: string
  pickup_date: string
  starts_at: string
  booked_at: string
  cancel_until: string
  can_cancel: boolean
  items: { variety: string; item: string; quantity: number }[]
  substitutes: { rank: number; variety: string; item: string }[]
}

export type MyBooking = {
  limits: Limits
  booking: BookingDetails | null
  hold: HeldTime | null
  next_pickup_allowed_on: string | null
  // The food bank closed the day they had booked, so the booking was cancelled (S7). Until that day is over.
  closed_day: { pickup_date: string; reason: string } | null
}

// ---------- packing, for staff (backend/app/routes/packing.py) ----------

export type QueueBag = {
  id: number
  code: string
  starts_at: string
  status: string
  things: number
  ran_out: string[] // booked food another volunteer found none of on the shelf (U7)
  packed_at: string | null
  packed_by: string | null
}

export type PackingQueue = {
  // The day being packed now, or packed next. null if no pickup days are coming up.
  day: {
    pickup_date: string
    packing_starts_at: string // when booking closes (K1)
    pickup_starts_at: string | null
    no_show_at: string
    can_pack: boolean
    why_not: string | null
  } | null
  bags: QueueBag[]
}

export type BagFood = {
  variety_id: number
  variety: string
  item: string
  quantity: number
  missing: number // saved when the bag is packed, 0 before
  ran_out_at: string | null // a volunteer found none on the shelf, maybe for another bag
}

export type BagSubstitute = {
  rank: number
  variety_id: number
  variety: string
  item: string
  replaced: string | null // once packed: the booked food it went in for
}

export type Bag = {
  id: number
  code: string
  pickup_date: string
  starts_at: string
  status: string
  packed_at: string | null
  packed_by: string | null
  can_pack: boolean
  why_not: string | null
  can_unpack: boolean // packed by mistake: can be undone until the bag is handed over
  food: BagFood[]
  substitutes: BagSubstitute[]
  sticky_note: string[] // once packed: what was written on the bag (U8)
}

/** What happens to one substitute, by the refill rule (U4). */
export type Outcome = 'use' | 'not_on_shelf' | 'none_left' | 'already_has_item' | 'not_needed'

export type PackingPlan = {
  substitutes: { rank: number; variety_id: number; outcome: Outcome; replaces: string | null }[]
  sticky_note: string[]
  in_bag: number // fewer than booked: the student chooses the rest at the counter (U6)
  booked: number
  uses: number[] // the substitutes to put in. Sent back with Packed.
}

// ---------- the counter, for staff (backend/app/routes/counter.py) ----------

export type ShelfFood = {
  variety_id: number
  variety: string
  item_id: number
  item: string
  photo_url: string | null
  stock: number // left that nobody booked
}

export type CounterPage = {
  pickup_date: string | null
  is_open: boolean
  why_not: string | null // like "The counter opens when booking closes, at 12:00 p.m."
  // Walk-ins only during pickup hours (W3).
  walk_ins_open: boolean
  walk_ins_why_not: string | null // like "Walk-ins are served from 3:30 p.m. to 5:30 p.m., during pickup hours."
  limits: { item_limit: number; max_per_item: number }
  food: ShelfFood[]
  extras: ShelfFood[] // one of each extra item (E3)
}

export type BagAtCounter = {
  id: number
  code: string
  starts_at: string
  status: string
  why_not: string | null // like "Bag K3P isn't packed yet..."
  packed_by: string | null
  picked_up_at: string | null
  picked_up_by: string | null
  contents: { variety: string; item_id: number; item: string; quantity: number }[]
  sticky_note: string[]
  short: number // things the substitutes couldn't replace: chosen from the shelf (U6)
  given_at_counter: { variety: string; item: string; quantity: number; is_extra: boolean }[] // once picked up
}

export type HandedOver = {
  code: string
  picked_up_at: string
  next_pickup_on: string
}

export type WalkInCheck = {
  can_serve: boolean
  why_not: string | null
  new_account: boolean // no account for this card yet: recording the walk-in makes one
  cancels: { pickup_date: string; code: string } | null // W4: their booking for a later day
}

export type WalkInDone = {
  served_at: string
  things: number
  extras: number
  new_account: boolean
  cancelled: { pickup_date: string; code: string } | null
  next_pickup_on: string
}

// ---------- fixing a pickup marked wrong (backend/app/routes/fixes.py) ----------

export type FixBag = {
  id: number
  code: string
  starts_at: string
  status: 'no_show' | 'picked_up'
  picked_up_at: string | null
  picked_up_by: string | null
  why_not: string | null // like "Bag K3P was never packed, so it can't have been handed over."
}

export type FixPage = {
  days: string[] // pickup days that are over and still have bags on record, newest first
  day: string | null // the one shown
  fix_before: string | null // when booking opens for the next pickup day, if still to come (B6)
  bags: FixBag[]
}

// ---------- the coordinator (backend/app/routes/days.py, settings.py, totals.py) ----------

export type CoordinatorDay = {
  pickup_date: string
  booking_opens_at: string
  booking_closes_at: string
  pickup_starts_at: string
  pickup_ends_at: string
  no_show_at: string
  booking_status: BookingStatus
  closed_reason: string | null
  booked: number // bookings still to come
  packed: number // of those, bags already packed
  // Why each change can't be made, like "Booking for Monday, November 9 is over, and packing has started."
  why_not_close: string | null
  why_not_reopen: string | null
  why_not_move: string | null
}

export type DaysPage = {
  days: CoordinatorDay[] // not over yet, from today
  pickup_weekdays: number[] // 1 is Monday
  close_until: string // the furthest date that can be closed
}

export type ClosedDay = {
  day: CoordinatorDay
  cancelled: number
  were_packed: number
}

export type PickupHoursRow = {
  weekday: number // 1 is Monday, 7 is Sunday
  starts_at: string // "15:30"
  ends_at: string
}

export type SettingsValues = {
  pickup_gap_days: number
  slot_minutes: number
  slot_capacity: number
  hold_minutes: number
  item_limit: number
  max_per_item: number
  substitute_limit: number
  booking_opens_days_before: number
  booking_opens_time: string // "17:00"
  booking_closes_time: string
  no_show_time: string
  no_shows_count: boolean
  retention_days: number
  setup_code_days: number
  login_tries: number
  login_window_minutes: number
  pickup_hours: PickupHoursRow[]
}

export type SettingsPage = {
  settings: SettingsValues
  days_made: string[] // from tomorrow: they keep their own times
  days_ahead: number
  changed_at: string | null
  changed_by: string | null
}

/** Any number under 5 comes as "fewer than 5". The real one never leaves the server (P12). */
export type Shown = number | 'fewer than 5'

export type Week = {
  week_starts_on: string // the Monday
  picked_up: Shown
  walk_ins: Shown
  no_shows: Shown
  cancelled: Shown
  items: { item: string; given_out: Shown }[]
}

export type TotalsPage = {
  weeks: Week[]
}
