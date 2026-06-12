// Field metadata for the editable review form. Each field carries the input
// shape the teacher should get (a bounded score box, a one-liner, a long note,
// or a fixed choice) so the form can render correct controls and validate edits.
export type FieldType = 'score' | 'text' | 'textarea' | 'select'

export interface FieldDef {
  label: string
  key: string
  type: FieldType
  max?: number
  options?: string[]
  /** Long fields span the whole column instead of sharing a row. */
  full?: boolean
  placeholder?: string
}

export interface FieldBlock {
  title: string
  fields: FieldDef[]
}

// Which stored document each editable section was read from — drives the
// "jump to this doc" affordance and the right-pane viewer.
export type DocKind = 'application' | 'teacher'

export const APPLICATION_BLOCKS: FieldBlock[] = [
  {
    title: 'Applicant',
    fields: [
      { label: 'School', key: 'school', type: 'text' },
      { label: 'City', key: 'city', type: 'text' },
      { label: 'Grade', key: 'current_grade', type: 'text' },
      { label: 'Gender', key: 'gender', type: 'select', options: ['', 'Male', 'Female', 'Other'] },
    ],
  },
  {
    title: 'Scores',
    fields: [
      { label: 'Resume', key: 'resume_rating_10', type: 'score', max: 10 },
      { label: 'Cover letter', key: 'cover_letter_rating_10', type: 'score', max: 10 },
      { label: 'STEM statement', key: 'stem_statement_rating_10', type: 'score', max: 10 },
      { label: 'FUS understanding', key: 'fus_understanding_rating', type: 'score', max: 5 },
      { label: 'Transcript vs median', key: 'transcript_relative_to_class_median_5', type: 'score', max: 5 },
      { label: 'Lowest grade', key: 'lowest_grade_in_current_grade', type: 'text' },
    ],
  },
  {
    title: 'Notes',
    fields: [
      { label: 'Cover letter notes', key: 'cover_letter_notes', type: 'textarea', full: true },
      { label: 'STEM statement notes', key: 'stem_statement_notes', type: 'textarea', full: true },
      { label: 'FUS understanding', key: 'fus_understanding_summary', type: 'textarea', full: true },
      { label: 'Features', key: 'features', type: 'textarea', full: true },
      { label: 'Volunteer experience', key: 'volunteer_experience', type: 'textarea', full: true },
      { label: 'Previous research', key: 'previous_research_experience', type: 'textarea', full: true },
      { label: 'Career goals', key: 'career_goals', type: 'textarea', full: true },
      { label: 'Commitment to STEM', key: 'commitment_to_stem', type: 'textarea', full: true },
      { label: 'Application note', key: 'general_application_note', type: 'textarea', full: true },
      { label: 'Sunnybrook form note', key: 'sunnybrook_form_note', type: 'textarea', full: true },
    ],
  },
]

export const TEACHER_BLOCKS: FieldBlock[] = [
  {
    title: 'Scores',
    fields: [
      { label: 'Teacher report', key: 'teacher_report_rating_5', type: 'score', max: 5 },
      { label: 'Total score', key: 'teacher_evaluation_total_score', type: 'text' },
      { label: 'Academic ranking', key: 'academic_ranking', type: 'text' },
    ],
  },
  {
    title: 'Notes',
    fields: [
      { label: 'Teacher comments', key: 'teacher_comments', type: 'textarea', full: true },
      { label: 'Teacher evaluation note', key: 'teacher_evaluation_note', type: 'textarea', full: true },
    ],
  },
]

export const ALL_EDITABLE_KEYS: string[] = [...APPLICATION_BLOCKS, ...TEACHER_BLOCKS]
  .flatMap((block) => block.fields.map((f) => f.key))
