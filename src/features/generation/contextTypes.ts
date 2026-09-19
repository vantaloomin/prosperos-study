export interface ContextRequest {
  knowledge_subject?: string
  knowledge_character_id?: string
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
  estimated_input_tokens: number; remaining_tokens: number; fits: boolean; overhead_tokens?: number
}
export interface ContextSection {
  key: string; label: string; description: string; bytes: number
  estimated_tokens: number; source_count: number
}
export interface ContextReport {
  writer_recall?: { max_queries: number; max_reads: number; extra_calls_per_candidate: number; scope: string; final_input_pending: boolean; available_groups?: number; semantic_enabled?: boolean; relationship_annotations?: number }
  knowledge_lens?: import('./KnowledgeChoice').KnowledgeReceipt
  fingerprint: string; branch_id: string; head_id: string | null
  branch_revision: number; story_revision: number; prompt_version: number
  coverage: { messages: number; complete_path: boolean; included_messages?: number; recalled_passages?: number; summarized_messages?: number }
  memory?: { algorithm: string; mode: 'long'; plans?: { version: number; available: number; selected_ids: string[]; omitted_ids: string[] }; summary_aids?: { chunk_id: string; version_id: string; summary: string; source_sha256: string }[]; canon?: { collections: { name: string; version_id: string; number: number; chunks: number; selected_chunks: number; stale_cues: number }[] }; selected: { id: string; source_id: string; reason: string }[] }
  budgets: ContextBudget[]; sections: ContextSection[]
  assessment: { status: 'none' | 'new' | 'saved' | 'completed'; budgets: ContextBudget[]; assessment_id?: string }
}
export interface ContextPage {
  text: string; offset: number; total_characters: number; next_offset: number | null
  sources: string[]; source_count: number
}
