// Loading shapes (13 Nov): grey outlines of what's coming, gently pulsing,
// instead of "Asking the server...". The page keeps its shape, so nothing jumps
// when the real content arrives. Screen readers hear "Loading" once.

type Shape = 'page' | 'cards' | 'days' | 'rows' | 'line'

export function Loading({ shape = 'page', label = 'Loading' }: { shape?: Shape; label?: string }) {
  return (
    <div className="loading" role="status">
      <span className="visually-hidden">{label}...</span>
      <div aria-hidden="true">
        {shape === 'page' && (
          <>
            <span className="skeleton skeleton-title" />
            <span className="skeleton skeleton-line" style={{ width: '70%' }} />
            <span className="skeleton skeleton-row" />
            <span className="skeleton skeleton-row" />
            <span className="skeleton skeleton-row" />
          </>
        )}
        {shape === 'cards' && (
          <div className="skeleton-grid">
            {[0, 1, 2, 3, 4, 5, 6, 7].map((n) => (
              <div key={n} className="skeleton-cardbox">
                <span className="skeleton-photo" />
                <div className="skeleton-lines">
                  <span className="skeleton skeleton-strong skeleton-line" style={{ width: '35%' }} />
                  <span className="skeleton skeleton-strong skeleton-line" style={{ width: '65%', height: '1.2rem' }} />
                  <span className="skeleton skeleton-line" style={{ width: '80%' }} />
                  <span className="skeleton skeleton-line" style={{ width: '45%' }} />
                </div>
              </div>
            ))}
          </div>
        )}
        {shape === 'days' &&
          [0, 1].map((n) => (
            <div key={n} className="card">
              <span className="skeleton skeleton-line" style={{ width: '35%' }} />
              <span className="skeleton skeleton-line" style={{ width: '60%' }} />
              <div className="skeleton-slots">
                {[0, 1, 2, 3, 4, 5, 6, 7].map((slot) => (
                  <span key={slot} className="skeleton skeleton-slot" />
                ))}
              </div>
            </div>
          ))}
        {shape === 'rows' && (
          <>
            <span className="skeleton skeleton-title" />
            {[0, 1, 2, 3, 4].map((n) => (
              <span key={n} className="skeleton skeleton-row" />
            ))}
          </>
        )}
        {shape === 'line' && <span className="skeleton skeleton-line" style={{ width: '50%' }} />}
      </div>
    </div>
  )
}
