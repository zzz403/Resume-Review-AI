import { useEffect, useState } from 'react'
import { ProcessingBar } from './components/ProcessingBar'
import { UploadPanel } from './components/UploadPanel'
import { StudentReview } from './components/StudentReview'
import { Toast, type ToastState } from './components/Toast'
import {
  API_BASE,
  clearApplicationData,
  createStudent,
  deleteStudent,
  DuplicateImportError,
  getLlmSettings,
  getStudent,
  getStudents,
  importFile,
  saveLlmSettings,
  submitApplication,
  submitTeacherEvaluation,
  updateStudent,
} from './api'
import type { StudentDetail, StudentSummary } from './types'

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic (Claude)',
  deepseek: 'DeepSeek',
  gemini: 'Google Gemini',
  openai: 'OpenAI (ChatGPT)',
}

const KEY_PLACEHOLDERS: Record<string, string> = {
  anthropic: 'Paste sk-ant-... key',
  deepseek: 'Paste sk-... key',
  gemini: 'Paste AIza... key',
  openai: 'Paste sk-... key',
}

const APPLICATION_FIELDS: [string, string][] = [
  ['Application note', 'general_application_note'],
  ['School', 'school'],
  ['City', 'city'],
  ['Grade', 'current_grade'],
  ['Gender', 'gender'],
  ['Resume /10', 'resume_rating_10'],
  ['Cover letter /10', 'cover_letter_rating_10'],
  ['STEM statement /10', 'stem_statement_rating_10'],
  ['FUS understanding /5', 'fus_understanding_rating'],
  ['Transcript vs median /5', 'transcript_relative_to_class_median_5'],
  ['Lowest grade', 'lowest_grade_in_current_grade'],
  ['Cover letter notes', 'cover_letter_notes'],
  ['STEM statement notes', 'stem_statement_notes'],
  ['FUS understanding', 'fus_understanding_summary'],
  ['Features', 'features'],
  ['Volunteer experience', 'volunteer_experience'],
  ['Previous research', 'previous_research_experience'],
  ['Career goals', 'career_goals'],
  ['Commitment to STEM', 'commitment_to_stem'],
  ['Sunnybrook form note', 'sunnybrook_form_note'],
]

const TEACHER_FIELDS: [string, string][] = [
  ['Teacher evaluation note', 'teacher_evaluation_note'],
  ['Teacher report /5', 'teacher_report_rating_5'],
  ['Teacher total score', 'teacher_evaluation_total_score'],
  ['Academic ranking', 'academic_ranking'],
  ['Teacher comments', 'teacher_comments'],
]

// Per-student in-flight upload tracking, kept at App level so the roster can
// keep showing "AI processing…" even after the user navigates away from detail.
interface ProcState {
  app: boolean
  teacher: boolean
  startedAt: number
}

interface DuplicateCandidate {
  requestedName: string
  existing: StudentSummary
}

function nonEmpty(value: unknown): boolean {
  return value !== '' && value !== null && value !== undefined
}

// Keys whose value actually changed between two student snapshots — used to
// briefly highlight the fields the AI just wrote.
function changedFieldKeys(before: StudentDetail | null, after: StudentDetail | null): Set<string> {
  const keys = new Set<string>()
  if (!after) return keys
  const all = new Set([...Object.keys(before ?? {}), ...Object.keys(after)])
  for (const k of all) {
    if (String(before?.[k] ?? '') !== String(after[k] ?? '')) keys.add(k)
  }
  return keys
}

function countFilled(detail: StudentDetail | null, fields: [string, string][]): number {
  if (!detail) return 0
  return fields.filter(([, key]) => nonEmpty(detail[key])).length
}

function hasAny(detail: StudentDetail | null, fields: [string, string][]): boolean {
  if (!detail) return false
  return fields.some(([, key]) => nonEmpty(detail[key]))
}

function initials(name: string): string {
  const parts = name.trim().split(/\s+/).filter(Boolean)
  if (parts.length === 0) return '?'
  return (parts[0][0] + (parts[1]?.[0] ?? '')).toUpperCase()
}

