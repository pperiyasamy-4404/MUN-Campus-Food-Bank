// Every time on screen is Newfoundland time, wherever the browser is (T1).
// A student whose laptop is still set to Toronto time still sees 3:30 pm.
const NEWFOUNDLAND = 'America/St_Johns'

const clock = new Intl.DateTimeFormat('en-CA', {
  timeZone: NEWFOUNDLAND,
  hour: 'numeric',
  minute: '2-digit',
})

const dayAndClock = new Intl.DateTimeFormat('en-CA', {
  timeZone: NEWFOUNDLAND,
  weekday: 'long',
  month: 'long',
  day: 'numeric',
  hour: 'numeric',
  minute: '2-digit',
})

// A pickup date has no time of day, like "2026-11-09". It is read as midnight UTC
// and shown in UTC. Shown in Newfoundland time instead, midnight UTC would be
// 8:30 pm the evening before, and Monday would show as Sunday.
const dateOnly = new Intl.DateTimeFormat('en-CA', {
  timeZone: 'UTC',
  weekday: 'long',
  month: 'long',
  day: 'numeric',
})

/** "3:30 p.m." */
export function showClock(moment: string): string {
  return clock.format(new Date(moment))
}

/** "Sunday, November 8 at 5:00 p.m." */
export function showDayAndClock(moment: string): string {
  return dayAndClock.format(new Date(moment))
}

/** "Monday, November 9" */
export function showDate(date: string): string {
  return dateOnly.format(new Date(`${date}T00:00:00Z`))
}
