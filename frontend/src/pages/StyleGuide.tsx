import { useState } from 'react'
import { Field } from '../forms.tsx'
import { PageHeading } from '../PageHeading.tsx'

// Every colour token, button, badge, alert and form state in one place, to check
// the MUN theme (decided 12 Nov). Only in development (npm run dev): App.tsx
// leaves the route out of the real build.

const BRAND = [
  '--color-claret',
  '--color-black',
  '--color-grey-10',
  '--color-grey-7',
  '--color-warm-grey-8',
  '--color-warm-grey-6',
  '--color-white',
  '--color-surface',
  '--color-border-subtle',
  '--color-green',
  '--color-gold',
  '--color-green-25',
  '--color-gold-25',
]

const SEMANTIC = [
  '--bg-page',
  '--bg-surface',
  '--text-primary',
  '--text-secondary',
  '--text-on-claret',
  '--text-link',
  '--action-primary-bg',
  '--action-primary-text',
  '--action-primary-hover-bg',
  '--border-input',
  '--border-subtle',
  '--focus-ring',
  '--status-available-bg',
  '--status-available-edge',
  '--status-limited-bg',
  '--status-limited-edge',
  '--status-on-color-text',
  '--status-full-bg',
  '--status-full-text',
  '--status-full-edge',
  '--alert-success-accent',
  '--alert-warning-accent',
  '--alert-error-accent',
  '--selected-border',
  '--page-title',
  '--sticky-note-bg',
  '--sticky-note-shadow',
  '--header-bg',
  '--header-text',
  '--tab-active-bar',
  '--strip-bg',
  '--strip-text',
  '--focus-ring-on-dark',
  '--section-title',
  '--accent-line',
]

function Swatches({ title, names }: { title: string; names: string[] }) {
  return (
    <section>
      <h2>{title}</h2>
      <ul className="sg-swatches">
        {names.map((name) => (
          <li key={name}>
            {/* A token, never a colour value. */}
            <span className="sg-swatch" style={{ background: `var(${name})` }} />
            <code>{name}</code>
          </li>
        ))}
      </ul>
    </section>
  )
}

export function StyleGuide() {
  const [name, setName] = useState('Quick oats')
  const [card, setCard] = useState('12')

  return (
    <div>
      <PageHeading>Style guide</PageHeading>
      <p className="lead">Only in development. Every colour comes from styles/theme.css.</p>

      <Swatches title="Brand tokens (MUN)" names={BRAND} />
      <Swatches title="Semantic tokens (what the CSS uses)" names={SEMANTIC} />

      <section>
        <h2>Buttons</h2>
        <p className="muted">Hover and focus are shown with helper classes; try the real ones with a mouse and the Tab key.</p>
        <p className="actions">
          <button type="button">Primary</button>
          <button type="button" className="sg-hover">
            Primary, hover
          </button>
          <button type="button" disabled>
            Primary, disabled
          </button>
          <button type="button" className="sg-focus">
            Primary, focus
          </button>
        </p>
        <p className="actions">
          <button type="button" className="secondary">
            Secondary
          </button>
          <button type="button" className="secondary sg-hover">
            Secondary, hover
          </button>
          <button type="button" className="secondary" disabled>
            Secondary, disabled
          </button>
          <button type="button" className="secondary sg-focus">
            Secondary, focus
          </button>
        </p>
        <p className="actions">
          <button type="button" className="link-button">
            A button that reads like a link
          </button>
          <a href="#links">A link</a>
          <button type="button" className="level-button level-button-on" aria-pressed>
            Chosen
          </button>
          <button type="button" className="chosen-button">
            ✓ Added
          </button>
        </p>
      </section>

      <section>
        <h2 id="links">Badges</h2>
        <p className="actions">
          <span className="slot-places">Free</span>
          <span className="stock-few">Few left</span>
          <span className="stock-out">Taken</span>
          <span className="stock-left">6 left</span>
          <span className="tag">Vegetarian</span>
        </p>
        <p className="actions">
          <span className="status status-open">Booking open</span>
          <span className="status status-not_open_yet">Booking not open yet</span>
          <span className="status status-booking_over">Booking over</span>
        </p>
      </section>

      <section>
        <h2>Alerts</h2>
        <div className="done-box" role="status">
          Monday, November 16 is closed. 3 bookings were cancelled.
        </div>
        <p className="notice">Booking for Monday, November 16 closes at 12:00 p.m.</p>
        <p className="problem" role="alert">
          Sorry, Chunk chicken has just run out. Choose something else.
        </p>
      </section>

      <section className="narrow">
        <h2>A form field</h2>
        <Field label="Variety name" hint="Like quick oats or steel-cut oats." value={name} onChange={setName} />
        <Field
          label="MUN card number"
          hint="From the student's card."
          value={card}
          onChange={setCard}
          error="Enter the 9 digits on your MUN card."
        />
      </section>
    </div>
  )
}
