import type { Category } from './api.ts'

// The food filters (13 Nov): a student taps "Vegetarian" or "Gluten-free" and
// sees only food that fits. Pure, so it's easy to test.

export type Diet = 'Vegetarian' | 'Halal' | 'Gluten-free' | 'Nut-free'

export const DIETS: Diet[] = ['Vegetarian', 'Halal', 'Gluten-free', 'Nut-free']

/** Does a variety with these tags fit every chosen diet? "Nut-free" means no "Contains nuts" tag. */
export function fits(tags: string[], wanted: Diet[]): boolean {
  return wanted.every((diet) => (diet === 'Nut-free' ? !tags.includes('Contains nuts') : tags.includes(diet)))
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
