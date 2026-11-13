// The three stages of booking, so a student always knows where they are (13 Nov).

const STEPS = ['Pick a time', 'Choose your food', 'Booked']

export function BookingSteps({ current }: { current: 1 | 2 | 3 }) {
  return (
    <ol className="steps-bar" aria-label="Booking steps">
      {STEPS.map((step, index) => {
        const number = index + 1
        return (
          <li
            key={step}
            className={number < current ? 'done' : undefined}
            aria-current={number === current ? 'step' : undefined}
          >
            {step}
            {number < current && <span className="visually-hidden"> (done)</span>}
          </li>
        )
      })}
    </ol>
  )
}
