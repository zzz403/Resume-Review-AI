import { useEffect, useMemo, useRef, useState } from 'react'
import {
  ALL_EDITABLE_KEYS,
  APPLICATION_BLOCKS,
  TEACHER_BLOCKS,
  type DocKind,
  type FieldBlock,
  type FieldDef,
} from '../fields'
import { applicationFileUrl, teacherEvaluationFileUrl } from '../api'
import type { StudentDetail } from '../types'

type FormValues = Record<string, string>

interface Props {
  studentId: string
  detail: StudentDetail
  onUploadApp: (file: File) => void
  onUploadTeacher: (file: File) => void
  uploadingApp: boolean
  uploadingTeacher: boolean
  changedKeys: Set<string>
  onSave: (updates: Record<string, string>) => Promise<void>
  onDelete: () => void
}

function toForm(detail: StudentDetail): FormValues {
  const out: FormValues = {}
  for (const key of ALL_EDITABLE_KEYS) {
    const v = detail[key]
    out[key] = v === null || v === undefined ? '' : String(v)
  }
  return out
}

const IMAGE_EXT = ['.png', '.jpg', '.jpeg', '.gif', '.webp']

function fileKind(name: string | null | undefined): 'pdf' | 'image' | 'other' | 'none' {
  if (!name) return 'none'
  const lower = name.toLowerCase()
  if (lower.endsWith('.pdf')) return 'pdf'
  if (IMAGE_EXT.some((ext) => lower.endsWith(ext))) return 'image'
  return 'other'
}

function scoreTint(value: string, max: number): string {
  if (value.trim() === '') return ''
  const num = Number(value)
  if (Number.isNaN(num)) return ''
  const ratio = num / max
  return ratio >= 0.7 ? 'score-good' : ratio >= 0.4 ? 'score-warn' : 'score-bad'
}

