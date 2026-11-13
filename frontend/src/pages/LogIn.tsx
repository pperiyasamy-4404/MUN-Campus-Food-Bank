import { useState, type FormEvent } from 'react'
import { Link, NavLink, useNavigate } from 'react-router'
import { send, type Me } from '../api.ts'
import { Field, Problem } from '../forms.tsx'
import { useValues } from '../useValues.ts'
import { useMe } from '../me.ts'
import { AlreadyLoggedIn } from './AlreadyLoggedIn.tsx'
import { PageHeading } from '../PageHeading.tsx'
import { WelcomeSplash } from '../ui/WelcomeSplash.tsx'
import logoFull from '../assets/logo-full.png'

// Logging in, for students (ID number) and for staff (username).

export function StudentLogIn() {
  return <LogIn who="student" />
}

export function StaffLogIn() {
  return <LogIn who="staff" />
}

function LogIn({ who }: { who: 'student' | 'staff' }) {
  const { me, loggedIn } = useMe()
  const navigate = useNavigate()
  const { values, set } = useValues({ name: '', password: '' })
  const [problem, setProblem] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [sending, setSending] = useState(false)
  // After a good password: the welcome screen, then the person's page (13 Nov).
  const [welcome, setWelcome] = useState<{ words: string; sub: string; to: string } | null>(null)
  const student = who === 'student'

  // Before the "already logged in" check: by now they are logged in, and the welcome comes first.
  if (welcome !== null) {
    return <WelcomeSplash words={welcome.words} sub={welcome.sub} onDone={() => navigate(welcome.to)} />
  }
  if (me.state === 'ready' && me.me !== null) {
    return <AlreadyLoggedIn me={me.me} />
  }

  async function logIn(event: FormEvent) {
    event.preventDefault()
    setSending(true)
    const answer = await send<Me>(
      student ? '/api/student/login' : '/api/staff/login',
      student
        ? { id_number: values.name, password: values.password }
        : { username: values.name, password: values.password },
    )
    setSending(false)
    if (!answer.ok) {
      setProblem(answer.message)
      setFields(answer.fields)
      return
    }
    const account = answer.data
    setWelcome(
      account.kind === 'staff'
        ? {
            words: `Welcome back, ${account.username}`,
            sub: account.role === 'coordinator' ? 'Opening the counter. The Coordinator tab is up top.' : 'Opening the counter',
            to: '/counter',
          }
        : { words: 'Welcome back', sub: "Let's get your pickup booked", to: '/book' },
    )
    loggedIn(account)
  }

  return (
    <div className="narrow">
      <img className="logo-full form-logo" src={logoFull} alt="MUN Campus Food Bank" width="640" height="409" />
      <PageHeading>Log in</PageHeading>
      {/* Two tabs, Student and Staff (decided 12 Nov): staff find their way in from
          the same page, without a link in the top bar or at the bottom. They're
          links, so /staff/login can still be bookmarked. */}
      <nav aria-label="Who is logging in" className="login-switch">
        <NavLink to="/login" end>
          Student
        </NavLink>
        <NavLink to="/staff/login" end>
          Staff
        </NavLink>
      </nav>
      <form onSubmit={logIn} noValidate>
        <Problem message={problem} />
        {student ? (
          <Field
            label="ID number"
            hint="The 9 digits on your MUN card."
            inputMode="numeric"
            autoComplete="username"
            value={values.name}
            onChange={set('name')}
            error={fields.id_number}
            required
          />
        ) : (
          <Field
            label="Username"
            autoComplete="username"
            autoCapitalize="none"
            value={values.name}
            onChange={set('name')}
            error={fields.username}
            required
          />
        )}
        <Field
          label="Password"
          type="password"
          autoComplete="current-password"
          value={values.password}
          onChange={set('password')}
          error={fields.password}
          required
        />
        <button type="submit" disabled={sending} aria-busy={sending}>
          {sending ? 'Checking...' : 'Log in'}
        </button>
      </form>
      {student ? (
        <div className="after-form">
          <p>
            First time? Get a setup code at the food bank counter, then{' '}
            <Link to="/setup">set up your account</Link>.
          </p>
          <p>Forgot your password? Ask at the counter for a new setup code.</p>
        </div>
      ) : (
        <div className="after-form">
          <p>
            Got a setup code from a coordinator? <Link to="/staff/setup">Choose your password</Link>.
          </p>
          <p>Forgot your password? Ask a coordinator for a new setup code.</p>
        </div>
      )}
    </div>
  )
}
