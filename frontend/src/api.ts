import { useEffect, useState } from 'react'

// The shapes the server sends. They match the response models in backend/app/routes/.

export type BookingStatus = 'not_open_yet' | 'open' | 'booking_over' | 'day_closed'

export type Slot = {
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
  name: string
  stock: number | null // null for extras, which only show as "may be available"
  tags: string[]
}

export type Item = {
  name: string
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
 * Send a form to the server, always as a POST with the values in the body.
 *
 * Never put an ID number or password in the web address: addresses end up in
 * the browser history and in server logs (P10).
 */
export async function send<T>(path: string, body: object = {}): Promise<Answer<T>> {
  let response: Response
  try {
    response = await fetch(path, {
      method: 'POST',
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
    // A form problem (422): one message per box, like loc ["body", "id_number"].
    const fields: Record<string, string> = {}
    for (const { loc, msg } of detail as { loc: (string | number)[]; msg: string }[]) {
      fields[String(loc[1] ?? 'form')] ??= msg
    }
    return { ok: false, status: response.status, message: 'Please fix the boxes marked in red.', fields }
  }
  return problem(response.status, 'Something went wrong on the server. Please try again.')
}

function problem(status: number, message: string): Answer<never> {
  return { ok: false, status, message, fields: {} }
}
