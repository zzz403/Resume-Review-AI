import type { Review } from '../types'

interface Props {
  items: Review[]
}

export function HistoryList({ items }: Props) {
  if (items.length === 0) {
    return <p className="muted-text">No reviews yet. Submit a resume to get started.</p>
  }

  return (
    <>
      <p className="history-title">Past Reviews</p>
      <ul className="history-list">
        {items.map((r) => (
          <li key={r.id} className="history-item">
            <span className="history-score">{r.score ?? '—'}</span>
            <span className="history-date">
              {new Date(r.created_at).toLocaleDateString('en-US', {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
              })}
            </span>
          </li>
        ))}
      </ul>
    </>
  )
}
