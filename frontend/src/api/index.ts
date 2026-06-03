import type {
  ApplicationSubmitResponse,
  AnthropicKeyResponse,
  ClearApplicationDataResponse,
  ExtractResponse,
  Review,
  ReviewResponse,
  TeacherEvaluationSubmitResponse,
} from '../types'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function extractResume(file: File): Promise<ExtractResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/extract`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Failed to extract resume')
  return res.json()
}

export async function submitApplication(file: File): Promise<ApplicationSubmitResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/applications`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Failed to submit application')
  return res.json()
}

export async function submitTeacherEvaluation(file: File): Promise<TeacherEvaluationSubmitResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/teacher-evaluations`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Failed to submit teacher evaluation')
  return res.json()
}

export async function clearApplicationData(): Promise<ClearApplicationDataResponse> {
  const res = await fetch(`${API_BASE}/application-data`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to clear application data')
  return res.json()
}

export async function saveAnthropicKey(apiKey: string): Promise<AnthropicKeyResponse> {
  const res = await fetch(`${API_BASE}/settings/anthropic-key`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ api_key: apiKey }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail ?? 'Failed to save Anthropic API key')
  }
  return res.json()
}

export async function submitResume(resumeText: string): Promise<ReviewResponse> {
  const res = await fetch(`${API_BASE}/review`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ resume_text: resumeText }),
  })
  if (!res.ok) throw new Error('Review request failed')
  return res.json()
}

export async function getHistory(): Promise<Review[]> {
  const res = await fetch(`${API_BASE}/history`)
  if (!res.ok) throw new Error('Failed to fetch history')
  return res.json()
}
