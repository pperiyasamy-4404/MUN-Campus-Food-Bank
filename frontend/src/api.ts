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
