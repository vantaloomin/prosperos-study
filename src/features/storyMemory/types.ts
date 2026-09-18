import type { Branch } from '../../types'

export interface Source { id: string; node_id?: string; asset_id?: string; version_id?: string; field?: string; name?: string; edition?: number; title: string; role?: string; text: string; start: number; end: number; sha256: string }
export interface SourcePage { items: Source[]; matches: number; next_offset: number | null; revision: number }
export interface SummaryItem { source_id: string; summary: string; quotes: string[]; topics: string[]; aliases: string[] }
export interface SummaryResult { items: SummaryItem[] }
export interface SummaryJob {
  id: string; status: string; error: string; output: string; attempt: number; result: SummaryResult | null; usage: Record<string, unknown>
  snapshot: { content: string; prompt: { template: string; number: number }; profile: { name: string; config: { model: string } } }
}
export interface SummaryVersion { id: string; job_id: string; node_id: string; branch_id: string; result: SummaryResult; enabled: number; created_at: string }
export interface SummaryRun {
  id: string; snapshot: { content: string }; jobs: SummaryJob[]; current_version: SummaryVersion | null; versions: SummaryVersion[]
}
export interface Preview { preview_hash: string; request_count: number; source_count: number; jobs: { profile_name: string; model: string; estimated_input_tokens: number; prompt_version: number; content: string; instructions: string }[] }
export interface SetupProps { branch: Branch; onStarted: (id: string) => void }
export const working = (job: { status: string }) => ['running', 'queued'].includes(job.status)
