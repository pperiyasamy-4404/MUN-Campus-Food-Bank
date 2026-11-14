// A time tapped on the home page before logging in (13 Nov night). It rides along
// in the page address's hidden state (not in the address itself: P10) from the
// home page, through Log in or Set up, to the Book page, which then holds that
// time straight away, as if it had been tapped there.

export type WantedSlot = { slotId: number; label: string }

/** The state to pass to navigate() or <Link state>. */
export function wantSlot(slotId: number, label: string): { wantedSlot: WantedSlot } {
  return { wantedSlot: { slotId, label } }
}

/** The wanted time from a page's location state, if there is one. */
export function wantedSlot(state: unknown): WantedSlot | null {
  if (typeof state !== 'object' || state === null || !('wantedSlot' in state)) return null
  const wanted = (state as { wantedSlot: unknown }).wantedSlot
  if (typeof wanted !== 'object' || wanted === null) return null
  const { slotId, label } = wanted as Partial<WantedSlot>
  return typeof slotId === 'number' && typeof label === 'string' ? { slotId, label } : null
}

// Each wanted time is used once: going back to choosing a time afterwards
// (Choose a different time) must not hold it again. Keyed by the history entry.
const used = new Set<string>()

/** True the first time it's asked for this history entry, false after that. */
export function firstTimeFor(locationKey: string): boolean {
  if (used.has(locationKey)) return false
  used.add(locationKey)
  return true
}
