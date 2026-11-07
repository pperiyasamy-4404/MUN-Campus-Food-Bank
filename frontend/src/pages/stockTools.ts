import { send, type Answer, type StockPage, type StockVariety, type TagChoice } from '../api.ts'

/** What every part of the stock page needs from the page itself. */
export type StockTools = {
  tags: TagChoice[]
  coordinator: boolean
  /** Ask the server for the whole page again, after adding or changing food. */
  reload: () => void
  /** A saved count changes one row: put the server's answer in its place. */
  counted: (variety: StockVariety) => void
  /** The server said "Please log in." */
  loggedOut: () => void
}

/** Send a change, and go back to the login page if the staff login has run out. */
export async function change<T>(
  tools: StockTools,
  path: string,
  body: object = {},
  method: 'POST' | 'PUT' | 'PATCH' = 'POST',
): Promise<Answer<T>> {
  const answer = await send<T>(path, body, method)
  if (!answer.ok && answer.status === 401) tools.loggedOut()
  return answer
}

/**
 * Shown food that hasn't been counted since the last pickup ended. Pickups and
 * walk-ins have changed the shelf since, so the count should be done again
 * before booking opens (I8). Food a volunteer found none of while packing needs
 * a count too: until then it can't be booked, and bags with it are flagged (U7).
 * Hidden food doesn't need counting.
 */
export function needsCounting(variety: StockVariety, lastPickupEndedAt: string | null): boolean {
  if (!variety.shown) return false
  if (variety.counted_at === null || variety.ran_out_at !== null) return true
  return lastPickupEndedAt !== null && new Date(variety.counted_at) < new Date(lastPickupEndedAt)
}

/** The page, with one variety swapped for the server's newer copy. */
export function withVariety(page: StockPage, newer: StockVariety): StockPage {
  return {
    ...page,
    categories: page.categories.map((category) => ({
      ...category,
      items: category.items.map((item) => ({
        ...item,
        varieties: item.varieties.map((variety) => (variety.id === newer.id ? newer : variety)),
      })),
    })),
  }
}
