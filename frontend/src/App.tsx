import { useEffect, useState } from 'react'
import { UploadPanel } from './components/UploadPanel'
import { HistoryList } from './components/HistoryList'
import { clearApplicationData, getHistory, getLlmSettings, saveLlmSettings, submitApplication, submitTeacherEvaluation } from './api'
import type { ApplicationSubmitResponse, Review, TeacherEvaluationSubmitResponse } from './types'

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

export default function App() {
  const [fileName, setFileName] = useState<string | null>(null)
  const [submitted, setSubmitted] = useState<ApplicationSubmitResponse | null>(null)
  const [teacherEvaluationFileName, setTeacherEvaluationFileName] = useState<string | null>(null)
  const [teacherEvaluationSubmitted, setTeacherEvaluationSubmitted] = useState<TeacherEvaluationSubmitResponse | null>(null)
  const [history, setHistory] = useState<Review[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [submittingTeacherEvaluation, setSubmittingTeacherEvaluation] = useState(false)
  const [clearingData, setClearingData] = useState(false)
  const [clearMessage, setClearMessage] = useState<string | null>(null)
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
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'main' | 'history'>('main')

  useEffect(() => {
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

  async function handleFileSelect(file: File) {
    setFileName(file.name)
    setSubmitted(null)
    setError(null)
    setSubmitting(true)
    try {
      const response = await submitApplication(file)
      setSubmitted(response)
    } catch {
      setError('Could not submit this application.')
    } finally {
      setSubmitting(false)
    }
  }

  async function handleTeacherEvaluationSelect(file: File) {
    setTeacherEvaluationFileName(file.name)
    setTeacherEvaluationSubmitted(null)
    setError(null)
    setSubmittingTeacherEvaluation(true)
    try {
      const response = await submitTeacherEvaluation(file)
      setTeacherEvaluationSubmitted(response)
    } catch {
      setError('Could not submit this teacher evaluation.')
    } finally {
      setSubmittingTeacherEvaluation(false)
    }
  }

  async function handleShowHistory() {
    setView('history')
    getHistory().then(setHistory).catch(() => {})
  }

  async function handleClearData() {
    const confirmed = window.confirm(
      'Delete all saved application rows, the Excel data, and saved teacher evaluation files? This cannot be undone.'
    )
    if (!confirmed) return

    setError(null)
    setClearMessage(null)
    setClearingData(true)
    try {
      const response = await clearApplicationData()
      setFileName(null)
      setSubmitted(null)
      setTeacherEvaluationFileName(null)
      setTeacherEvaluationSubmitted(null)
      setClearMessage(
        `Data cleared. Removed ${response.removed_teacher_evaluations.length} teacher evaluation file(s).`
      )
    } catch {
      setError('Could not clear saved application data.')
    } finally {
      setClearingData(false)
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
      setError(err instanceof Error ? err.message : 'LLM provider key could not be saved.')
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
        <div className="submission-layout">
          <div className="upload-row">
            <UploadPanel
              onFileSelect={handleFileSelect}
              fileName={fileName}
              submitted={!!submitted}
              loading={submitting}
              label="Upload Application"
              emptyTitle="Drop your application here"
              savedLabel="Application Saved"
              loadingLabel="Updating Excel..."
              buttonIdleLabel="Upload Application"
            />
            <UploadPanel
              onFileSelect={handleTeacherEvaluationSelect}
              fileName={teacherEvaluationFileName}
              submitted={!!teacherEvaluationSubmitted}
              loading={submittingTeacherEvaluation}
              label="Upload Teacher Evaluation"
              emptyTitle="Drop teacher evaluation here"
              savedLabel="Teacher Evaluation Saved"
              loadingLabel="Saving..."
              buttonIdleLabel="Upload Teacher Evaluation"
            />
          </div>
          <div className="panel result-panel output-panel">
            <p className="label">Application Output</p>
            <div className="settings-box">
              <p className="score-label">AI Providers</p>
              {activeTextProvider && (
                <p className="placeholder">
                  Text: {PROVIDER_LABELS[activeTextProvider] ?? activeTextProvider}
                  {' — '}
                  {textProviderConfigured ? '✓ key configured' : '⚠ no key set'}
                </p>
              )}
              {activeVisionProvider && (
                <p className="placeholder">
                  Image reading: {PROVIDER_LABELS[activeVisionProvider] ?? activeVisionProvider}
                  {' — '}
                  {visionProviderConfigured ? '✓ key configured' : '⚠ no key set'}
                </p>
              )}
              <div className="provider-grid">
                <div className="provider-control">
                  <div className="provider-heading">
                    <p className="score-label">Text AI</p>
                  </div>
                  <select
                    className="text-input"
                    value={textProvider}
                    onChange={(event) => setTextProvider(event.target.value)}
                  >
                    {availableProviders.map((name) => (
                      <option key={name} value={name}>
                        {PROVIDER_LABELS[name] ?? name}
                      </option>
                    ))}
                  </select>
                  <div className="settings-row">
                    <input
                      className="text-input"
                      type="password"
                      value={textApiKey}
                      onChange={(event) => setTextApiKey(event.target.value)}
                      placeholder={KEY_PLACEHOLDERS[textProvider] ?? 'Paste API key'}
                      autoComplete="off"
                    />
                    <button
                      className="btn-secondary"
                      type="button"
                      onClick={handleSaveTextApiKey}
                      disabled={savingTextApiKey || !textApiKey.trim()}
                    >
                      {savingTextApiKey ? 'Checking...' : 'Save'}
                    </button>
                  </div>
                </div>
                <div className="provider-control">
                  <div className="provider-heading">
                    <p className="score-label">Image Reading AI</p>
                    <span className="recommended-pill">Recommend ChatGPT</span>
                  </div>
                  <select
                    className="text-input"
                    value={visionProvider}
                    onChange={(event) => setVisionProvider(event.target.value)}
                  >
                    {availableVisionProviders.map((name) => (
                      <option key={name} value={name}>
                        {PROVIDER_LABELS[name] ?? name}
                      </option>
                    ))}
                  </select>
                  <div className="settings-row">
                    <input
                      className="text-input"
                      type="password"
                      value={visionApiKey}
                      onChange={(event) => setVisionApiKey(event.target.value)}
                      placeholder={KEY_PLACEHOLDERS[visionProvider] ?? 'Paste API key'}
                      autoComplete="off"
                    />
                    <button
                      className="btn-secondary"
                      type="button"
                      onClick={handleSaveVisionApiKey}
                      disabled={savingVisionApiKey || !visionApiKey.trim()}
                    >
                      {savingVisionApiKey ? 'Checking...' : 'Save'}
                    </button>
                  </div>
                </div>
              </div>
              {apiKeyMessage && <p className="success-text">{apiKeyMessage}</p>}
            </div>
            {submitting && <p className="placeholder">Processing application…</p>}
            {!submitting && submitted && (
              <div className="score-card">
                <p className="score-label">Excel updated</p>
                <h2>{submitted.applicant_name || submitted.file_name}</h2>
              </div>
            )}
            <a className="btn-secondary" href="http://127.0.0.1:8000/applications.xlsx">
              Open applications.xlsx
            </a>
            <button
              className="btn-danger"
              type="button"
              onClick={handleClearData}
              disabled={clearingData || submitting || submittingTeacherEvaluation}
            >
              {clearingData ? 'Clearing...' : 'Reset Saved Data'}
            </button>
            {clearMessage && <p className="placeholder">{clearMessage}</p>}
            {teacherEvaluationSubmitted && (
              <p className="placeholder">
                Teacher evaluation saved: {teacherEvaluationSubmitted.file_name}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