export function StudentReview({
  studentId,
  detail,
  onUploadApp,
  onUploadTeacher,
  uploadingApp,
  uploadingTeacher,
  changedKeys,
  onSave,
  onDelete,
}: Props) {
  const [form, setForm] = useState<FormValues>(() => toForm(detail))
  const [baseline, setBaseline] = useState<FormValues>(() => toForm(detail))
  const [saving, setSaving] = useState(false)

  const appName = (detail.file_name as string) || null
  const teacherName = (detail.teacher_evaluation_file_name as string) || null
  const appAvailable = !!appName
  const teacherAvailable = !!teacherName

  const [activeDoc, setActiveDoc] = useState<DocKind>(appAvailable || !teacherAvailable ? 'application' : 'teacher')

  // Re-seed the form whenever a genuinely new student snapshot arrives (open a
  // different student, an upload re-runs the AI, or our own save returns). This
  // never fires mid-typing because `detail`'s identity only changes on real data
  // updates, so in-progress edits are preserved until one of those moments.
  const detailRef = useRef(detail)
  useEffect(() => {
    detailRef.current = detail
    const next = toForm(detail)
    setForm(next)
    setBaseline(next)
  }, [detail])

  // Keep the viewer pointed at a document that actually exists as files come and go.
  useEffect(() => {
    if (activeDoc === 'application' && !appAvailable && teacherAvailable) setActiveDoc('teacher')
    if (activeDoc === 'teacher' && !teacherAvailable && appAvailable) setActiveDoc('application')
  }, [activeDoc, appAvailable, teacherAvailable])

  const changedFieldKeys = useMemo(
    () => ALL_EDITABLE_KEYS.filter((k) => (form[k] ?? '') !== (baseline[k] ?? '')),
    [form, baseline],
  )
  const dirty = changedFieldKeys.length > 0

  function setField(key: string, value: string) {
    setForm((prev) => ({ ...prev, [key]: value }))
  }

  function discard() {
    setForm(baseline)
  }

  async function save() {
    if (!dirty || saving) return
    const updates: Record<string, string> = {}
    for (const key of changedFieldKeys) updates[key] = form[key]
    setSaving(true)
    try {
      await onSave(updates)
      // App pushes a fresh `detail` on success, which re-seeds the baseline via
      // the effect above; this is a fallback if the parent keeps the same object.
      setBaseline({ ...form })
    } finally {
      setSaving(false)
    }
  }

  // ⌘/Ctrl+S saves without leaving the keyboard.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 's') {
        e.preventDefault()
        save()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  })

  const activeName = activeDoc === 'application' ? appName : teacherName
  const activeUrl =
    activeDoc === 'application'
      ? applicationFileUrl(studentId, appName ?? '')
      : teacherEvaluationFileUrl(studentId, teacherName ?? '')
  const activeUploading = activeDoc === 'application' ? uploadingApp : uploadingTeacher
  const onReplace = activeDoc === 'application' ? onUploadApp : onUploadTeacher

  return (
    <>
      <div className={`save-bar ${dirty ? 'is-active' : ''}`} aria-hidden={!dirty}>
        <span className="save-bar-status">
          <span className="save-dot" />
          {changedFieldKeys.length} unsaved change{changedFieldKeys.length === 1 ? '' : 's'}
        </span>
        <div className="save-bar-actions">
          <button className="btn-ghost" onClick={discard} disabled={saving}>Discard</button>
          <button className="btn-primary save-bar-save" onClick={save} disabled={saving}>
            {saving ? 'Saving…' : 'Save changes'}
          </button>
        </div>
      </div>

      <div className="review-workspace">
        <section className="review-form panel">
          <FormSection
            label="Application"
            blocks={APPLICATION_BLOCKS}
            form={form}
            baseline={baseline}
            changedKeys={changedKeys}
            onChange={setField}
            onJump={() => appAvailable && setActiveDoc('application')}
            jumpEnabled={appAvailable}
          />
          <FormSection
            label="Teacher evaluation"
            blocks={TEACHER_BLOCKS}
            form={form}
            baseline={baseline}
            changedKeys={changedKeys}
            onChange={setField}
            onJump={() => teacherAvailable && setActiveDoc('teacher')}
            jumpEnabled={teacherAvailable}
          />
          <div className="review-form-foot">
            <button className="btn-danger" onClick={onDelete}>Delete student</button>
          </div>
        </section>

        <aside className="review-doc">
          <div className="doc-tabs">
            <button
              className={`doc-tab ${activeDoc === 'application' ? 'is-active' : ''}`}
              onClick={() => setActiveDoc('application')}
            >
              Application
              {appAvailable && <span className="doc-tab-dot" aria-hidden="true" />}
            </button>
            <button
              className={`doc-tab ${activeDoc === 'teacher' ? 'is-active' : ''}`}
              onClick={() => setActiveDoc('teacher')}
            >
              Teacher eval
              {teacherAvailable && <span className="doc-tab-dot" aria-hidden="true" />}
            </button>
            <span className="doc-tabs-spacer" />
            {activeName && (
              <a className="doc-open" href={activeUrl} target="_blank" rel="noreferrer" title="Open in new tab">
                Open ↗
              </a>
            )}
          </div>

          <div className="doc-toolbar">
            <span className="doc-filename" title={activeName ?? undefined}>
              {activeUploading ? 'Reading document…' : activeName ?? 'No document uploaded'}
            </span>
            <FilePicker
              label={activeName ? 'Replace' : 'Upload'}
              loading={activeUploading}
              onPick={onReplace}
            />
          </div>

          <DocViewport
            url={activeUrl}
            name={activeName}
            kind={fileKind(activeName)}
            loading={activeUploading}
            onPick={onReplace}
            docLabel={activeDoc === 'application' ? 'application' : 'teacher evaluation'}
          />
        </aside>
      </div>
    </>
  )
}

function FormSection({
  label,
  blocks,
  form,
  baseline,
  changedKeys,
  onChange,
  onJump,
  jumpEnabled,
}: {
  label: string
  blocks: FieldBlock[]
  form: FormValues
  baseline: FormValues
  changedKeys: Set<string>
  onChange: (key: string, value: string) => void
  onJump: () => void
  jumpEnabled: boolean
}) {
  return (
    <div className="review-section">
      <div className="review-section-head">
        <h3>{label}</h3>
        <button className="doc-jump" onClick={onJump} disabled={!jumpEnabled}>
          {jumpEnabled ? 'View source ↗' : 'No file'}
        </button>
      </div>
      {blocks.map((block) => (
        <div className="review-block" key={block.title}>
          <p className="review-block-title">{block.title}</p>
          <div className="field-grid">
            {block.fields.map((field) => (
              <Field
                key={field.key}
                field={field}
                value={form[field.key] ?? ''}
                edited={(form[field.key] ?? '') !== (baseline[field.key] ?? '')}
                flash={changedKeys.has(field.key)}
                onChange={onChange}
              />
            ))}
          </div>
        </div>
      ))}
    </div>
  )
}

