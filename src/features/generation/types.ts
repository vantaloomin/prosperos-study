import type { ModelProfile } from '../models/types'
import type { LoreReceipt } from '../library/LoreReceiptView'

export interface Candidate {
  id: string
  generation_id: string
  profile: ModelProfile
  status: 'queued' | 'running' | 'done' | 'error' | 'cancelled' | 'interrupted'
  output: string
  error: string
  usage: Record<string, unknown>
  attempt: number
  accepted_branch_id: string | null
  accepted_node_id: string | null
}
export interface Generation {
  id: string
  branch_id: string
  stale: boolean
  candidates: Candidate[]
  snapshot: {
    lore?: LoreReceipt
    opportunity_id: string | null
    content: string
    prompt: { id: string; key: string; number: number; template: string }
    estimated_input_tokens: number
    coverage: { messages: number; complete_path: boolean }
  }
}
export interface GenerationSummary { id: string; branch_id: string; created_at: string }
export const isWorking = (candidate: Candidate) => candidate.status === 'running' || candidate.status === 'queued'
