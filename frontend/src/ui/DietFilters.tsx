import { DIETS, type Diet } from '../foodFilter.ts'

/**
 * Filter chips: "Show only: Vegetarian, Halal, Gluten-free, Nut-free" (13 Nov).
 * Each is a toggle button (aria-pressed), so a screen reader says "pressed".
 * The count says how much is showing, and is read out when it changes.
 */
export function DietFilters({
  chosen,
  onChange,
  showing,
  of,
}: {
  chosen: Diet[]
  onChange: (diets: Diet[]) => void
  showing: number
  of: number
}) {
  const toggle = (diet: Diet) =>
    onChange(chosen.includes(diet) ? chosen.filter((one) => one !== diet) : [...chosen, diet])

  return (
    <div className="filters" role="group" aria-label="Show only food that is">
      <span className="filters-label" aria-hidden="true">
        Show only:
      </span>
      {DIETS.map((diet) => (
        <button key={diet} type="button" className="chip" aria-pressed={chosen.includes(diet)} onClick={() => toggle(diet)}>
          {diet}
        </button>
      ))}
      {chosen.length > 0 && (
        <>
          <button type="button" className="link-button" onClick={() => onChange([])}>
            Clear
          </button>
          <span className="filters-count" role="status">
            Showing {showing} of {of}
          </span>
        </>
      )}
    </div>
  )
}
