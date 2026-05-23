import type { ReviewResponse } from '../types'

interface Props {
  extractedText: string | null
  result: ReviewResponse | null
  extracting: boolean
}

export function ResultPanel({ extractedText, result, extracting }: Props) {
  if (extracting) {
    return (
      <div className="panel result-panel result-empty">
        <p className="muted-text">Extracting content…</p>
      </div>
    )
  }

  if (!extractedText) {
    return (
      <div className="panel result-panel result-empty">
        <p className="muted-text">Upload a resume to see its content here</p>
      </div>
    )
  }

  return (
    <div className="panel result-panel">
      {result && (
        <>
          <div className="score-header">
            <span className="score-label">Score</span>
            <span className={`score-value${result.score === null ? ' null' : ''}`}>
              {result.score ?? '—'}
            </span>
          </div>
          <p className="feedback">{result.feedback}</p>
          <div className="divider" />
        </>
      )}

      <p className="label">Extracted Content</p>
      <pre className="extracted-text">{extractedText}</pre>
    </div>
  )
}
