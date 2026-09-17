import type { AssetVersion } from '../../types'
import type { AssetDraft } from '../library/versionChanges'

export type AuthoringStep = 'authoring-draft' | 'authoring-critique' | 'authoring-tighten'
export const actions: Record<AuthoringStep, string> = { 'authoring-draft': 'Draft', 'authoring-critique': 'Critique', 'authoring-tighten': 'Tighten' }
export interface Target { key: string; label: string; text: string }
export interface EditorProps { draft: AssetDraft; draftId: string; asset?: AssetVersion; onChange: (draft: AssetDraft) => void }
export interface RequestBody {
  source_version_id?: string; draft_id: string; kind: string; name: string; target_key: string; target_label: string
  text: string; context: Record<string, string>; direction: string; step: AuthoringStep; profile_ids: string[]
}
export interface Preview {
  preview_hash: string; request_count: number
  jobs: { profile_name: string; model: string; provider: string; prompt_version: number; estimated_input_tokens: number; content: string; prompt: string }[]
}
export interface Proposal { summary: string; proposal: string | null; findings: { quote: string; explanation: string; suggestion: string }[] }
export interface Job {
  id: string; status: string; error: string; output: string; attempt: number; result: Proposal | null; usage: Record<string, unknown>
  snapshot: { step: AuthoringStep; content: string; prompt: { template: string; number: number }; profile: { name: string; config: { model: string } } }
}
export interface RunSummary { id: string; name: string; target_key: string; target_label: string; step: AuthoringStep; asset_id: string | null; source_version_id: string | null; created_at: string }
export interface Run extends RunSummary { snapshot: { kind: string; name: string; draft_id: string; target_key: string; step: AuthoringStep; content: string }; jobs: Job[] }
export interface FrozenContent { target: Target; supporting_fields: Record<string, string>; direction: string }
export const working = (job: { status: string }) => ['running', 'queued'].includes(job.status)
