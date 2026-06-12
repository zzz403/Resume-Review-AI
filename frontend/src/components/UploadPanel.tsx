import { useRef, useState, DragEvent } from 'react'

interface Props {
  onFileSelect: (file: File) => void
  fileName: string | null
  submitted: boolean
  loading: boolean
  label?: string
  emptyTitle?: string
  savedLabel?: string
  loadingLabel?: string
  buttonIdleLabel?: string
}

export function UploadPanel({
  onFileSelect,
  fileName,
  submitted,
  loading,
  label = 'Upload Application',
  emptyTitle = 'Drop your application here',
  savedLabel = 'Application Saved',
  loadingLabel = 'Processing...',
  buttonIdleLabel = 'Upload Application',
}: Props) {
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
      <p className="label">{label}</p>

      <div
        className={`dropzone ${dragging ? 'dragging' : ''} ${fileName ? 'has-file' : ''} ${loading ? 'processing' : ''}`}
        onDragOver={(e) => { if (!loading) { e.preventDefault(); setDragging(true) } }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { if (!loading) handleDrop(e) }}
        onClick={() => { if (!loading) inputRef.current?.click() }}
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
        {loading ? (
          <div className="file-selected">
            <span className="spinner spinner-lg" aria-hidden="true" />
            <span className="file-name">{fileName}</span>
            <span className="file-change">{loadingLabel}</span>
          </div>
        ) : fileName ? (
          <div className="file-selected">
            <span className="file-icon">📄</span>
            <span className="file-name">{fileName}</span>
            <span className="file-change">Click to change</span>
          </div>
        ) : (
          <div className="dropzone-hint">
            <span className="dropzone-icon">⬆</span>
            <span>{emptyTitle}</span>
            <span>or <u>click to browse</u></span>
            <span className="dropzone-formats">PDF · DOCX · TXT</span>
          </div>
        )}
      </div>

      {loading && <div className="indeterminate upload-progress" aria-hidden="true" />}

      <button
        className="btn-primary"
        disabled
      >
        {loading ? loadingLabel : submitted ? savedLabel : buttonIdleLabel}
      </button>
    </div>
  )
}
