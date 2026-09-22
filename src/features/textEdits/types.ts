export type TextTarget = { kind: 'story-brief'; story_id: string } | { kind: 'passage'; story_id: string; branch_id: string; node_id: string } | { kind: 'candidate'; story_id: string; branch_id: string; candidate_id: string } | { kind: 'scene-block'; story_id: string; branch_id: string; scene_id: string; job_id: string; item_id: string } | { kind: 'document'; story_id: string; branch_id: string; purpose: 'composer' | 'author-note' | 'scene-goal' } | { kind: 'library-field' | 'writing-field'; story_id: string; asset_id: string; field: string; item_id?: string } | { kind: 'prompt'; story_id: string; prompt_key: string; prompt_scope: 'story' | 'workspace'; workspace_id?: string }
export interface TargetSnapshot { ref: TextTarget; basis: { revision: number; head_id?: string; document_id?: string; role?: string; removed?: boolean; version_id?: string; asset_kind?: string }; text: string; label: string; version: string; limit: number }
export interface TextSelection { start: number; end: number; text: string }
export interface TextEditSummary { id: string; label: string; status: TextProposal['status']; created_at: string; receipt_id: string | null }
export type EditAction = 'add' | 'insert-before' | 'insert-after' | 'replace' | 'update'
export interface TextProposal { id: string; story_id: string; target: TargetSnapshot; selection: TextSelection; action: EditAction; replacement: string; after_text: string; explanation: string; revision: number; status: 'pending' | 'conflict' | 'applied' | 'dismissed'; created_at: string; undo_of: string | null; receipt: TextReceipt | null }
export interface TextReceipt { id: string; proposal_id: string; story_id: string; before_target: TargetSnapshot; after_target: TargetSnapshot; selection: TextSelection; action: EditAction; replacement: string; explanation: string; created_at: string; undo_of: string | null; result: { branch_id?: string; node_id?: string; preserved_suffix_count?: number; source_branch_id?: string } }
export type EditInitial = { target: TextTarget; rebase?: TextProposal; expectedEdition?: string; expectedVersion?: string; replacement?: string } | { proposalId: string } | { receiptId: string }
export const wholeText = (text: string): TextSelection => ({ start: 0, end: text.length, text })
export function editPreview(text: string, selection: TextSelection, action: EditAction, replacement: string) {
  const start = action === 'insert-after' ? selection.end : selection.start
  const end = action === 'insert-before' ? selection.start : selection.end
  return text.slice(0, start) + replacement + text.slice(end)
}
