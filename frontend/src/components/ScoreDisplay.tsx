import type { ReviewResponse } from '../types'

interface Props {
  result: ReviewResponse | null
}

export function ScoreDisplay({ result }: Props) {
  if (!result) return null

  return (
    <div className="card">
      <div className="score-header">
        <span className="score-label">Score</span>
        <span className={`score-value ${result.score === null ? 'null' : ''}`}>
          {result.score ?? '—'}
        </span>
      </div>
      <div className="divider" />
      <p className="feedback">{result.feedback}</p>
    </div>
  )
}
