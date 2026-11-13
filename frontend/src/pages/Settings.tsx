import { useState, type FormEvent, type ReactNode } from 'react'
import { send, type SettingsPage, type SettingsValues } from '../api.ts'
import { Field, Problem } from '../forms.tsx'
import { useMe } from '../me.ts'
import { showDate, showDayAndClock } from '../time.ts'
import { CoordinatorNav } from './CoordinatorParts.tsx'
import { useStaffData, WEEKDAYS } from './coordinatorTools.ts'
import { PageHeading } from '../PageHeading.tsx'
import { Loading } from '../ui/Loading.tsx'

// The food bank's numbers and weekly pickup hours (R3). Some are used straight
// away. The ones that make pickup days are copied onto each day when it's
// made, a week ahead, so days already made keep their times.

export function Settings() {
  const { forget } = useMe()
  const load = useStaffData<SettingsPage>('/api/settings', 0, forget)

  if (load.state === 'loading') return <Loading shape="page" />
  if (load.state === 'failed') return <p className="problem">Could not get the settings. Is the server running?</p>

  return (
    <div>
      <CoordinatorNav />
      <PageHeading>Settings</PageHeading>
      <SettingsForm page={load.data} onLoggedOut={forget} />
    </div>
  )
}

// Every box holds text while it's being typed. The server reads "28" as 28.
type Hours = { on: boolean; starts_at: string; ends_at: string }
type Form = Record<Exclude<keyof SettingsValues, 'pickup_hours' | 'no_shows_count'>, string> & {
  no_shows_count: boolean
  hours: Hours[] // one per weekday, Monday first
}

function startingForm(values: SettingsValues): Form {
  const { pickup_hours, no_shows_count, ...rest } = values
  const text = Object.fromEntries(Object.entries(rest).map(([name, value]) => [name, String(value)]))
  return {
    ...(text as Omit<Form, 'hours' | 'no_shows_count'>),
    no_shows_count,
    hours: WEEKDAYS.map((_, index) => {
      const day = pickup_hours.find((hours) => hours.weekday === index + 1)
      return day ? { on: true, starts_at: day.starts_at, ends_at: day.ends_at } : { on: false, starts_at: '', ends_at: '' }
    }),
  }
}

