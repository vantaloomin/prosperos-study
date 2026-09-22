import type { Selection } from '../../types'
import type { SavedComparison } from '../branchTools/types'
import type { TargetSnapshot, TextSelection, TextTarget } from '../textEdits/types'

export type ContextSource = { kind: 'branch'; branch_id: string; expected_revision: number } |
  { kind: 'text'; branch_id: string; expected_revision: number; target: TextTarget; expected_version: string; selection: TextSelection } |
  { kind: 'comparison'; comparison_id: string } | { kind: 'turn'; turn_id: string } |
  { kind: 'comparison-text'; comparison_id: string; side: 'left' | 'right'; node_id: string; selection: TextSelection }
export type ContextTarget = { kind: 'branch' } | { kind: 'text'; snapshot: Omit<TargetSnapshot, 'text'>; selection: TextSelection; comparison?: SavedComparison } |
  { kind: 'comparison'; comparison: SavedComparison } | { kind: 'turn'; turn_id: string }
export interface CompanionContext {
  id: string; story_id: string; story_title: string; thread_id: string; created_at: string; target: ContextTarget; story_revision: number; source_count: number
  branch: { id: string; story_id: string; name: string; revision: number; head_id: string | null }
  model_context: { kind: string; branch: string; branch_revision: number; authority: string }
}
export interface ContextHead { revision: number; context: CompanionContext | null }
export type CompanionFocus = Selection | null
