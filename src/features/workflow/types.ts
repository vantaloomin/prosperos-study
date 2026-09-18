import type { SourceMemoryReceipt } from './SourceMemoryCoverage'
import type { ModelProfile } from '../models/types'
import type { BeatCoverage } from '../scenes/types'

export interface TaskSetting { historical?: boolean; key: string; label: string; enabled: boolean; enabled_source?: string; custom_prompt: boolean; pinned: boolean; prompt_id: string; number: number; profile_id: string | null }
export interface Lens { key: string; name?: string; focus: string }
export interface WorkflowStep { enabled?: boolean; key: string; name: string; scope: string; focus?: string; effective_profile_id: string | null; tasks?: TaskSetting[]; lenses?: Lens[] }
export interface Routing {
  story_revision: number; primary_profile_id: string | null; workspace_primary_id: string | null
  effective_primary_id: string | null; step_profiles: Record<string, string>; steps: WorkflowStep[]
}
export interface ReviewStep { key: string; profile_ids: string[]; lenses?: string[] }
export const defaultReviewSteps: ReviewStep[] = ['review-blind', 'review-informed'].map((key) => ({ key, profile_ids: [] }))
export interface ReviewRequest { expected_revision: number; from_node_id?: string | null; through_node_id?: string | null; scene_id?: string; scene_revision?: number; steps: ReviewStep[] }
export interface ReviewScene { id: string; title: string; revision: number }
export interface ReviewHistoryItem { id: string; created_at: string; scene?: { id: string; title: string } | null }
export interface ReviewPreview {
  preview_hash: string; request_count: number; draft_messages: number
  scene?: ReviewScene | null
  jobs: { step: string; name: string; scope: string; profile_name: string; model: string; estimated_input_tokens: number; prompt_version: number; source_count: number; source_memory?: SourceMemoryReceipt | null }[]
}
export interface ReviewFinding { lens?: string; severity: 'hard' | 'soft' | 'cut' | 'hold'; source_id: string; quote: string; explanation: string; suggestion: string }
export interface ReviewJob {
  id: string; step: string; status: string; output: string; error: string; attempt: number; usage: Record<string, unknown>
  snapshot: { prompt_sections?: import('../../components/PromptInstructions').PromptSection[]; source_memory?: SourceMemoryReceipt; profile: ModelProfile; prompt: { id: string; number: number; template: string }; content: string; estimated_input_tokens: number }
  result: { summary: string; findings: ReviewFinding[]; coverage?: BeatCoverage[] } | null
}
export interface ReviewRun {
  id: string; created_at: string; selections: Record<string, string>; jobs: ReviewJob[]
  current_scene_draft?: boolean | null
  snapshot: { prompt_sections?: import('../../components/PromptInstructions').PromptSection[]; branch: { id: string; name: string; revision: number }; story_revision: number; draft_messages: number; from_node_id: string | null; through_node_id: string | null; scene?: ReviewScene }
}
export const working = (job: ReviewJob) => ['queued', 'running'].includes(job.status)
