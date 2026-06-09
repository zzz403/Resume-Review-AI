import { useEffect, useState } from 'react'
import { UploadPanel } from './components/UploadPanel'
import {
  API_BASE,
  clearApplicationData,
  createStudent,
  deleteStudent,
  getLlmSettings,
  getStudent,
  getStudents,
  saveLlmSettings,
  submitApplication,
  submitTeacherEvaluation,
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
  ['Application note', 'general_application_note'],
  ['Sunnybrook form note', 'sunnybrook_form_note'],
]

const TEACHER_FIELDS: [string, string][] = [
  ['Teacher report /5', 'teacher_report_rating_5'],
  ['Teacher total score', 'teacher_evaluation_total_score'],
  ['Academic ranking', 'academic_ranking'],
  ['Teacher comments', 'teacher_comments'],
  ['Teacher evaluation note', 'teacher_evaluation_note'],
]

function nonEmpty(value: unknown): boolean {
  return value !== '' && value !== null && value !== undefined
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

export default function App() {
  const [view, setView] = useState<'roster' | 'detail'>('roster')
  const [students, setStudents] = useState<StudentSummary[]>([])
  const [search, setSearch] = useState('')
  const [newName, setNewName] = useState('')
  const [creating, setCreating] = useState(false)

  const [detail, setDetail] = useState<StudentDetail | null>(null)
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const [appFileName, setAppFileName] = useState<string | null>(null)
  const [teacherFileName, setTeacherFileName] = useState<string | null>(null)
  const [uploadingApp, setUploadingApp] = useState(false)
  const [uploadingTeacher, setUploadingTeacher] = useState(false)

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

  async function handleCreate() {
    const name = newName.trim()
    if (!name) return
    setCreating(true)
    setError(null)
    try {
      const student = await createStudent(name)
      setNewName('')
      refreshStudents()
      openStudent(student.student_id)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not create student.')
    } finally {
      setCreating(false)
    }
  }

  async function openStudent(studentId: string) {
    setError(null)
    setSelectedId(studentId)
    setDetail(null)
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
    setAppFileName(file.name)
    setError(null)
    setUploadingApp(true)
    try {
      const updated = await submitApplication(selectedId, file)
      setDetail(updated)
      refreshStudents()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit this application.')
    } finally {
      setUploadingApp(false)
    }
  }

  async function handleTeacherFile(file: File) {
    if (!selectedId) return
    setTeacherFileName(file.name)
    setError(null)
    setUploadingTeacher(true)
    try {
      const updated = await submitTeacherEvaluation(selectedId, file)
      setDetail(updated)
      refreshStudents()
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Could not submit this teacher evaluation.')
    } finally {
      setUploadingTeacher(false)
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

  return (
    <div className="app">
      <header className="header">
        <h1 className="logo">Student Review <span>AI</span></h1>
        <div className="header-actions">
          {view === 'detail' && (
            <button className="btn-ghost" onClick={() => { setView('roster'); refreshStudents() }}>← All students</button>
          )}
          <a className="btn-ghost" href={`${API_BASE}/applications.xlsx`}>Download xlsx</a>
          <button className="btn-ghost" onClick={() => setShowSettings(true)}>Settings</button>
        </div>
      </header>

      {error && <p className="error-banner">{error}</p>}

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
            <small>FUS Lab · Applicant Review</small>
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
            <button className="btn-primary roster-add" onClick={handleCreate} disabled={creating || !newName.trim()}>
              {creating ? 'Adding…' : '+ New Student'}
            </button>
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
                        <td><span className={`pill ${status.cls}`}>{status.label}</span></td>
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
        <div className="submission-layout">
          <button className="back-link" onClick={() => { setView('roster'); refreshStudents() }}>
            ← Back to all students
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
              </div>
            )}
          </div>

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
            {(uploadingApp || uploadingTeacher) && <p className="placeholder">Processing with AI…</p>}
            <FieldGroup title="Application" detail={detail} fields={APPLICATION_FIELDS} empty="No application uploaded yet." />
            <FieldGroup title="Teacher Evaluation" detail={detail} fields={TEACHER_FIELDS} empty="No teacher evaluation uploaded yet." />
            <button className="btn-danger" onClick={handleDeleteStudent}>Delete student</button>
          </div>
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
}: {
  title: string
  detail: StudentDetail | null
  fields: [string, string][]
  empty: string
}) {
  const rows = detail ? fields.filter(([, key]) => nonEmpty(detail[key])) : []
  return (
    <div className="field-group">
      <div className="field-group-title">
        <p className="score-label">{title}</p>
        <span className={`pill ${rows.length ? 'pill-good' : 'pill-muted'}`}>{rows.length ? `${rows.length} fields` : 'empty'}</span>
      </div>
      {rows.length === 0 ? (
        <p className="placeholder">{empty}</p>
      ) : (
        <dl className="field-list">
          {rows.map(([label, key]) => (
            <div className="field-row" key={key}>
              <dt>{label}</dt>
              <dd>{String(detail?.[key])}</dd>
            </div>
          ))}
        </dl>
      )}
    </div>
  )
}
