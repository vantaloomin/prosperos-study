export interface ContextRequest {
  expected_revision: number
  profile_ids: string[]
  direction?: string
  use_prepared_beat: boolean
  assess_beat: boolean
  assessment_profile_ids: string[]
}
export interface ContextBudget {
  profile_id: string; version_id: string; name: string; version: number
  provider: string; model: string; context_tokens: number; output_tokens: number
  estimated_input_tokens: number; remaining_tokens: number; fits: boolean
}
export interface ContextSection {
  key: string; label: string; description: string; bytes: number
  estimated_tokens: number; source_count: number
}
export interface ContextReport {
  fingerprint: string; branch_id: string; head_id: string | null
  branch_revision: number; story_revision: number; prompt_version: number
  coverage: { messages: number; complete_path: boolean }
  budgets: ContextBudget[]; sections: ContextSection[]
  assessment: { status: 'none' | 'new' | 'saved' | 'completed'; budgets: ContextBudget[]; assessment_id?: string }
}
export interface ContextPage {
  text: string; offset: number; total_characters: number; next_offset: number | null
  sources: string[]; source_count: number
}
