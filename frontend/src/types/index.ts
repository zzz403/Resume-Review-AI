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

export interface ExtractResponse {
  text: string
}

export interface StudentSummary {
  student_id: string
  applicant_name: string
  email: string
  school: string
  current_grade: string | number
  has_application: boolean
  has_teacher_evaluation: boolean
  resume_rating_10: string | number
  cover_letter_rating_10: string | number
  stem_statement_rating_10: string | number
  teacher_report_rating_5: string | number
  academic_ranking: string
  created_at: string
  submitted_at: string
}

export type StudentDetail = Record<string, string | number | boolean | null>

export interface ClearApplicationDataResponse {
  message: string
  removed_data_files: string[]
  removed_teacher_evaluations: string[]
  excel_path: string
}

export interface LlmSettings {
  provider: string
  configured: boolean
  text_provider: string
  text_configured: boolean
  vision_provider: string
  vision_configured: boolean
  available_providers: string[]
  available_vision_providers: string[]
}

export interface LlmSaveResponse {
  provider: string
  role: 'text' | 'vision'
  configured: boolean
  message: string
  key_preview: string
}
