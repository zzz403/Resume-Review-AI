export interface Review {
  id: string
  resume_text: string
  score: number | null
  feedback: string
  created_at: string
}

export interface ReviewResponse {
  score: number | null
  feedback: string
}
