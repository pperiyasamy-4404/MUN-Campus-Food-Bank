/**
 * The student's last pickup in the food bank's old system (decided 12 Nov).
 * Required, so it can't be forgotten: a date from the old records, or "No pickup
 * in the old system". Example: food the old way on 12 November, so a code or a
 * walk-in on 19 November knows the 30 days run to 12 December.
 */
export type OldSystem = { on: string; never: boolean }

export const NO_OLD_SYSTEM_ANSWER: OldSystem = { on: '', never: false }

/** What the server wants. */
export function oldSystemAnswer(answer: OldSystem): { never_in_old_system: boolean; old_system_pickup_on: string | null } {
  return { never_in_old_system: answer.never, old_system_pickup_on: answer.never || answer.on === '' ? null : answer.on }
}

/** A problem to show before asking the server, or null. */
export function oldSystemProblem(answer: OldSystem): string | null {
  if (!answer.never && answer.on === '') {
    return 'Choose their last pickup in the old system, or tick "No pickup in the old system".'
  }
  return null
}
