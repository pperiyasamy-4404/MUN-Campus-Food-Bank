// Small pure helpers for the live countdowns and the hold bar (13 Nov).
// Pure, so they're easy to test: no clock, no page.

/** "in 2 h 14 min", "in 5 min", "in 40 s", or "now". For "Booking opens in ...". */
export function untilText(milliseconds: number): string {
  if (milliseconds <= 0) return 'now'
  const seconds = Math.ceil(milliseconds / 1000)
  if (seconds < 60) return `in ${seconds} s`
  const minutes = Math.ceil(seconds / 60)
  if (minutes < 60) return `in ${minutes} min`
  const hours = Math.floor(minutes / 60)
  const rest = minutes % 60
  if (hours < 24) return rest === 0 ? `in ${hours} h` : `in ${hours} h ${rest} min`
  const days = Math.floor(hours / 24)
  const restHours = hours % 24
  return restHours === 0 ? `in ${days} ${days === 1 ? 'day' : 'days'}` : `in ${days} d ${restHours} h`
}

/** How urgent the hold is: plenty of time, the last 2 minutes, or the last minute. */
export function holdLevel(secondsLeft: number): 'plenty' | 'soon' | 'now' {
  if (secondsLeft <= 60) return 'now'
  if (secondsLeft <= 120) return 'soon'
  return 'plenty'
}

/** The share of the hold still left, from 0 to 1, for the bar. */
export function holdShare(secondsLeft: number, holdMinutes: number): number {
  const total = holdMinutes * 60
  if (total <= 0) return 0
  return Math.min(1, Math.max(0, secondsLeft / total))
}
