import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router'
import { send, type Me } from '../api.ts'
import { Field, NewPasswordFields, Problem } from '../forms.tsx'
import { useValues } from '../useValues.ts'
import { useMe } from '../me.ts'
import { AlreadyLoggedIn } from './AlreadyLoggedIn.tsx'
import { PageHeading } from '../PageHeading.tsx'

// Choosing a password with a setup code from the counter (R1) or a coordinator (R3).
// The same page resets a forgotten password: it's just a new code.

export function StudentSetUp() {
  return <SetUp who="student" />
}

export function StaffSetUp() {
  return <SetUp who="staff" />
}

function SetUp({ who }: { who: 'student' | 'staff' }) {
  const { me, loggedIn } = useMe()
  const navigate = useNavigate()
  const { values, set } = useValues({ name: '', code: '', password: '', again: '' })
  const [problem, setProblem] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [sending, setSending] = useState(false)
  const student = who === 'student'

  if (me.state === 'ready' && me.me !== null) {
    return <AlreadyLoggedIn me={me.me} />
  }

  async function setUp(event: FormEvent) {
    event.preventDefault()
    // Checked here, because the server only ever sees one copy.
    if (values.password !== values.again) {
      setProblem('Please fix the boxes marked in red.')
      setFields({ again: "The two passwords aren't the same." })
      return
    }
    setSending(true)
    const answer = await send<Me>(student ? '/api/student/setup' : '/api/staff/setup', {
      ...(student ? { id_number: values.name } : { username: values.name }),
      setup_code: values.code,
      new_password: values.password,
    })
    setSending(false)
    if (!answer.ok) {
      setProblem(answer.message)
      setFields(answer.fields)
      return
    }
    loggedIn(answer.data)
    navigate(student ? '/book' : '/counter')
  }

  return (
    <div className="narrow">
      <PageHeading>{student ? 'Set up your account' : 'Choose your staff password'}</PageHeading>
      <p className="lead">
        {student
          ? 'Use the setup code you got at the food bank counter. You can do this right there, or later at home.'
          : 'Use the setup code a coordinator gave you.'}
      </p>
      <form onSubmit={setUp} noValidate>
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
            hint="The one a coordinator gave you."
            autoComplete="username"
            autoCapitalize="none"
            value={values.name}
            onChange={set('name')}
            error={fields.username}
            required
          />
        )}
        <Field
          label="Setup code"
          hint="8 letters and numbers, like K7QM-4TXP."
          autoComplete="one-time-code"
          autoCapitalize="characters"
          spellCheck={false}
          className="code-input"
          value={values.code}
          onChange={set('code')}
          error={fields.setup_code}
          required
        />
        <NewPasswordFields
          password={values.password}
          again={values.again}
          onPassword={set('password')}
          onAgain={set('again')}
          error={fields.new_password}
          againError={fields.again}
        />
        <button type="submit" disabled={sending}>
          {sending ? 'Saving...' : 'Save my password and log in'}
        </button>
      </form>
      <div className="after-form">
        <p>
          Already chosen a password? <Link to={student ? '/login' : '/staff/login'}>Log in</Link>.
        </p>
        <p>
          {student
            ? 'Code not working, or run out? Ask at the counter for a new one.'
            : 'Code not working, or run out? Ask a coordinator for a new one.'}
        </p>
      </div>
    </div>
  )
}
