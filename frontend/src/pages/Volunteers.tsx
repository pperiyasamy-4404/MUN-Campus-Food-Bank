import { useEffect, useState, type FormEvent } from 'react'
import { send, type IssuedCode, type Volunteer } from '../api.ts'
import { Field, Problem, SetupCodeBox } from '../forms.tsx'
import { useValues } from '../useValues.ts'
import { useMe } from '../me.ts'
import { showDay, showDayAndClock } from '../time.ts'
import { CoordinatorNav } from './CoordinatorParts.tsx'
import { PageHeading } from '../PageHeading.tsx'

// The Staff page (R3): every volunteer and coordinator. A coordinator adds a
// volunteer, gives a new setup code, makes someone a coordinator or a volunteer
// (several coordinators since 11 Nov), or switches an account off when someone
// leaves. Their own row has no buttons: another coordinator changes it.

// Why a setup code was given: the words around it change.
type Why = 'added' | 'new code' | 'switched back on'

type List = { state: 'loading' } | { state: 'failed' } | { state: 'ready'; volunteers: Volunteer[] }

export function Volunteers() {
  const { forget } = useMe()
  const [list, setList] = useState<List>({ state: 'loading' })
  const [problem, setProblem] = useState<string | null>(null)
  // The code just given, who it's for, and why. Shown once, until Done.
  const [issued, setIssued] = useState<{ username: string; code: IssuedCode; why: Why } | null>(null)

  // Each change adds 1, which asks for the list again.
  const [version, setVersion] = useState(0)
  const refresh = () => setVersion((old) => old + 1)

  useEffect(() => {
    // If the page goes away before the answer comes, drop the answer.
    let stillWanted = true
    fetch('/api/volunteers')
      .then(async (response) => {
        if (response.status === 401) return stillWanted && forget()
        if (!response.ok) throw new Error(`The server answered ${response.status}`)
        const volunteers = (await response.json()) as Volunteer[]
        if (stillWanted) setList({ state: 'ready', volunteers })
      })
      .catch(() => {
        if (stillWanted) setList({ state: 'failed' })
      })
    return () => {
      stillWanted = false
    }
  }, [version, forget])

  async function newCode(volunteer: Volunteer) {
    const answer = await send<IssuedCode>(`/api/volunteers/${volunteer.id}/setup-code`)
    if (!answer.ok) {
      if (answer.status === 401) forget()
      return setProblem(answer.message)
    }
    setProblem(null)
    setIssued({ username: volunteer.username, code: answer.data, why: 'new code' })
    refresh()
  }

  async function switchOff(volunteer: Volunteer) {
    const sure = window.confirm(
      `Switch off ${volunteer.username}? They'll be logged out straight away, and can't log in until you switch them back on.`,
    )
    if (!sure) return
    const answer = await send<Volunteer>(`/api/volunteers/${volunteer.id}/switch-off`)
    if (!answer.ok) {
      if (answer.status === 401) forget()
      return setProblem(answer.message)
    }
    setProblem(null)
    refresh()
  }

  async function changeRole(volunteer: Volunteer, to: 'coordinator' | 'volunteer') {
    const sure = window.confirm(
      to === 'coordinator'
        ? `Make ${volunteer.username} a coordinator? They'll be able to close days, change settings and manage staff, ` +
            'with the password they have now.'
        : `Make ${volunteer.username} a volunteer? They'll lose the coordinator pages straight away.`,
    )
    if (!sure) return
    const answer = await send<Volunteer>(`/api/volunteers/${volunteer.id}/make-${to}`)
    if (!answer.ok) {
      if (answer.status === 401) forget()
      return setProblem(answer.message)
    }
    setProblem(null)
    refresh()
  }

  async function switchOn(volunteer: Volunteer) {
    const answer = await send<{ volunteer: Volunteer; code: IssuedCode }>(`/api/volunteers/${volunteer.id}/switch-on`)
    if (!answer.ok) {
      if (answer.status === 401) forget()
      return setProblem(answer.message)
    }
    setProblem(null)
    setIssued({ username: volunteer.username, code: answer.data.code, why: 'switched back on' })
    refresh()
  }

  return (
    <div>
      <CoordinatorNav />
      <PageHeading>Staff</PageHeading>
      <p className="lead">
        Each volunteer and coordinator has their own login, so the log can say who did what. They choose their own
        password with a setup code. You never see it. To add a coordinator, add them as a volunteer, then make them a
        coordinator.
      </p>

      {issued && (
        <SetupCodeBox
          title={
            issued.why === 'switched back on'
              ? `${issued.username} is switched back on`
              : `Setup code for ${issued.username}`
          }
          code={issued.code}
          onDone={() => setIssued(null)}
        >
          <p>
            Give it to {issued.username} with their username. They choose a password on the "Staff log in"
            page, under "Choose your password".
            {issued.why === 'new code' && ' Their old password keeps working until they use this code.'}
            {issued.why === 'switched back on' && ' Their old password no longer works.'}
          </p>
        </SetupCodeBox>
      )}

      <AddVolunteer
        onAdded={(username, code) => {
          setIssued({ username, code, why: 'added' })
          refresh()
        }}
        onLoggedOut={forget}
      />

      <h2>Everyone</h2>
      <Problem message={problem} />
      {list.state === 'loading' && <p className="muted">Asking the server...</p>}
      {list.state === 'failed' && <p className="problem">Could not get the staff list. Is the server running?</p>}
      {list.state === 'ready' && (
        <table className="people">
          <thead>
            <tr>
              <th scope="col">Username and role</th>
              <th scope="col">Account</th>
              <th scope="col">
                <span className="visually-hidden">Changes</span>
              </th>
            </tr>
          </thead>
          <tbody>
            {list.volunteers.map((volunteer) => (
              <tr key={volunteer.id} className={volunteer.switched_off_at ? 'switched-off' : undefined}>
                <th scope="row">
                  {volunteer.username}
                  {/* Under the name, not in its own column, so the table still fits a phone. */}
                  <span className="role-line">
                    {volunteer.role === 'coordinator' ? 'Coordinator' : 'Volunteer'}
                    {volunteer.you && ' (you)'}
                  </span>
                </th>
                <td>{accountState(volunteer)}</td>
                <td>
                  {volunteer.you ? (
                    <span className="muted">That's you</span>
                  ) : volunteer.switched_off_at ? (
                    <div className="row-actions">
                      <button type="button" className="secondary" onClick={() => switchOn(volunteer)}>
                        Switch back on
                      </button>
                    </div>
                  ) : (
                    <div className="row-actions">
                      <button type="button" className="secondary" onClick={() => newCode(volunteer)}>
                        New setup code
                      </button>
                      <button
                        type="button"
                        className="secondary"
                        onClick={() => changeRole(volunteer, volunteer.role === 'coordinator' ? 'volunteer' : 'coordinator')}
                      >
                        {volunteer.role === 'coordinator' ? 'Make volunteer' : 'Make coordinator'}
                      </button>
                      <button type="button" className="danger" onClick={() => switchOff(volunteer)}>
                        Switch off
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  )
}

function accountState(volunteer: Volunteer): string {
  if (volunteer.switched_off_at) return `Switched off on ${showDay(volunteer.switched_off_at)}`
  if (volunteer.password_set) return 'Ready'
  if (volunteer.setup_code_expires_at) {
    return `Waiting for them to choose a password. Their code runs out ${showDayAndClock(volunteer.setup_code_expires_at)}`
  }
  return 'No password yet, and their code has run out. Give them a new one.'
}

function AddVolunteer({
  onAdded,
  onLoggedOut,
}: {
  onAdded: (username: string, code: IssuedCode) => void
  onLoggedOut: () => void
}) {
  const { values, set, clear } = useValues({ username: '' })
  const [problem, setProblem] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [sending, setSending] = useState(false)

  async function add(event: FormEvent) {
    event.preventDefault()
    setSending(true)
    const answer = await send<{ volunteer: Volunteer; code: IssuedCode }>('/api/volunteers', {
      username: values.username,
    })
    setSending(false)
    if (!answer.ok) {
      if (answer.status === 401) onLoggedOut()
      setProblem(answer.message)
      setFields(answer.fields)
      return
    }
    setProblem(null)
    setFields({})
    clear()
    onAdded(answer.data.volunteer.username, answer.data.code)
  }

  return (
    <form className="card add-form" onSubmit={add} noValidate autoComplete="off">
      <h2>Add a volunteer</h2>
      <Problem message={problem} />
      <Field
        label="Username"
        hint="A first name or a nickname, like Sam. Add an initial if two people share a name."
        value={values.username}
        onChange={set('username')}
        error={fields.username}
        required
      />
      <button type="submit" disabled={sending}>
        {sending ? 'Adding...' : 'Add and give a setup code'}
      </button>
    </form>
  )
}
