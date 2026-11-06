import { useState, type FormEvent } from 'react'
import { send, type IssuedCode } from '../api.ts'
import { Field, Problem, SetupCodeBox } from '../forms.tsx'
import { useValues } from '../useValues.ts'
import { useMe } from '../me.ts'

// At the counter: the volunteer checks a student's MUN card and gives them a
// setup code (R1). A new card gets an account. A card that has one gets a new
// code, which is how a forgotten password is reset.

export function Counter() {
  const { forget } = useMe()
  const { values, set, clear } = useValues({ id_number: '', again: '' })
  const [problem, setProblem] = useState<string | null>(null)
  const [fields, setFields] = useState<Record<string, string>>({})
  const [sending, setSending] = useState(false)
  const [issued, setIssued] = useState<IssuedCode | null>(null)

  async function giveCode(event: FormEvent) {
    event.preventDefault()
    setProblem(null)
    setFields({})
    // Typed twice: a typo would make an account for someone else's number, and
    // the student's code wouldn't work with their real one.
    if (values.id_number.replace(/[\s-]/g, '') !== values.again.replace(/[\s-]/g, '')) {
      setProblem('Please fix the boxes marked in red.')
      setFields({ again: "The two numbers aren't the same. Check the card again." })
      return
    }
    setSending(true)
    const answer = await send<IssuedCode>('/api/student-setup-codes', { id_number: values.id_number })
    setSending(false)
    if (!answer.ok) {
      if (answer.status === 401) forget() // the 12 hours are over: back to the login page
      setProblem(answer.message)
      setFields(answer.fields)
      return
    }
    // The number isn't needed any more, so it leaves the screen straight away.
    clear()
    setIssued(answer.data)
  }

  return (
    <div className="narrow">
      <h1>Give a setup code</h1>
      {issued ? (
        <SetupCodeBox
          title={issued.new_account ? 'New account made' : 'New setup code for an existing account'}
          code={issued}
          onDone={() => setIssued(null)}
        >
          {!issued.new_account && (
            <p>Their old password keeps working until they use this code.</p>
          )}
          <div className="tell">
            <p>
              <strong>Tell the student:</strong>
            </p>
            <ol>
              <li>On your own phone, open the food bank website and choose "Set up your account".</li>
              <li>Type your ID number and this code, then choose a password.</li>
              <li>Please don't use your MUN password.</li>
            </ol>
          </div>
        </SetupCodeBox>
      ) : (
        <>
          <p className="lead">
            Check the student's MUN card first. The number is only used to find or make their account, and is
            never shown again.
          </p>
          <form onSubmit={giveCode} noValidate autoComplete="off">
            <Problem message={problem} />
            <Field
              label="ID number on the MUN card"
              inputMode="numeric"
              value={values.id_number}
              onChange={set('id_number')}
              error={fields.id_number}
              required
            />
            <Field
              label="Type it again"
              inputMode="numeric"
              value={values.again}
              onChange={set('again')}
              error={fields.again}
              required
            />
            <button type="submit" disabled={sending}>
              {sending ? 'Giving a code...' : 'Give a setup code'}
            </button>
          </form>
        </>
      )}
    </div>
  )
}
