import { useEffect, useState } from 'react'

// Time-based narrative. These are not real backend phases — they are an honest,
// deterministic function of elapsed time so the user always feels the app moving.
const STAGES = [
  'Reading the file…',
  'Extracting fields…',
  'AI is scoring & summarizing…',
  'Almost done…',
]

const STAGE_MS = 6000

export function formatElapsed(ms: number): string {
  const total = Math.max(0, Math.floor(ms / 1000))
  const m = Math.floor(total / 60)
  const s = total % 60
  return `${m}:${s.toString().padStart(2, '0')}`
}

export function ProcessingBar({ startedAt, label }: { startedAt: number; label: string }) {
  const [now, setNow] = useState(() => Date.now())

  useEffect(() => {
    const id = setInterval(() => setNow(Date.now()), 1000)
    return () => clearInterval(id)
  }, [])

  const elapsed = now - startedAt
  const stage = STAGES[Math.min(STAGES.length - 1, Math.floor(elapsed / STAGE_MS))]

  return (
    <div className="proc-bar" role="status" aria-live="polite">
      <div className="proc-bar-row">
        <span className="spinner" aria-hidden="true" />
        <div className="proc-text">
          <span className="proc-title">{label}</span>
          <span className="proc-stage">{stage}</span>
        </div>
        <span className="proc-elapsed" title="Elapsed time">{formatElapsed(elapsed)}</span>
      </div>
      <div className="proc-track"><span className="proc-fill" /></div>
    </div>
  )
}
