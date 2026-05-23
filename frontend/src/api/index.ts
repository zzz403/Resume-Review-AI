import type { Review, ReviewResponse, ExtractResponse } from '../types'

const API_BASE = import.meta.env.VITE_API_URL ?? 'http://localhost:8000'

export async function extractResume(file: File): Promise<ExtractResponse> {
  const form = new FormData()
  form.append('file', file)
  const res = await fetch(`${API_BASE}/extract`, { method: 'POST', body: form })
  if (!res.ok) throw new Error('Failed to extract resume')
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
