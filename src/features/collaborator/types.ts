import type { BranchSummary } from '../../types'
import type { ModelProfile } from '../models/types'
import type { CompanionContext } from './contextTypes'
import type { CompanionEditResult, CompanionWork, WritingLabels } from './workTypes'

export interface SideThread { id: string; name: string; story_id: string; turns: SideTurn[]; curation?: { archived: boolean; revision: number } }
export interface ConversationMatch { kind: 'name' | 'question' | 'reply'; turn_id: string | null; reply_id: string | null; before: string; match: string; after: string; truncated_before: boolean; truncated_after: boolean }
export interface ConversationLocation { turnId: string; replyId: string | null }
export interface SideTurn {
  id: string; thread_id: string; question: string; selected_reply_id: string | null; source_count: number
  snapshot: { branch: BranchSummary; story_revision: number; disclosure: string; max_reads: number; pinned_context?: CompanionContext; side_work?: CompanionWork & { writing: WritingLabels }; retrieval?: { version: number; input_allowance: number } }
  replies: SideReply[]
}
export interface SideReply {
  id: string; profile: ModelProfile; status: string; output: string; error: string
  usage: Record<string, unknown>[]; coverage: string[]
  edit?: CompanionEditResult | null
}
export interface Source { id: string; title: string; text: string }
export const activeReply = (reply: SideReply) => reply.status === 'running' || reply.status === 'queued'
