import { useEffect, useId, useRef, useState, type ReactNode } from 'react'
import { Icon } from './ui/Icon.tsx'

// Food shown as cards: the item's photo on top, its name, then its varieties.
// Used by the students' pages and the counter, so food looks the same everywhere.
//
// Since 13 Nov a card opens into a bigger pop-up card: tap the photo or the name.
// The pop-up shows a large photo and the same rows, with the same buttons, so a
// student can add food from there too.

/** The item's photo, fading in once it has arrived, or a simple drawing of a bowl if it has none yet. */
export function FoodPhoto({ url, name, eager = false }: { url: string | null; name: string; eager?: boolean }) {
  const [loaded, setLoaded] = useState(false)
  if (url) {
    return (
      <img
        className={loaded ? 'food-photo fades loaded' : 'food-photo fades'}
        src={url}
        alt={name}
        loading={eager ? 'eager' : 'lazy'}
        onLoad={() => setLoaded(true)}
        onError={() => setLoaded(true)}
      />
    )
  }
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
  const [open, setOpen] = useState(false)

  return (
    <article className={highlighted ? 'food-card food-card-chosen' : 'food-card'}>
      {/* The photo opens the card too, for a mouse or a finger. The name below is the
          same thing as a real button, for the keyboard and screen readers. */}
      <div className="food-photo-frame card-photo" onClick={() => setOpen(true)}>
        <FoodPhoto url={photoUrl} name={name} />
        {badge && <span className="food-badge">{badge}</span>}
        <span className="card-open-hint" aria-hidden="true">
          View
        </span>
      </div>
      <div className="food-body">
        {category && <p className="food-category">{category}</p>}
        <h3 className="food-name">
          <button type="button" className="card-open card-open-title" aria-haspopup="dialog" onClick={() => setOpen(true)}>
            {name}
            <span className="visually-hidden">: see more</span>
          </button>
        </h3>
        <ul className="food-varieties">{children}</ul>
      </div>
      {open && (
        <FoodDetails name={name} category={category} photoUrl={photoUrl} badge={badge} onClose={() => setOpen(false)}>
          {children}
        </FoodDetails>
      )}
    </article>
  )
}

/**
 * The pop-up card: the browser's own <dialog>, so the keyboard stays inside it,
 * Escape closes it, and the focus goes back to the card afterwards.
 */
function FoodDetails({
  name,
  category,
  photoUrl,
  badge,
  onClose,
  children,
}: {
  name: string
  category?: string
  photoUrl: string | null
  badge?: string
  onClose: () => void
  children: ReactNode
}) {
  const dialog = useRef<HTMLDialogElement>(null)
  const title = useId()

  useEffect(() => {
    const box = dialog.current
    if (box && !box.open) box.showModal()
  }, [])

  return (
    <dialog
      ref={dialog}
      className="food-dialog"
      aria-labelledby={title}
      onClose={onClose}
      // A click on the dark area around the card closes it.
      onClick={(event) => {
        if (event.target === dialog.current) dialog.current?.close()
      }}
    >
      <div className="food-dialog-photo">
        <FoodPhoto url={photoUrl} name={name} eager />
        {badge && <span className="food-badge">{badge}</span>}
        <button type="button" className="food-dialog-close" onClick={() => dialog.current?.close()} aria-label="Close">
          <Icon name="close" className="toast-icon" />
        </button>
      </div>
      <div className="food-dialog-body">
        {category && <p className="food-category">{category}</p>}
        <h2 id={title}>{name}</h2>
        <ul className="food-varieties">{children}</ul>
        <button type="button" className="secondary food-dialog-done" onClick={() => dialog.current?.close()}>
          Done
        </button>
      </div>
    </dialog>
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
