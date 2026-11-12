import type { ReactNode } from 'react'

// Food shown as cards: the item's photo on top, its name, then its varieties.
// Used by the students' pages and the counter, so food looks the same everywhere.

/** The item's photo, or a simple drawing of a bowl if it has none yet. */
export function FoodPhoto({ url, name }: { url: string | null; name: string }) {
  if (url) return <img className="food-photo" src={url} alt={name} loading="lazy" />
  return (
    <div className="food-photo food-photo-none" aria-hidden="true">
      <svg viewBox="0 0 64 48" width="72" height="54">
        <path d="M8 22 h48 a24 18 0 0 1 -48 0 z" fill="currentColor" opacity=".35" />
        <path d="M14 22 c2-8 8-12 12-10 c3-6 12-6 14 0 c5-2 10 2 10 10" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" opacity=".5" />
        <rect x="24" y="40" width="16" height="4" rx="2" fill="currentColor" opacity=".35" />
      </svg>
    </div>
  )
}

/** One item as a card. The rows for its varieties go inside. */
export function FoodCard({
  name,
  category,
  photoUrl,
  badge,
  highlighted = false,
  children,
}: {
  name: string
  category?: string
  photoUrl: string | null
  // A small label on the photo, like "✓ 1 chosen".
  badge?: string
  highlighted?: boolean
  children: ReactNode
}) {
  return (
    <article className={highlighted ? 'food-card food-card-chosen' : 'food-card'}>
      <div className="food-photo-frame">
        <FoodPhoto url={photoUrl} name={name} />
        {badge && <span className="food-badge">{badge}</span>}
      </div>
      <div className="food-body">
        {category && <p className="food-category">{category}</p>}
        <h3 className="food-name">{name}</h3>
        <ul className="food-varieties">{children}</ul>
      </div>
    </article>
  )
}

/**
 * How much is left, in words: "6 left", "Out of stock", or, for food nobody
 * counts, "Few left" or "In stock" (decided 12 Nov).
 */
export function StockNote({ stock, fewLeft }: { stock: number | null; fewLeft: boolean }) {
  if (stock === 0) return <span className="stock-out">Out of stock</span>
  if (stock !== null) return <span className="stock-left">{stock} left</span>
  if (fewLeft) return <span className="stock-few">Few left</span>
  return <span className="stock-left">In stock</span>
}

/** One variety inside a card: its name and tags on the left, and whatever goes on the right. */
export function FoodRow({
  name,
  tags = [],
  note,
  dim = false,
  children,
}: {
  name: string
  tags?: string[]
  // Under the name, like "6 left".
  note?: ReactNode
  dim?: boolean
  children?: ReactNode
}) {
  return (
    <li className={dim ? 'food-row food-row-dim' : 'food-row'}>
      <div className="food-row-about">
        <span className="food-row-name">{name}</span>
        {tags.length > 0 && (
          <span className="food-tags">
            {tags.map((tag) => (
              <span key={tag} className="tag">
                {tag}
              </span>
            ))}
          </span>
        )}
        {note && <span className="food-row-note">{note}</span>}
      </div>
      {children && <div className="food-row-action">{children}</div>}
    </li>
  )
}
