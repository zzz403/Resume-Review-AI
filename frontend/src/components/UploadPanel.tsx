import { useRef, useState, DragEvent } from 'react'

interface Props {
  onFileSelect: (file: File) => void
  onReview: () => void
  fileName: string | null
  hasExtracted: boolean
  loading: boolean
}

export function UploadPanel({ onFileSelect, onReview, fileName, hasExtracted, loading }: Props) {
  const [dragging, setDragging] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)

  function handleDrop(e: DragEvent) {
    e.preventDefault()
    setDragging(false)
    const file = e.dataTransfer.files[0]
    if (file) onFileSelect(file)
  }

  return (
    <div className="panel upload-panel">
      <p className="label">Upload Resume</p>

      <div
        className={`dropzone ${dragging ? 'dragging' : ''} ${fileName ? 'has-file' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDragging(true) }}
        onDragLeave={() => setDragging(false)}
        onDrop={handleDrop}
        onClick={() => inputRef.current?.click()}
      >
        <input
          ref={inputRef}
          type="file"
          accept=".pdf,.doc,.docx,.txt"
          style={{ display: 'none' }}
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onFileSelect(file)
          }}
        />
        {fileName ? (
          <div className="file-selected">
            <span className="file-icon">📄</span>
            <span className="file-name">{fileName}</span>
            <span className="file-change">Click to change</span>
          </div>
        ) : (
          <div className="dropzone-hint">
            <span className="dropzone-icon">⬆</span>
            <span>Drop your resume here</span>
            <span>or <u>click to browse</u></span>
            <span className="dropzone-formats">PDF · DOCX · TXT</span>
          </div>
        )}
      </div>

      <button
        className="btn-primary"
        onClick={onReview}
        disabled={!hasExtracted || loading}
      >
        {loading ? 'Reviewing…' : 'Review Resume →'}
      </button>
    </div>
  )
}
