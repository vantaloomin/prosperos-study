import type { ModelProfile } from '../models/types'
import type { LoreReceipt } from '../library/LoreReceiptView'

export interface Candidate {
  id: string
  generation_id: string
  profile: ModelProfile
  status: 'queued' | 'running' | 'cleaning' | 'done' | 'error' | 'cancelled' | 'interrupted'
  cleanup?: import('../phrases/cleanupTypes').Cleanup | null
  text_edit?: { id: string; revision: number; text: string; receipt_id: string; attempt: number } | null
  wording_version?: string | null
  output: string
  error: string
  usage: Record<string, unknown> & { writer_recall?: import('./RecallReceipt').RecallReceiptData; continuity_revision?: import('./ContinuityRevision').ContinuityRevisionData }
  attempt: number
  accepted_branch_id: string | null
  accepted_node_id: string | null
  activity?: { started_at: string; first_text_at: string | null; last_event_at: string | null; finished_at: string | null; error_kind: string } | null
}
export interface Generation {
  id: string
  branch_id: string
  stale: boolean
  candidates: Candidate[]
  snapshot: {
    branch: { id: string; story_id: string }
    writer_recall?: { version: number }
    knowledge_lens?: import('./KnowledgeChoice').KnowledgeReceipt
    lore?: LoreReceipt
    opportunity_id: string | null
    content: string
    prompt: { id: string; key: string; number: number; template: string }
    estimated_input_tokens: number
    coverage: { messages: number; complete_path: boolean; included_messages?: number; recalled_passages?: number }
    reviewed_context?: { fingerprint: string; stage: 'writer' | 'before_assessment' }
  }
}
export interface GenerationSummary { id: string; branch_id: string; created_at: string; statuses: Candidate['status'][]; unaccepted: boolean }
export const isWorking = (candidate: Candidate) => ['running', 'queued', 'cleaning'].includes(candidate.status)
export const isUpdating = (candidate: Candidate) => isWorking(candidate) || Boolean(candidate.usage.cleanup_pending)
