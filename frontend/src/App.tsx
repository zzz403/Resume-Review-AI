import { useEffect, useState } from 'react'
import { UploadPanel } from './components/UploadPanel'
import { HistoryList } from './components/HistoryList'
import { clearApplicationData, getHistory, getLlmSettings, saveLlmSettings, submitApplication, submitTeacherEvaluation } from './api'
import type { ApplicationSubmitResponse, Review, TeacherEvaluationSubmitResponse } from './types'

const PROVIDER_LABELS: Record<string, string> = {
  anthropic: 'Anthropic (Claude)',
  deepseek: 'DeepSeek',
  gemini: 'Google Gemini',
}

const KEY_PLACEHOLDERS: Record<string, string> = {
  anthropic: 'Paste sk-ant-... key',
  deepseek: 'Paste sk-... key',
  gemini: 'Paste AIza... key',
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
  const [availableProviders, setAvailableProviders] = useState<string[]>(['anthropic', 'deepseek', 'gemini'])
  const [provider, setProvider] = useState('anthropic')
  const [activeProvider, setActiveProvider] = useState<string | null>(null)
  const [providerConfigured, setProviderConfigured] = useState(false)
  const [apiKey, setApiKey] = useState('')
  const [savingApiKey, setSavingApiKey] = useState(false)
  const [apiKeyMessage, setApiKeyMessage] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [view, setView] = useState<'main' | 'history'>('main')

  useEffect(() => {
    getLlmSettings()
      .then((settings) => {
        if (settings.available_providers?.length) setAvailableProviders(settings.available_providers)
        setProvider(settings.provider)
        setActiveProvider(settings.provider)
        setProviderConfigured(settings.configured)
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

  async function handleSaveApiKey() {
    setError(null)
    setApiKeyMessage(null)
    setSavingApiKey(true)
    try {
      const response = await saveLlmSettings(provider, apiKey)
      setApiKey('')
      setActiveProvider(response.provider)
      setProviderConfigured(response.configured)
      setApiKeyMessage(`${response.message} (${response.key_preview})`)
    } catch (err) {
      setApiKeyMessage(null)
      setError(err instanceof Error ? err.message : 'LLM provider key could not be saved.')
    } finally {
      setSavingApiKey(false)
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
              <p className="score-label">AI Provider</p>
              {activeProvider && (
                <p className="placeholder">
                  Active: {PROVIDER_LABELS[activeProvider] ?? activeProvider}
                  {' — '}
                  {providerConfigured ? '✓ key configured' : '⚠ no key set'}
                </p>
              )}
              <div className="settings-row">
                <select
                  className="text-input"
                  value={provider}
                  onChange={(event) => setProvider(event.target.value)}
                >
                  {availableProviders.map((name) => (
                    <option key={name} value={name}>
                      {PROVIDER_LABELS[name] ?? name}
                    </option>
                  ))}
                </select>
              </div>
              <div className="settings-row">
                <input
                  className="text-input"
                  type="password"
                  value={apiKey}
                  onChange={(event) => setApiKey(event.target.value)}
                  placeholder={KEY_PLACEHOLDERS[provider] ?? 'Paste API key'}
                  autoComplete="off"
                />
                <button
                  className="btn-secondary"
                  type="button"
                  onClick={handleSaveApiKey}
                  disabled={savingApiKey || !apiKey.trim()}
                >
                  {savingApiKey ? 'Checking...' : 'Save Key'}
                </button>
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
