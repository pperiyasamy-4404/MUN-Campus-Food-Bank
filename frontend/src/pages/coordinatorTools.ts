import { useEffect, useState } from 'react'

// What the coordinator's pages share: asking the server for a page, and a few
// ways of showing days and times.

export type Load<T> = { state: 'loading' } | { state: 'failed' } | { state: 'ready'; data: T }

/** Ask the server for a page. A new version asks again. Logged out (401) calls onLoggedOut. */
export function useStaffData<T>(path: string, version: number, onLoggedOut: () => void): Load<T> {
  const [load, setLoad] = useState<Load<T>>({ state: 'loading' })
  useEffect(() => {
    // If the page goes away before the answer comes, drop the answer.
    let stillWanted = true
    fetch(path)
      .then(async (response) => {
        if (response.status === 401) {
          if (stillWanted) onLoggedOut()
          return
        }
        if (!response.ok) throw new Error(`The server answered ${response.status}`)
        const data = (await response.json()) as T
        if (stillWanted) setLoad({ state: 'ready', data })
      })
      .catch(() => {
        if (stillWanted) setLoad({ state: 'failed' })
      })
    return () => {
      stillWanted = false
    }
  }, [path, version, onLoggedOut])
  return load
}

export const WEEKDAYS = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday']

/** "Monday and Thursday", from [1, 4]. */
export function sayWeekdays(weekdays: number[]): string {
  const names = weekdays.map((weekday) => WEEKDAYS[weekday - 1])
  return names.length > 1 ? `${names.slice(0, -1).join(', ')} and ${names[names.length - 1]}` : (names[0] ?? '')
}

/**
 * What a date-and-time box takes: "2026-11-08T17:00".
 *
 * The server sends St. John's times with their offset, like
 * "2026-11-08T17:00:00-03:30", so the first 16 characters are already the
 * St. John's date and time, wherever the browser is (T1).
 */
export function forTimeBox(moment: string): string {
  return moment.slice(0, 16)
}

/** Today's date in St. John's, like "2026-11-10". en-CA writes dates that way. */
export function todayInStJohns(): string {
  return new Intl.DateTimeFormat('en-CA', { timeZone: 'America/St_Johns' }).format(new Date())
}

/** "1 booking", "3 bookings". */
export function count(how_many: number, one: string, many = `${one}s`): string {
  return `${how_many} ${how_many === 1 ? one : many}`
}
