export type ToastKind = 'success' | 'error'

export interface ToastState {
  kind: ToastKind
  text: string
}

export function Toast({ kind, text, onClose }: ToastState & { onClose: () => void }) {
  return (
    <div className={`toast toast-${kind}`} role="status" aria-live="polite">
      <span className="toast-icon" aria-hidden="true">{kind === 'success' ? '✓' : '!'}</span>
      <span className="toast-text">{text}</span>
      <button className="toast-close" onClick={onClose} aria-label="Dismiss">✕</button>
    </div>
  )
}
