import { useId, useState, type InputHTMLAttributes, type ReactNode } from 'react'
import type { OldSystem } from './oldSystem.ts'
import { showDayAndClock } from './time.ts'

// Pieces every form uses: a labelled box with its own error, and the message
// at the top when the server says no.

type FieldProps = {
  label: string
  hint?: string
  error?: string
  value: string
  onChange: (value: string) => void
} & Omit<InputHTMLAttributes<HTMLInputElement>, 'value' | 'onChange'>

export function Field({ label, hint, error, value, onChange, ...input }: FieldProps) {
  const id = useId()
  return (
    <div className={error ? 'field field-wrong' : 'field'}>
      <label htmlFor={id}>{label}</label>
      {hint && (
        <p className="hint" id={`${id}-hint`}>
          {hint}
        </p>
      )}
      <input
        id={id}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={error ? true : undefined}
        aria-describedby={[hint && `${id}-hint`, error && `${id}-error`].filter(Boolean).join(' ') || undefined}
        {...input}
      />
      {error && (
        <p className="field-error" id={`${id}-error`}>
          {error}
        </p>
      )}
    </div>
  )
}

/** The student's last pickup in the old system: a date, or the "none" tick box (decided 12 Nov). */
export function OldSystemPickup({
  answer,
  onChange,
  error,
  today,
}: {
  answer: OldSystem
  onChange: (answer: OldSystem) => void
  error?: string
  today: string
}) {
  const id = useId()
  return (
    <fieldset className={error ? 'old-system field-wrong' : 'old-system'} aria-describedby={`${id}-hint`}>
      <legend>Last pickup in the old system</legend>
      <p className="hint" id={`${id}-hint`}>
        Look them up in the old records. Choose the date, or tick the box if they've never had food from the food bank.
      </p>
      <label htmlFor={`${id}-date`} className="old-system-date">
        Date
      </label>
      <input
        id={`${id}-date`}
        type="date"
        max={today}
        value={answer.on}
        disabled={answer.never}
        aria-invalid={error ? true : undefined}
        aria-describedby={error ? `${id}-error` : undefined}
        onChange={(event) => onChange({ on: event.target.value, never: false })}
      />
      <label className="check">
        <input
          type="checkbox"
          checked={answer.never}
          onChange={(event) => onChange({ on: '', never: event.target.checked })}
        />
        No pickup in the old system
      </label>
      {error && (
        <p className="field-error" id={`${id}-error`}>
          {error}
        </p>
      )}
    </fieldset>
  )
}

/** The server's "no", read out by screen readers as soon as it appears. */
export function Problem({ message }: { message: string | null }) {
  if (message === null) return null
  return (
    <p className="problem" role="alert">
      {message}
    </p>
  )
}

/** A new password, typed twice. A typo here would mean another trip to the counter. */
export function NewPasswordFields({
  password,
  again,
  onPassword,
  onAgain,
  error,
  againError,
}: {
  password: string
  again: string
  onPassword: (value: string) => void
  onAgain: (value: string) => void
  error?: string
  againError?: string
}) {
  const [show, setShow] = useState(false)
  return (
    <>
      <Field
        label="Choose a password"
        hint="At least 8 characters. Please don't use your MUN password."
        type={show ? 'text' : 'password'}
        autoComplete="new-password"
        value={password}
        onChange={onPassword}
        error={error}
        required
      />
      <Field
        label="Re-enter password"
        type={show ? 'text' : 'password'}
        autoComplete="new-password"
        value={again}
        onChange={onAgain}
        error={againError}
        required
      />
      <label className="check">
        <input type="checkbox" checked={show} onChange={(event) => setShow(event.target.checked)} />
        Show the password
      </label>
    </>
  )
}

/** A setup code, shown once, big enough to read out across the counter. */
export function SetupCodeBox({
  title,
  code,
  children,
  onDone,
}: {
  title: string
  code: { setup_code: string; expires_at: string }
  children?: ReactNode
  onDone: () => void
}) {
  return (
    <section className="code-box" aria-live="polite">
      <h2>{title}</h2>
      <p className="code">{code.setup_code}</p>
      <p>
        It works once, and runs out on <strong>{showDayAndClock(code.expires_at)}</strong>
      </p>
      {children}
      <p className="muted">This code is shown only now. Nobody can look it up later.</p>
      <button type="button" onClick={onDone}>
        Done, clear the screen
      </button>
    </section>
  )
}
