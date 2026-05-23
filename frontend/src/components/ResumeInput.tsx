import { useState } from 'react'

interface Props {
  onSubmit: (text: string) => void
  loading: boolean
}

export function ResumeInput({ onSubmit, loading }: Props) {
  const [text, setText] = useState('')

  return (
    <div className="card">
      <label className="label">Your Resume</label>
      <textarea
        className="textarea"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="Paste the full text of your resume here…"
        rows={13}
      />
      <button
        className="btn-primary"
        onClick={() => onSubmit(text)}
        disabled={loading || text.trim().length === 0}
      >
        {loading ? 'Analyzing…' : 'Review Resume →'}
      </button>
    </div>
  )
}
