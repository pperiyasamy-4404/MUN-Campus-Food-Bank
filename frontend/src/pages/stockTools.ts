import { send, type Answer, type StockPage, type StockVariety, type TagChoice } from '../api.ts'

/** What every part of the stock page needs from the page itself. */
export type StockTools = {
  tags: TagChoice[]
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
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE' = 'POST',
): Promise<Answer<T>> {
  const answer = await send<T>(path, body, method)
  if (!answer.ok && answer.status === 401) tools.loggedOut()
  return answer
}

/**
 * Shown food that needs a look before booking opens (I8):
 * - food a volunteer found none of while packing: until someone checks the
 *   shelf it can't be booked, and bags with it are flagged (U7);
 * - food marked out of stock, then found by another volunteer (Found it):
 *   there's some, but nobody knows how much, so it can't be booked yet;
 * - food with a number that hasn't been counted since the last pickup ended:
 *   pickups and walk-ins have changed the shelf since.
 * Food with no number never needs counting: that's the point of it (decided 12 Nov).
 * Hidden food doesn't need anything.
 */
export function needsCounting(variety: StockVariety, lastPickupEndedAt: string | null): boolean {
  if (!variety.shown) return false
  if (variety.ran_out_at !== null || variety.found_at !== null) return true
  if (variety.stock === null) return false
  if (variety.counted_at === null) return true
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

/**
 * A photo from the phone or computer, made ready to send: shrunk to at most
 * 800 pixels wide and saved as a JPEG. Phone photos are often 3 to 5 MB, and
 * the server takes 2 MB at most. Drawing it again also drops the hidden details
 * phones add to photos, like where it was taken.
 */
export async function shrinkPhoto(file: File): Promise<Blob> {
  const picture = await createImageBitmap(file)
  const scale = Math.min(1, 800 / picture.width)
  const canvas = document.createElement('canvas')
  canvas.width = Math.round(picture.width * scale)
  canvas.height = Math.round(picture.height * scale)
  canvas.getContext('2d')?.drawImage(picture, 0, 0, canvas.width, canvas.height)
  picture.close()
  return new Promise((resolve, reject) =>
    canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error('Could not read that photo'))), 'image/jpeg', 0.82),
  )
}

/** Send an item's new photo. The answer is a problem in words, or null if it worked. */
export async function uploadPhoto(tools: StockTools, itemId: number, photo: Blob): Promise<string | null> {
  let response: Response
  try {
    response = await fetch(`/api/items/${itemId}/photo`, {
      method: 'PUT',
      headers: { 'Content-Type': 'image/jpeg' },
      body: photo,
    })
  } catch {
    return "Couldn't reach the server. Check your internet connection and try again."
  }
  if (response.ok) return null
  if (response.status === 401) tools.loggedOut()
  const answer = (await response.json().catch(() => null)) as { detail?: unknown } | null
  return typeof answer?.detail === 'string' ? answer.detail : 'The photo could not be saved. Please try again.'
}