function Monogram({ name }: { name: string }) {
  return <span className="monogram" aria-hidden="true">{initials(name)}</span>
}

function ScoreChip({ value, max }: { value: string | number; max: number }) {
  if (!nonEmpty(value)) return <span className="chip chip-empty">—</span>
  const num = Number(value)
  if (Number.isNaN(num)) return <span className="chip chip-empty">{String(value)}</span>
  const ratio = num / max
  const cls = ratio >= 0.7 ? 'chip-good' : ratio >= 0.4 ? 'chip-warn' : 'chip-bad'
  return <span className={`chip ${cls}`}>{num}</span>
}

function rosterStatus(s: StudentSummary): { label: string; cls: string } {
  if (s.has_application && s.has_teacher_evaluation) return { label: 'Complete', cls: 'pill-good' }
  if (s.has_application) return { label: 'Needs teacher eval', cls: 'pill-warn' }
  if (s.has_teacher_evaluation) return { label: 'Needs application', cls: 'pill-warn' }
  return { label: 'Empty', cls: 'pill-muted' }
}

function normalizedName(name: string): string {
  return name.trim().replace(/\s+/g, ' ').toLowerCase()
}

function displayValue(key: string, value: unknown): string {
  if (!nonEmpty(value)) return 'null'
  if (key === 'volunteer_experience' || key === 'previous_research_experience') {
    if (value === true || value === 'true') return 'Yes'
    if (value === false || value === 'false') return 'No'
  }
  return String(value)
}

function duplicateReasonLabel(reason: string): string {
  if (reason === 'email') return 'email'
  if (reason === 'reversed_name') return 'reversed name'
  if (reason === 'same_name_tokens') return 'same name words'
  return 'name'
}

