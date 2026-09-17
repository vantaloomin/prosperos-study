import type { BranchSummary } from '../../types'
import type { ModelProfile } from '../models/types'

export interface SideThread { id: string; name: string; story_id: string; turns: SideTurn[] }
export interface SideTurn {
  id: string; question: string; selected_reply_id: string | null; source_count: number
  snapshot: { branch: BranchSummary; story_revision: number; disclosure: string; max_reads: number }
  replies: SideReply[]
}
export interface SideReply {
  id: string; profile: ModelProfile; status: string; output: string; error: string
  usage: Record<string, unknown>[]; coverage: string[]
}
export interface Source { id: string; title: string; text: string }
export const activeReply = (reply: SideReply) => reply.status === 'running' || reply.status === 'queued'
