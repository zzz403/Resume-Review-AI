import type {
  ClearApplicationDataResponse,
  ExtractResponse,
  LlmSettings,
  LlmSaveResponse,
  Review,
  ReviewResponse,
  StudentDetail,
  StudentSummary,
} from '../types'

export const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function extractResume(file: File): Promise<ExtractResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/extract`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Failed to extract resume')
  return res.json()
}

export async function getStudents(): Promise<StudentSummary[]> {
  const res = await fetch(`${API_BASE}/students`)
  if (!res.ok) throw new Error('Failed to load students')
  return res.json()
}

export async function createStudent(name: string, email = ''): Promise<StudentSummary> {
  const res = await fetch(`${API_BASE}/students`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, email }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail ?? 'Failed to create student')
  }
  return res.json()
}

export async function getStudent(studentId: string): Promise<StudentDetail> {
  const res = await fetch(`${API_BASE}/students/${studentId}`)
  if (!res.ok) throw new Error('Failed to load student')
  return res.json()
}

export async function deleteStudent(studentId: string): Promise<void> {
  const res = await fetch(`${API_BASE}/students/${studentId}`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to delete student')
}

export async function updateStudent(
  studentId: string,
  updates: Record<string, string | number | boolean | null>,
): Promise<StudentDetail> {
  const res = await fetch(`${API_BASE}/students/${studentId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ updates }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail ?? 'Failed to save changes')
  }
  return res.json()
}

// Direct URLs to the stored source documents — the PDF viewer loads these in an
// iframe; a `v` cache-buster forces a reload after a fresh upload replaces a file.
export function applicationFileUrl(studentId: string, version?: string | number): string {
  const q = version ? `?v=${encodeURIComponent(String(version))}` : ''
  return `${API_BASE}/students/${studentId}/files/application${q}`
}

export function teacherEvaluationFileUrl(studentId: string, version?: string | number): string {
  const q = version ? `?v=${encodeURIComponent(String(version))}` : ''
  return `${API_BASE}/students/${studentId}/files/teacher-evaluation${q}`
}

export async function submitApplication(studentId: string, file: File): Promise<StudentDetail> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/students/${studentId}/application`, { method: 'POST', body: form })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail ?? 'Failed to submit application')
  }
  return res.json()
}

export async function submitTeacherEvaluation(studentId: string, file: File): Promise<StudentDetail> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/students/${studentId}/teacher-evaluation`, { method: 'POST', body: form })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail ?? 'Failed to submit teacher evaluation')
  }
  return res.json()
}

export async function clearApplicationData(): Promise<ClearApplicationDataResponse> {
  const res = await fetch(`${API_BASE}/application-data`, { method: 'DELETE' })
  if (!res.ok) throw new Error('Failed to clear application data')
  return res.json()
}

export async function getLlmSettings(): Promise<LlmSettings> {
  const res = await fetch(`${API_BASE}/settings/llm`)
  if (!res.ok) throw new Error('Failed to load LLM settings')
  return res.json()
}

export async function saveLlmSettings(provider: string, apiKey: string, role: 'text' | 'vision' = 'text'): Promise<LlmSaveResponse> {
  const res = await fetch(`${API_BASE}/settings/llm`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ provider, api_key: apiKey, role }),
  })
  if (!res.ok) {
    const data = await res.json().catch(() => ({}))
    throw new Error(data.detail ?? 'Failed to save LLM settings')
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
