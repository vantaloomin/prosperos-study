export interface ContinuityChange {
  id: string; action: 'add' | 'replace' | 'resolve'; target_id: string | null
  kind: 'fact' | 'knowledge' | 'thread'; subject: string; text: string; reason: string
  evidence: { source_id: string; quote: string }[]
}
export interface ContinuityProposal { summary: string; scene_summary: string; summary_quote: string; changes: ContinuityChange[] }
export interface SceneReceipt { branch_id: string; node_id: string; manual_review?: boolean; disabled_steps?: string[]; commit_id?: string; proposal_job_id?: string; selected_ids: string[]; include_summary: boolean }
export interface ContinuityView {
  entries: { id: string; kind: string; subject: string; text: string; status: string; node_id: string; evidence: { source_id: string; quote: string }[] }[]
  commits: { id: string; node_id: string; summary: string; note: string; created_at: string; changes: ContinuityChange[] }[]
}
