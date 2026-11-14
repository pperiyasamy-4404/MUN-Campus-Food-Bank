import { useState, type FormEvent } from 'react'
import { send, type IssuedCode } from '../api.ts'
import {
  Field,
  OldSystemPickup,
  Problem,
  SetupCodeBox,
} from '../forms.tsx'
import { NO_OLD_SYSTEM_ANSWER, oldSystemAnswer, oldSystemProblem, type OldSystem } from '../oldSystem.ts'
import { useValues } from '../useValues.ts'
import { useMe } from '../me.ts'
import { PageHeading } from '../PageHeading.tsx'
import { showDate, todayInNewfoundland } from '../time.ts'

// At the counter: the volunteer checks a student's MUN card and gives them a
// setup code (R1). A new card gets an account. A card that has one gets a new
// code, which is how a forgotten password is reset.
// While the food bank switches over, the volunteer also types the student's
// last pickup from the old records, so the 30 days count from it (decided 12 Nov).
// Its own tab since 13 Nov night (the user's wish): it's too important to be a
// small link under the counter, so it has a page of its own, as a card.

export function SetupCode() {
  const { forget } = useMe()
  const { values, set, clear } = useValues({ id_number: '', again: '' })
  const [oldSystem, setOldSystem] = useState<OldSystem>(NO_OLD_SYSTEM_ANSWER)
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
    const notAnswered = oldSystemProblem(oldSystem)
    if (notAnswered) {
      setProblem('Please fix the boxes marked in red.')
      setFields({ old_system_pickup_on: notAnswered })
      return
    }
    setSending(true)
    const answer = await send<IssuedCode>('/api/student-setup-codes', {
      id_number: values.id_number,
      ...oldSystemAnswer(oldSystem),
    })
    setSending(false)
    if (!answer.ok) {
      if (answer.status === 401) forget() // the 12 hours are over: back to the login page
      setProblem(answer.message)
      setFields(answer.fields)
      return
    }
    // The number isn't needed any more, so it leaves the screen straight away.
    clear()
    setOldSystem(NO_OLD_SYSTEM_ANSWER)
    setIssued(answer.data)
  }

  return (
    <div className="auth">
      <section className="auth-card auth-card-wide">
      <span className="auth-badge" aria-hidden="true">
        <KeyIcon />
      </span>
      <PageHeading>Give a setup code</PageHeading>
      <p className="auth-lead">For a student's first login, or when they forget their password.</p>
      {issued ? (
        <SetupCodeBox
          title={issued.new_account ? 'New account made' : 'New setup code for an existing account'}
          code={issued}
          onDone={() => setIssued(null)}
        >
          {!issued.new_account && (
            <p>Their old password keeps working until they use this code.</p>
          )}
          {issued.next_pickup_on && (
            <p className="notice">
              From their last pickup, they can't get food again until {showDate(issued.next_pickup_on)}. Tell them
              booking will wait until then.
            </p>
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
          <ol className="steps-strip">
            <li>Check their MUN card</li>
            <li>Type the number twice</li>
            <li>Read them the code</li>
          </ol>
          <p className="muted small-print">
            The number is only used to find or make their account, and is never shown again.
          </p>
          <form onSubmit={giveCode} noValidate autoComplete="off">
            <Problem message={problem} />
            <Field
              label="ID number on the MUN card"
              hint="Type it from the card itself. No card, no food: a student who lost it gets a new MUN card first."
              inputMode="numeric"
              value={values.id_number}
              onChange={set('id_number')}
              error={fields.id_number}
              required
            />
            <Field
              label="Re-enter ID number"
              inputMode="numeric"
              value={values.again}
              onChange={set('again')}
              error={fields.again}
              required
            />
            <OldSystemPickup
              answer={oldSystem}
              onChange={setOldSystem}
              error={fields.old_system_pickup_on}
              today={todayInNewfoundland()}
            />
            <button type="submit" className="auth-submit" disabled={sending} aria-busy={sending}>
              {sending ? 'Giving a code...' : 'Give a setup code'}
            </button>
          </form>
        </>
      )}
      </section>
    </div>
  )
}

/** A key, for the top of the page. The same drawing as the Setup code tab. */
function KeyIcon() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" focusable="false">
      <circle cx="7.5" cy="15.5" r="4.5" />
      <path d="m10.7 12.3 9.8-9.8M17 6l3 3M14.5 8.5l2 2" />
    </svg>
  )
}