function SettingsForm({ page: first, onLoggedOut }: { page: SettingsPage; onLoggedOut: () => void }) {
  // What the server has saved. After Save, its answer replaces it.
  const [page, setPage] = useState(first)
  const [form, setForm] = useState<Form>(() => startingForm(first.settings))
  const [problem, setProblem] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [sending, setSending] = useState(false)
  const [saved, setSaved] = useState(false)

  const set = (name: keyof Omit<Form, 'hours' | 'no_shows_count'>) => (value: string) =>
    setForm((old) => ({ ...old, [name]: value }))
  const setHours = (index: number, change: Partial<Hours>) =>
    setForm((old) => ({ ...old, hours: old.hours.map((day, n) => (n === index ? { ...day, ...change } : day)) }))

  // The weekdays sent, in order, so an error at pickup_hours.1 can be put next to its day.
  const sentDays = form.hours.flatMap((day, index) => (day.on ? [index] : []))
  function hoursError(index: number): string | undefined {
    const at = sentDays.indexOf(index)
    if (at < 0) return undefined
    return fields[`pickup_hours.${at}.starts_at`] ?? fields[`pickup_hours.${at}.ends_at`]
  }

  async function save(event: FormEvent) {
    event.preventDefault()
    setProblem(null)
    setFields({})
    setSaved(false)
    const { hours, ...values } = form
    setSending(true)
    const answer = await send<SettingsPage>(
      '/api/settings',
      {
        ...values,
        pickup_hours: sentDays.map((index) => ({
          weekday: index + 1,
          starts_at: hours[index].starts_at,
          ends_at: hours[index].ends_at,
        })),
      },
      'PUT',
    )
    setSending(false)
    if (answer.ok) {
      setPage(answer.data)
      setForm(startingForm(answer.data.settings))
      return setSaved(true)
    }
    if (answer.status === 401) return onLoggedOut()
    setFields(answer.fields)
    setProblem(answer.message)
  }

  const number = (name: keyof Omit<Form, 'hours' | 'no_shows_count'>, label: string, hint?: string) => (
    <Field
      label={label}
      hint={hint}
      type="number"
      inputMode="numeric"
      value={form[name]}
      onChange={set(name)}
      error={fields[name]}
      required
    />
  )
  const clock = (name: keyof Omit<Form, 'hours' | 'no_shows_count'>, label: string, hint?: string) => (
    <Field label={label} hint={hint} type="time" value={form[name]} onChange={set(name)} error={fields[name]} required />
  )

  return (
    <form onSubmit={save}>
      <p className="lead">
        Times are St. John's time. Every change is logged with your name.
        {page.changed_at && page.changed_by && (
          <> Last changed by {page.changed_by} on {showDayAndClock(page.changed_at)}</>
        )}
      </p>
      {saved && (
        <div className="done-box" role="status">
          Saved. New pickup days will use these.
          {page.capacity_changed_on && page.capacity_changed_on.length > 0 && (
            <> Students per slot also changed on {page.capacity_changed_on.map(showDate).join('; ')}.</>
          )}
        </div>
      )}

      <Group
        title="For new pickup days"
        about={
          <>
            Copied onto each pickup day when it's made, {page.days_ahead} days ahead. Days already made keep their
            times
            {page.days_made.length > 0 && <>: {page.days_made.map(showDate).join('; ')}</>}. To change one of those,
            move its booking times or close it on the Pickup days page. Students per slot is different: it also
            changes on those days, until their booking opens.
          </>
        }
      >
        <fieldset className="hours">
          <legend>Pickup days and hours</legend>
          {WEEKDAYS.map((name, index) => {
            const day = form.hours[index]
            const error = hoursError(index)
            return (
              <div className={error ? 'hours-row field-wrong' : 'hours-row'} key={name}>
                <label className="check">
                  <input type="checkbox" checked={day.on} onChange={(event) => setHours(index, { on: event.target.checked })} />
                  {name}
                </label>
                {day.on && (
                  <>
                    <label>
                      <span className="visually-hidden">{name} pickup starts</span>
                      <input
                        type="time"
                        value={day.starts_at}
                        onChange={(event) => setHours(index, { starts_at: event.target.value })}
                        required
                      />
                    </label>
                    <span>to</span>
                    <label>
                      <span className="visually-hidden">{name} pickup ends</span>
                      <input
                        type="time"
                        value={day.ends_at}
                        onChange={(event) => setHours(index, { ends_at: event.target.value })}
                        required
                      />
                    </label>
                  </>
                )}
                {error && <p className="field-error">{error}</p>}
              </div>
            )
          })}
        </fieldset>
        <div className="settings-grid">
          {number('booking_opens_days_before', 'Booking opens, days before', '1 is the day before. 0 is the same day.')}
          {clock('booking_opens_time', 'Booking opens at')}
          {clock('booking_closes_time', 'Booking closes at', 'On the pickup day. Packing starts then.')}
          {clock('no_show_time', 'No-shows at', 'After pickup ends. Unpicked bags become no-shows.')}
          {number('slot_minutes', 'Slot length, minutes')}
          {number('slot_capacity', 'Students per slot', "Also on days already made, until their booking opens.")}
        </div>
      </Group>

      <Group title="Used straight away" about="These apply to the next booking, pickup or login.">
        <div className="settings-grid">
          {number('pickup_gap_days', 'Pickup gap, days', 'Days between one pickup and the next.')}
          {number('hold_minutes', 'Time to choose food, minutes', 'How long a slot is held while a student chooses.')}
          {number('item_limit', 'Things per booking')}
          {number('max_per_item', 'Most of one item', 'Counting all its kinds together.')}
          {number('substitute_limit', 'Substitutes per booking')}
          {number('setup_code_days', 'Setup codes last, days')}
          {number('login_tries', 'Wrong password tries')}
          {number('login_window_minutes', '...in this many minutes')}
        </div>
        <label className="check">
          <input
            type="checkbox"
            checked={form.no_shows_count}
            onChange={(event) => setForm((old) => ({ ...old, no_shows_count: event.target.checked }))}
          />
          A no-show counts as a pickup for the pickup gap
        </label>
      </Group>

      <Group
        title="Privacy"
        about="Booking details are deleted after this many days, once their totals are saved. A shorter time deletes more at the next jobs run."
      >
        <div className="settings-grid">
          {number('retention_days', 'Keep booking details, days', 'At least the pickup gap.')}
        </div>
      </Group>

      <Problem message={problem} />
      <button type="submit" disabled={sending} aria-busy={sending}>
        {sending ? 'Saving...' : 'Save the settings'}
      </button>
    </form>
  )
}

function Group({ title, about, children }: { title: string; about: ReactNode; children: ReactNode }) {
  return (
    <section className="card">
      <h2 className="in-card">{title}</h2>
      <p className="muted">{about}</p>
      {children}
    </section>
  )
}
