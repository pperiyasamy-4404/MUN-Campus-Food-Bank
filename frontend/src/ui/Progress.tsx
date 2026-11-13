/** A bar that fills up, like "8 of 13 in the bag" (13 Nov). The words say it too. */
export function Progress({ done, total, words }: { done: number; total: number; words: string }) {
  const share = total <= 0 ? 0 : Math.min(1, Math.max(0, done / total))
  return (
    <div className="progress">
      <div
        className="progress-track"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={total}
        aria-valuenow={done}
        aria-label={words}
      >
        <div className="progress-fill" style={{ width: `${share * 100}%` }} />
      </div>
      <p className="progress-words">{words}</p>
    </div>
  )
}
