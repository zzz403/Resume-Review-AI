import { useState, useEffect } from 'react'
import { ResumeInput } from './components/ResumeInput'
import { ScoreDisplay } from './components/ScoreDisplay'
import { HistoryList } from './components/HistoryList'
import { submitResume, getHistory } from './api'
import type { Review, ReviewResponse } from './types'

export default function App() {
  const [result, setResult] = useState<ReviewResponse | null>(null)
  const [history, setHistory] = useState<Review[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'review' | 'history'>('review')

  useEffect(() => {
    getHistory().then(setHistory).catch(() => {})
  }, [])

  async function handleSubmit(text: string) {
    setLoading(true)
    setError(null)
    try {
      const res = await submitResume(text)
      setResult(res)
      const updated = await getHistory()
      setHistory(updated)
    } catch {
      setError('Something went wrong. Is the backend running on port 8000?')
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="app">
      <header className="header">
        <h1 className="logo">
          Resume Review <span>AI</span>
        </h1>
        <button
          className="btn-ghost"
          onClick={() => setView(view === 'review' ? 'history' : 'review')}
        >
          {view === 'review' ? `History (${history.length})` : '← Back'}
        </button>
      </header>

      <main className="main">
        {view === 'history' ? (
          <HistoryList items={history} />
        ) : (
          <>
            <ResumeInput onSubmit={handleSubmit} loading={loading} />
            {error && <p className="error-box">{error}</p>}
            <ScoreDisplay result={result} />
          </>
        )}
      </main>
    </div>
  )
}
