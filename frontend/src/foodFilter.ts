import type { Category } from './api.ts'

// The food filters (13 Nov): a student taps "Vegetarian" or "Gluten-free" and
// sees only food that fits. Pure, so it's easy to test.

// Only these two since 13 Nov night (the user's choice): Halal and Nut-free were taken off.
// Canned added 14 Nov (Prakash's choice): not a diet, but a tag like the others, so the
// same filter works ("Vegetarian" + "Canned" = vegetarian canned food).
export type Diet = 'Vegetarian' | 'Gluten-free' | 'Canned'

export const DIETS: Diet[] = ['Vegetarian', 'Gluten-free', 'Canned']

/** Does a variety with these tags fit every chosen diet? */
export function fits(tags: string[], wanted: Diet[]): boolean {
  return wanted.every((diet) => tags.includes(diet))
}

/**
 * Only the varieties that fit, and only the items and categories that still
 * have one. Nothing chosen: everything, unchanged.
 */
export function filterFood(categories: Category[], wanted: Diet[]): Category[] {
  if (wanted.length === 0) return categories
  return categories
    .map((category) => ({
      ...category,
      items: category.items
        .map((item) => ({ ...item, varieties: item.varieties.filter((variety) => fits(variety.tags, wanted)) }))
        .filter((item) => item.varieties.length > 0),
    }))
    .filter((category) => category.items.length > 0)
}

/** How many varieties there are, for "Showing 9 of 25". */
export function countVarieties(categories: Category[]): number {
  return categories.reduce((sum, category) => sum + category.items.reduce((n, item) => n + item.varieties.length, 0), 0)
}
