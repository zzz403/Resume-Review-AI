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

export interface ApplicationSubmitResponse {
  message: string
  file_name: string
  applicant_name: string
  excel_path: string
}

export interface TeacherEvaluationSubmitResponse {
  message: string
  file_name: string
  saved_path: string
  applicant_name: string
  teacher_report_rating_5: number | string
  academic_ranking: string
}

export interface ClearApplicationDataResponse {
  message: string
  removed_data_files: string[]
  removed_teacher_evaluations: string[]
  excel_path: string
}

export interface AnthropicKeyResponse {
  message: string
  key_preview: string
}
