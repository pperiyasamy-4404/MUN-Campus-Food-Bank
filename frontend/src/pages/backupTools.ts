// Which backups (substitutes) can replace anything, and which only stand in for
// the student's own pick (14 Nov, idea 2 on substitutes-redesign.html).
//
// The packing rule (refill() in backend/app/services/packing.py) skips a substitute
// that would give the student more of an item than max_per_item. So with the sample
// limit of 1: Bran flakes chosen, Corn flakes as a backup. If the oil runs out, Corn
// flakes is skipped (a second cereal). It's used only if the Bran flakes runs out.
// This file only says that out loud; the rule itself stays on the server.

export type BackupLine = { variety: { id: number; name: string }; itemKey: string }

/**
 * The chosen varieties this backup can only replace, by name. Empty if it can
 * replace anything, because the student hasn't got as many of its item as they're allowed.
 */
export function onlyReplaces(
  backup: BackupLine,
  lines: BackupLine[],
  chosen: Record<number, number>,
  maxPerItem: number,
): string[] {
  const sameItem = lines.filter((line) => line.itemKey === backup.itemKey && (chosen[line.variety.id] ?? 0) > 0)
  const howMany = sameItem.reduce((sum, line) => sum + chosen[line.variety.id], 0)
  return howMany >= maxPerItem ? sameItem.map((line) => line.variety.name) : []
}

/** "only if your Bran flakes runs out", or with two: "only if your Bran flakes or Corn flakes runs out". */
export function onlyIfSaying(names: string[]): string {
  return `only if your ${names.join(' or ')} runs out`
}
