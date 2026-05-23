import { useState } from 'react'
import { UploadPanel } from './components/UploadPanel'
import { ResultPanel } from './components/ResultPanel'
import { HistoryList } from './components/HistoryList'
import { extractResume, submitResume, getHistory } from './api'
import type { Review, ReviewResponse } from './types'

export default function App() {
  const [fileName, setFileName] = useState<string | null>(null)
  const [extractedText, setExtractedText] = useState<string | null>(null)
  const [result, setResult] = useState<ReviewResponse | null>(null)
  const [history, setHistory] = useState<Review[]>([])
  const [extracting, setExtracting] = useState(false)
  const [reviewing, setReviewing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'main' | 'history'>('main')

  async function handleFileSelect(file: File) {
    setFileName(file.name)
    setExtractedText(null)
    setResult(null)
    setError(null)
    setExtracting(true)
    try {
      const { text } = await extractResume(file)
      setExtractedText(text)
    } catch {
      setError('Could not extract text from this file.')
    } finally {
      setExtracting(false)
    }
  }

  async function handleReview() {
    if (!extractedText) return
    setReviewing(true)
    setError(null)
    try {
      const res = await submitResume(extractedText)
      setResult(res)
      getHistory().then(setHistory).catch(() => {})
    } catch {
      setError('Review failed. Is the backend running on port 8000?')
    } finally {
      setReviewing(false)
    }
  }

  async function handleShowHistory() {
    setView('history')
    getHistory().then(setHistory).catch(() => {})
  }

  return (
    <div className="app">
      <header className="header">
        <h1 className="logo">Resume Review <span>AI</span></h1>
        <button
          className="btn-ghost"
          onClick={() => view === 'main' ? handleShowHistory() : setView('main')}
        >
          {view === 'main' ? 'History' : '← Back'}
        </button>
      </header>

      {error && <p className="error-banner">{error}</p>}

      {view === 'history' ? (
        <div className="single-col">
          <HistoryList items={history} />
        </div>
      ) : (
        <div className="two-col">
          <UploadPanel
            onFileSelect={handleFileSelect}
            onReview={handleReview}
            fileName={fileName}
            hasExtracted={!!extractedText}
            loading={reviewing}
          />
          <ResultPanel
            extractedText={extractedText}
            result={result}
            extracting={extracting}
          />
        </div>
      )}
    </div>
  )
}