export default function App() {
  const [view, setView] = useState<'roster' | 'detail'>('roster')
  // The detail page opens in read-only "summary" mode; the editable PDF + form
  // workspace is entered explicitly via the Edit button so the upload-first flow
  // stays the default.
  const [editMode, setEditMode] = useState(false)
  const [students, setStudents] = useState<StudentSummary[]>([])
  const [search, setSearch] = useState('')
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)
  const [importingApplications, setImportingApplications] = useState(false)
  const [importProgress, setImportProgress] = useState('')
  const [duplicateCandidate, setDuplicateCandidate] = useState<DuplicateCandidate | null>(null)

  const [detail, setDetail] = useState<StudentDetail | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [appFileName, setAppFileName] = useState<string | null>(null)
  const [teacherFileName, setTeacherFileName] = useState<string | null>(null)
  const [uploadingApp, setUploadingApp] = useState(false)
  const [uploadingTeacher, setUploadingTeacher] = useState(false)
  const [processing, setProcessing] = useState<Record<string, ProcState>>({})
  const [changedKeys, setChangedKeys] = useState<Set<string>>(new Set())
  const [toast, setToast] = useState<ToastState | null>(null)

  const [showSettings, setShowSettings] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // ── AI provider settings ──
  const [availableProviders, setAvailableProviders] = useState<string[]>(['anthropic', 'deepseek', 'gemini', 'openai'])
  const [availableVisionProviders, setAvailableVisionProviders] = useState<string[]>(['anthropic', 'gemini', 'openai'])
  const [textProvider, setTextProvider] = useState('anthropic')
  const [visionProvider, setVisionProvider] = useState('anthropic')
  const [activeTextProvider, setActiveTextProvider] = useState<string | null>(null)
  const [activeVisionProvider, setActiveVisionProvider] = useState<string | null>(null)
  const [textProviderConfigured, setTextProviderConfigured] = useState(false)
  const [visionProviderConfigured, setVisionProviderConfigured] = useState(false)
  const [textApiKey, setTextApiKey] = useState('')
  const [visionApiKey, setVisionApiKey] = useState('')
  const [savingTextApiKey, setSavingTextApiKey] = useState(false)
  const [savingVisionApiKey, setSavingVisionApiKey] = useState(false)
  const [apiKeyMessage, setApiKeyMessage] = useState<string | null>(null)

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === 'Escape') setShowSettings(false)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [])

  // Auto-dismiss toasts: success is brief, error lingers a bit longer.
  useEffect(() => {
    if (!toast) return
    const id = setTimeout(() => setToast(null), toast.kind === 'success' ? 3200 : 6000)
    return () => clearTimeout(id)
  }, [toast])

  // Clear the "just updated" highlight shortly after it plays.
  useEffect(() => {
    if (changedKeys.size === 0) return
    const id = setTimeout(() => setChangedKeys(new Set()), 1800)
    return () => clearTimeout(id)
  }, [changedKeys])

  function startProcessing(studentId: string, kind: 'app' | 'teacher') {
    setProcessing((prev) => {
      const existing = prev[studentId]
      return {
        ...prev,
        [studentId]: {
          app: kind === 'app' ? true : existing?.app ?? false,
          teacher: kind === 'teacher' ? true : existing?.teacher ?? false,
          startedAt: existing?.startedAt ?? Date.now(),
        },
      }
    })
  }

  function stopProcessing(studentId: string, kind: 'app' | 'teacher') {
    setProcessing((prev) => {
      const existing = prev[studentId]
      if (!existing) return prev
      const next: ProcState = {
        ...existing,
        app: kind === 'app' ? false : existing.app,
        teacher: kind === 'teacher' ? false : existing.teacher,
      }
      if (!next.app && !next.teacher) {
        const { [studentId]: _drop, ...rest } = prev
        return rest
      }
      return { ...prev, [studentId]: next }
    })
  }

  useEffect(() => {
    refreshStudents()
    getLlmSettings()
      .then((settings) => {
        if (settings.available_providers?.length) setAvailableProviders(settings.available_providers)
        if (settings.available_vision_providers?.length) setAvailableVisionProviders(settings.available_vision_providers)
        setTextProvider(settings.text_provider ?? settings.provider)
        setVisionProvider(settings.vision_provider ?? settings.provider)
        setActiveTextProvider(settings.text_provider ?? settings.provider)
        setActiveVisionProvider(settings.vision_provider ?? settings.provider)
        setTextProviderConfigured(settings.text_configured ?? settings.configured)
        setVisionProviderConfigured(settings.vision_configured ?? settings.configured)
      })
      .catch(() => {})
  }, [])

  function refreshStudents() {
    getStudents()
      .then((s) => { setStudents(s); setError(null) })
      .catch(() => setError('Could not load students.'))
  }

  async function handleCreate(allowDuplicate = false) {
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    setError(null)
    try {
      if (!allowDuplicate) {
        const latestStudents = await getStudents()
        setStudents(latestStudents)
        const duplicate = latestStudents.find((s) => normalizedName(s.applicant_name) === normalizedName(name))
        if (duplicate) {
          setDuplicateCandidate({ requestedName: name, existing: duplicate })
          return
        }
      }
      const student = await createStudent(name)
      setNewName('')
      setDuplicateCandidate(null)
      refreshStudents()
      openStudent(student.student_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create student.')
    } finally {
      setCreating(false)
    }
  }

  async function handleImportApplications(files: FileList | null) {
    const selected = Array.from(files ?? [])
    if (selected.length === 0) return
    setImportingApplications(true)
    setImportProgress(`0/${selected.length}`)
    setError(null)
    let imported = 0
    let skipped = 0
    const duplicateWarnings: string[] = []
    try {
      for (let index = 0; index < selected.length; index += 1) {
        const file = selected[index]
        setImportProgress(`${index + 1}/${selected.length}`)
        try {
          await importFile(file)
          imported += 1
          refreshStudents()
        } catch (err) {
          if (err instanceof DuplicateImportError) {
            skipped += 1
            const filename = err.filename || file.name
            const matched = err.matchedApplicantName || 'existing applicant'
            const docType = err.docType ? `${err.docType} ` : ''
            const reason = duplicateReasonLabel(err.reason)
            const email = err.matchedEmail ? ` (${err.matchedEmail})` : ''
            duplicateWarnings.push(`- ${filename} matched ${matched}${email} by ${reason}; ${docType}already exists`)
            continue
          }
          throw err
        }
      }
      const skippedText = skipped ? ` · skipped ${skipped} duplicate${skipped === 1 ? '' : 's'}` : ''
      setToast({ kind: 'success', text: `Imported ${imported} file${imported === 1 ? '' : 's'}${skippedText}` })
      if (duplicateWarnings.length > 0) {
        setError(`Skipped duplicate files:\n${duplicateWarnings.join('\n')}`)
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not import files.'
      setError(msg)
      setToast({ kind: 'error', text: `Import stopped after ${imported} imported, ${skipped} skipped` })
    } finally {
      setImportingApplications(false)
      setImportProgress('')
    }
  }

  function handleOpenDuplicateCandidate() {
    if (!duplicateCandidate) return
    const studentId = duplicateCandidate.existing.student_id
    setDuplicateCandidate(null)
    setNewName('')
    openStudent(studentId)
  }

  async function openStudent(studentId: string) {
    setError(null)
    setSelectedId(studentId)
    setDetail(null)
    setEditMode(false)
    setView('detail')
    try {
      const data = await getStudent(studentId)
      setDetail(data)
      setAppFileName((data.file_name as string) || null)
      setTeacherFileName((data.teacher_evaluation_file_name as string) || null)
    } catch {
      setError('Could not load this student.')
    }
  }

  async function handleAppFile(file: File) {
    if (!selectedId) return
    const studentId = selectedId
    const before = detail
    setAppFileName(file.name)
    setError(null)
    setUploadingApp(true)
    startProcessing(studentId, 'app')
    try {
      const updated = await submitApplication(studentId, file)
      setDetail(updated)
      setChangedKeys(changedFieldKeys(before, updated))
      refreshStudents()
      setToast({ kind: 'success', text: `Application processed · ${countFilled(updated, APPLICATION_FIELDS)} fields read` })
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not submit this application.'
      setError(msg)
      setToast({ kind: 'error', text: 'AI processing failed — no results were saved for the application.' })
    } finally {
      setUploadingApp(false)
      stopProcessing(studentId, 'app')
    }
  }

  async function handleTeacherFile(file: File) {
    if (!selectedId) return
    const studentId = selectedId
    const before = detail
    setTeacherFileName(file.name)
    setError(null)
    setUploadingTeacher(true)
    startProcessing(studentId, 'teacher')
    try {
      const updated = await submitTeacherEvaluation(studentId, file)
      setDetail(updated)
      setChangedKeys(changedFieldKeys(before, updated))
      refreshStudents()
      setToast({ kind: 'success', text: `Teacher evaluation processed · ${countFilled(updated, TEACHER_FIELDS)} fields read` })
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not submit this teacher evaluation.'
      setError(msg)
      setToast({ kind: 'error', text: 'AI processing failed — no results were saved for the teacher evaluation.' })
    } finally {
      setUploadingTeacher(false)
      stopProcessing(studentId, 'teacher')
    }
  }

  async function handleSaveEdits(updates: Record<string, string>) {
    if (!selectedId) return
    try {
      const updated = await updateStudent(selectedId, updates)
      setDetail(updated)
      refreshStudents()
      const n = Object.keys(updates).length
      setToast({ kind: 'success', text: `Saved · ${n} field${n === 1 ? '' : 's'} updated` })
    } catch (err) {
      const msg = err instanceof Error ? err.message : 'Could not save your changes.'
      setError(msg)
      setToast({ kind: 'error', text: 'Changes could not be saved.' })
      throw err
    }
  }

  async function handleDeleteStudent() {
    if (!selectedId || !detail) return
    const name = (detail.applicant_name as string) || 'this student'
    if (!window.confirm(`Delete ${name} and all their saved data? This cannot be undone.`)) return
    try {
      await deleteStudent(selectedId)
      setView('roster')
      setSelectedId(null)
      setDetail(null)
      refreshStudents()
    } catch {
      setError('Could not delete this student.')
    }
  }

  async function handleClearData() {
    if (!window.confirm('Delete ALL students, the Excel data, and saved teacher evaluation files? This cannot be undone.')) return
    setError(null)
    try {
      await clearApplicationData()
      refreshStudents()
    } catch {
      setError('Could not clear saved data.')
    }
  }

  async function handleSaveTextApiKey() {
    setError(null)
    setApiKeyMessage(null)
    setSavingTextApiKey(true)
    try {
      const response = await saveLlmSettings(textProvider, textApiKey, 'text')
      setTextApiKey('')
      setActiveTextProvider(response.provider)
      setTextProviderConfigured(response.configured)
      setApiKeyMessage(`${response.message} (${response.key_preview})`)
    } catch (err) {
      setApiKeyMessage(null)
      setError(err instanceof Error ? err.message : 'Text provider key could not be saved.')
    } finally {
      setSavingTextApiKey(false)
    }
  }

  async function handleSaveVisionApiKey() {
    setError(null)
    setApiKeyMessage(null)
    setSavingVisionApiKey(true)
    try {
      const response = await saveLlmSettings(visionProvider, visionApiKey, 'vision')
      setVisionApiKey('')
      setActiveVisionProvider(response.provider)
      setVisionProviderConfigured(response.configured)
      setApiKeyMessage(`${response.message} (${response.key_preview})`)
    } catch (err) {
      setApiKeyMessage(null)
      setError(err instanceof Error ? err.message : 'Image reading provider key could not be saved.')
    } finally {
      setSavingVisionApiKey(false)
    }
  }

  const filtered = students.filter((s) =>
    `${s.applicant_name} ${s.email} ${s.school}`.toLowerCase().includes(search.trim().toLowerCase())
  )

  const detailHasApp = hasAny(detail, APPLICATION_FIELDS)
  const detailHasTeacher = hasAny(detail, TEACHER_FIELDS)

  const activeProc = selectedId ? processing[selectedId] : undefined
  const procLabel = activeProc?.app && activeProc?.teacher
    ? 'AI is analyzing the application & teacher evaluation'
    : activeProc?.teacher
      ? 'AI is analyzing the teacher evaluation'
      : 'AI is analyzing the application'

  return (
    <div className="app">
      <header className="header">
        <h1 className="logo">High School Application Review <span>AI</span></h1>
        <div className="header-actions">
          {view === 'detail' && (
            <button className="btn-ghost" onClick={() => { setView('roster'); refreshStudents() }}>← All students</button>
          )}
          <a className="btn-ghost" href={`${API_BASE}/applications.xlsx`}>Download xlsx</a>
          <button className="btn-ghost" onClick={() => setShowSettings(true)}>Settings</button>
        </div>
      </header>

      {error && <p className="error-banner">{error}</p>}

      {duplicateCandidate && (
        <div className="modal-overlay">
          <div className="modal modal-small" role="dialog" aria-modal="true" aria-labelledby="duplicate-title">
            <div className="modal-head">
              <div>
                <h2 id="duplicate-title">Candidate already exists</h2>
                <small>Duplicate name found</small>
              </div>
            </div>
            <div className="modal-body">
              <p className="modal-copy">
                A candidate named <strong>{duplicateCandidate.existing.applicant_name}</strong> is already in the system.
              </p>
              <p className="placeholder">
                Open the existing profile, or add <strong>{duplicateCandidate.requestedName}</strong> as a separate candidate.
              </p>
              <div className="modal-actions">
                <button className="btn-secondary" onClick={handleOpenDuplicateCandidate}>
                  Open existing profile
                </button>
                <button className="btn-primary" onClick={() => handleCreate(true)} disabled={creating}>
                  {creating ? 'Adding...' : 'Add as new candidate'}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {showSettings && (
        <div className="modal-overlay" onClick={() => setShowSettings(false)}>
          <div className="modal" role="dialog" aria-modal="true" onClick={(e) => e.stopPropagation()}>
            <div className="modal-head">
              <div>
                <h2>Settings</h2>
                <small>AI providers &amp; data</small>
              </div>
              <button className="modal-close" onClick={() => setShowSettings(false)} aria-label="Close">✕</button>
            </div>

            <div className="modal-body">
              <p className="label">AI Providers</p>
              {activeTextProvider && (
                <p className="placeholder">
                  Text: {PROVIDER_LABELS[activeTextProvider] ?? activeTextProvider}
                  {' — '}{textProviderConfigured ? '✓ key configured' : '⚠ no key set'}
                </p>
              )}
              {activeVisionProvider && (
                <p className="placeholder">
                  Image reading: {PROVIDER_LABELS[activeVisionProvider] ?? activeVisionProvider}
                  {' — '}{visionProviderConfigured ? '✓ key configured' : '⚠ no key set'}
                </p>
              )}
              <div className="provider-grid">
                <div className="provider-control">
                  <div className="provider-heading"><p className="score-label">Text AI</p></div>
                  <select className="text-input" value={textProvider} onChange={(e) => setTextProvider(e.target.value)}>
                    {availableProviders.map((name) => (
                      <option key={name} value={name}>{PROVIDER_LABELS[name] ?? name}</option>
                    ))}
                  </select>
                  <div className="settings-row">
                    <input
                      className="text-input"
                      type="password"
                      value={textApiKey}
                      onChange={(e) => setTextApiKey(e.target.value)}
                      placeholder={KEY_PLACEHOLDERS[textProvider] ?? 'Paste API key'}
                      autoComplete="off"
                    />
                    <button className="btn-secondary" onClick={handleSaveTextApiKey} disabled={savingTextApiKey || !textApiKey.trim()}>
                      {savingTextApiKey ? 'Checking...' : 'Save'}
                    </button>
                  </div>
                </div>
                <div className="provider-control">
                  <div className="provider-heading">
                    <p className="score-label">Image Reading AI</p>
                    <span className="recommended-pill">Recommend ChatGPT</span>
                  </div>
                  <select className="text-input" value={visionProvider} onChange={(e) => setVisionProvider(e.target.value)}>
                    {availableVisionProviders.map((name) => (
                      <option key={name} value={name}>{PROVIDER_LABELS[name] ?? name}</option>
                    ))}
                  </select>
                  <div className="settings-row">
                    <input
                      className="text-input"
                      type="password"
                      value={visionApiKey}
                      onChange={(e) => setVisionApiKey(e.target.value)}
                      placeholder={KEY_PLACEHOLDERS[visionProvider] ?? 'Paste API key'}
                      autoComplete="off"
                    />
                    <button className="btn-secondary" onClick={handleSaveVisionApiKey} disabled={savingVisionApiKey || !visionApiKey.trim()}>
                      {savingVisionApiKey ? 'Checking...' : 'Save'}
                    </button>
                  </div>
                </div>
              </div>
              {apiKeyMessage && <p className="success-text">{apiKeyMessage}</p>}

              <div className="modal-danger">
                <p className="score-label">Danger zone</p>
                <button className="btn-danger" onClick={handleClearData}>Reset all saved data</button>
              </div>
            </div>
          </div>
        </div>
      )}

      {view === 'roster' ? (
        <div className="roster-col">
          <div className="roster-head">
            <h2>Students</h2>
            <small>Hynynen Lab · Applicant Review</small>
          </div>
          <div className="roster-toolbar">
            <input
              className="text-input"
              placeholder="Search by name, email, or school"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
            />
            <input
              className="text-input"
              placeholder="New student name"
              value={newName}
              onChange={(e) => setNewName(e.target.value)}
              onKeyDown={(e) => { if (e.key === 'Enter') handleCreate() }}
            />
            <button className="btn-primary roster-add" onClick={() => handleCreate()} disabled={creating || !newName.trim()}>
              {creating ? 'Adding…' : '+ New Student'}
            </button>
            <label className={`btn-secondary roster-import ${importingApplications ? 'is-disabled' : ''}`}>
              <input
                type="file"
                accept=".pdf,.doc,.docx,.png,.jpg,.jpeg,.webp"
                multiple
                disabled={importingApplications}
                onChange={(e) => {
                  handleImportApplications(e.currentTarget.files)
                  e.currentTarget.value = ''
                }}
              />
              {importingApplications ? `Importing ${importProgress}` : 'Import files'}
            </label>
          </div>

          <div className="panel result-panel roster-card">
            {filtered.length === 0 ? (
              <p className="placeholder" style={{ padding: '24px 14px' }}>
                {students.length === 0 ? 'No students yet. Add one above to get started.' : 'No matches.'}
              </p>
            ) : (
              <table className="roster-table">
                <thead>
                  <tr>
                    <th>Student</th>
                    <th>School</th>
                    <th className="num">Grade</th>
                    <th>Status</th>
                    <th className="num">Resume</th>
                    <th className="num">Cover</th>
                    <th className="num">STEM</th>
                    <th className="num">Teacher</th>
                    <th>Ranking</th>
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((s) => {
                    const status = rosterStatus(s)
                    const proc = processing[s.student_id]
                    const isProcessing = !!(proc && (proc.app || proc.teacher))
                    return (
                      <tr key={s.student_id} className="roster-row" onClick={() => openStudent(s.student_id)}>
                        <td>
                          <div className="who">
                            <Monogram name={s.applicant_name} />
                            <div className="who-text">
                              <span className="roster-name">{s.applicant_name || '(unnamed)'}</span>
                              {s.email && <span className="who-email">{s.email}</span>}
                            </div>
                          </div>
                        </td>
                        <td>{s.school || '—'}</td>
                        <td className="num">{s.current_grade || '—'}</td>
                        <td>
                          {isProcessing ? (
                            <span className="pill pill-proc"><span className="spinner" aria-hidden="true" />AI processing…</span>
                          ) : (
                            <span className={`pill ${status.cls}`}>{status.label}</span>
                          )}
                        </td>
                        <td className="num"><ScoreChip value={s.resume_rating_10} max={10} /></td>
                        <td className="num"><ScoreChip value={s.cover_letter_rating_10} max={10} /></td>
                        <td className="num"><ScoreChip value={s.stem_statement_rating_10} max={10} /></td>
                        <td className="num"><ScoreChip value={s.teacher_report_rating_5} max={5} /></td>
                        <td>{s.academic_ranking || '—'}</td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            )}
            <p className="roster-foot">{students.length} student{students.length === 1 ? '' : 's'} stored</p>
          </div>
        </div>
      ) : (
        <div className={`submission-layout ${editMode ? 'review-mode' : ''}`}>
          <button
            className="back-link"
            onClick={() => { if (editMode) { setEditMode(false) } else { setView('roster'); refreshStudents() } }}
          >
            {editMode ? '← Back to summary' : '← Back to all students'}
          </button>
          <div className="detail-header">
            <Monogram name={(detail?.applicant_name as string) || ''} />
            <div className="detail-id">
              <h2>{(detail?.applicant_name as string) || 'Loading…'}</h2>
              {detail && (detail.email as string) && <span className="detail-sub">{detail.email as string}</span>}
            </div>
            {detail && (
              <div className="detail-status">
                <span className={`pill ${detailHasApp ? 'pill-good' : 'pill-muted'}`}>
                  {detailHasApp ? 'Application ✓' : 'No application'}
                </span>
                <span className={`pill ${detailHasTeacher ? 'pill-good' : 'pill-muted'}`}>
                  {detailHasTeacher ? 'Teacher eval ✓' : 'No teacher eval'}
                </span>
                {!editMode ? (
                  <button
                    className="btn-primary edit-toggle"
                    onClick={() => setEditMode(true)}
                    disabled={!detailHasApp && !detailHasTeacher}
                    title={!detailHasApp && !detailHasTeacher ? 'Upload a document first' : 'Edit fields against the source PDF'}
                  >
                    ✎ Edit &amp; review
                  </button>
                ) : (
                  <button className="btn-ghost edit-toggle" onClick={() => setEditMode(false)}>
                    ✓ Done
                  </button>
                )}
              </div>
            )}
          </div>

          {activeProc && (activeProc.app || activeProc.teacher) && (
            <ProcessingBar startedAt={activeProc.startedAt} label={procLabel} />
          )}

          {!detail ? (
            <div className="panel result-panel">
              <p className="placeholder">Loading…</p>
            </div>
          ) : editMode ? (
            <StudentReview
              studentId={selectedId as string}
              detail={detail}
              onUploadApp={handleAppFile}
              onUploadTeacher={handleTeacherFile}
              uploadingApp={uploadingApp}
              uploadingTeacher={uploadingTeacher}
              changedKeys={changedKeys}
              onSave={handleSaveEdits}
              onDelete={handleDeleteStudent}
            />
          ) : (
            <>
              <div className="upload-row">
                <UploadPanel
                  onFileSelect={handleAppFile}
                  fileName={appFileName}
                  submitted={detailHasApp}
                  loading={uploadingApp}
                  label="Application"
                  emptyTitle="Drop the application here"
                  savedLabel="Application Processed"
                  loadingLabel="Processing…"
                  buttonIdleLabel="Application"
                />
                <UploadPanel
                  onFileSelect={handleTeacherFile}
                  fileName={teacherFileName}
                  submitted={detailHasTeacher}
                  loading={uploadingTeacher}
                  label="Teacher Evaluation"
                  emptyTitle="Drop the teacher evaluation here"
                  savedLabel="Teacher Evaluation Processed"
                  loadingLabel="Processing…"
                  buttonIdleLabel="Teacher Evaluation"
                />
              </div>

              <div className="panel result-panel">
                <FieldGroup title="Application" detail={detail} fields={APPLICATION_FIELDS} empty="No application uploaded yet." loading={uploadingApp} changedKeys={changedKeys} />
                <FieldGroup title="Teacher Evaluation" detail={detail} fields={TEACHER_FIELDS} empty="No teacher evaluation uploaded yet." loading={uploadingTeacher} changedKeys={changedKeys} />
                <button className="btn-danger" onClick={handleDeleteStudent}>Delete student</button>
              </div>
            </>
          )}
        </div>
      )}

      {toast && (
        <div className="toast-wrap">
          <Toast kind={toast.kind} text={toast.text} onClose={() => setToast(null)} />
        </div>
      )}
    </div>
  )
}

function FieldGroup({
  title,
  detail,
  fields,
  empty,
  loading = false,
  changedKeys,
}: {
  title: string
  detail: StudentDetail | null
  fields: [string, string][]
  empty: string
  loading?: boolean
  changedKeys?: Set<string>
}) {
  const filledCount = detail ? fields.filter(([, key]) => nonEmpty(detail[key])).length : 0
  return (
    <div className="field-group">
      <div className="field-group-title">
        <p className="score-label">{title}</p>
        {loading ? (
          <span className="pill pill-proc"><span className="spinner" aria-hidden="true" />reading…</span>
        ) : (
          <span className={`pill ${filledCount ? 'pill-good' : 'pill-muted'}`}>{filledCount}/{fields.length} fields</span>
        )}
      </div>
      {loading ? (
        <FieldSkeleton />
      ) : (
        <dl className="field-list">
          {fields.map(([label, key]) => (
            <div className={`field-row ${changedKeys?.has(key) ? 'field-flash' : ''}`} key={key}>
              <dt>{label}</dt>
              <dd>{displayValue(key, detail?.[key])}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}

function FieldSkeleton() {
  const widths = ['mid', 'wide', 'short', 'wide', 'mid'] as const
  return (
    <div className="skeleton-list">
      {widths.map((w, i) => (
        <div className="skeleton-row" key={i}>
          <span className="skeleton-bar short" />
          <span className={`skeleton-bar ${w}`} />
        </div>
      ))}
    </div>
  )
}