function Field({
  field,
  value,
  edited,
  flash,
  onChange,
}: {
  field: FieldDef
  value: string
  edited: boolean
  flash: boolean
  onChange: (key: string, value: string) => void
}) {
  const cls = `field-edit ${field.full ? 'is-full' : ''} ${edited ? 'is-edited' : ''} ${flash ? 'is-flash' : ''}`
  return (
    <label className={cls}>
      <span className="field-edit-label">
        {field.label}
        {field.type === 'score' && <span className="field-edit-max">/{field.max}</span>}
        {edited && <span className="field-edit-mark" title="Edited">●</span>}
      </span>

      {field.type === 'textarea' ? (
        <textarea
          className="field-input field-textarea"
          value={value}
          rows={2}
          placeholder={field.placeholder ?? '—'}
          onChange={(e) => onChange(field.key, e.target.value)}
        />
      ) : field.type === 'select' ? (
        <select className="field-input" value={value} onChange={(e) => onChange(field.key, e.target.value)}>
          {(field.options ?? []).map((opt) => (
            <option key={opt} value={opt}>{opt === '' ? '—' : opt}</option>
          ))}
        </select>
      ) : field.type === 'score' ? (
        <input
          className={`field-input field-score ${scoreTint(value, field.max ?? 10)}`}
          type="number"
          inputMode="decimal"
          min={0}
          max={field.max}
          step={0.5}
          value={value}
          placeholder="—"
          onChange={(e) => onChange(field.key, e.target.value)}
        />
      ) : (
        <input
          className="field-input"
          type="text"
          value={value}
          placeholder={field.placeholder ?? '—'}
          onChange={(e) => onChange(field.key, e.target.value)}
        />
      )}
    </label>
  )
}

function FilePicker({
  label,
  loading,
  onPick,
}: {
  label: string
  loading: boolean
  onPick: (file: File) => void
}) {
  const ref = useRef<HTMLInputElement>(null)
  return (
    <>
      <input
        ref={ref}
        type="file"
        accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.doc,.docx"
        hidden
        onChange={(e) => {
          const file = e.target.files?.[0]
          if (file) onPick(file)
          e.target.value = ''
        }}
      />
      <button className="btn-ghost doc-replace" onClick={() => ref.current?.click()} disabled={loading}>
        {loading ? 'Reading…' : label}
      </button>
    </>
  )
}

function DocViewport({
  url,
  name,
  kind,
  loading,
  onPick,
  docLabel,
}: {
  url: string
  name: string | null
  kind: ReturnType<typeof fileKind>
  loading: boolean
  onPick: (file: File) => void
  docLabel: string
}) {
  const [drag, setDrag] = useState(false)

  if (loading) {
    return (
      <div className="doc-viewport doc-viewport-empty">
        <span className="spinner spinner-lg" aria-hidden="true" />
        <p className="placeholder">AI is reading this {docLabel}…</p>
      </div>
    )
  }

  if (kind === 'none') {
    return (
      <label
        className={`doc-viewport doc-viewport-empty doc-dropzone ${drag ? 'is-drag' : ''}`}
        onDragOver={(e) => { e.preventDefault(); setDrag(true) }}
        onDragLeave={() => setDrag(false)}
        onDrop={(e) => {
          e.preventDefault()
          setDrag(false)
          const file = e.dataTransfer.files?.[0]
          if (file) onPick(file)
        }}
      >
        <input
          type="file"
          accept=".pdf,.png,.jpg,.jpeg,.gif,.webp,.doc,.docx"
          hidden
          onChange={(e) => {
            const file = e.target.files?.[0]
            if (file) onPick(file)
            e.target.value = ''
          }}
        />
        <div className="doc-empty-icon" aria-hidden="true">⤓</div>
        <p className="doc-empty-title">Drop the {docLabel} here</p>
        <p className="placeholder">or click to choose a PDF</p>
      </label>
    )
  }

  if (kind === 'pdf') {
    return <iframe className="doc-viewport doc-frame" src={url} title={name ?? 'Document'} />
  }

  if (kind === 'image') {
    return (
      <div className="doc-viewport doc-image-wrap">
        <img className="doc-image" src={url} alt={name ?? 'Document'} />
      </div>
    )
  }

  // Non-previewable type (e.g. .docx) — offer a download instead of a broken frame.
  return (
    <div className="doc-viewport doc-viewport-empty">
      <div className="doc-empty-icon" aria-hidden="true">📄</div>
      <p className="doc-empty-title">{name}</p>
      <p className="placeholder">This file type can’t be previewed in the browser.</p>
      <a className="btn-secondary" href={url} target="_blank" rel="noreferrer" download>
        Download file
      </a>
    </div>
  )
}
