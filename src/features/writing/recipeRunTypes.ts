import type { Beat, Opportunity, RngSettings } from '../mechanics/types'
import type { ModelProfile } from '../models/types'
import type { EditAction, TargetSnapshot, TextProposal, TextSelection } from '../textEdits/types'
import type { ReviewFinding, ReviewStep } from '../workflow/types'
import type { SourceMemoryReceipt } from '../workflow/SourceMemoryCoverage'
import type { RecipeContent, WritingChoices, WritingResource } from './types'

export type RecipeTask = 'writer' | 'review' | 'revision'
export const emptyRecipeBeat: Beat = { label: '', completed: true, waiting_for_player: false, protected: false, resolves_event: false, new_scene: false, family: 'narrative-push', attempt: null, extras: [] }
export interface RecipeSelection { target: TargetSnapshot; selection: TextSelection; action: EditAction }
export interface RecipeRunChoices {
  direction: string; writing: WritingChoices; profiles: Partial<Record<RecipeTask, string>>
  task_switches: Record<string, boolean>; review_lenses: string[] | null; randomness: RngSettings | null; beat: Beat | null
}
export interface RecipeRunBody extends RecipeRunChoices {
  expected_revision: number; target: TargetSnapshot['ref']; expected_version: string; selection: TextSelection; action: EditAction
}
export interface RecipeGuidance {
  style: WritingResource | null; recipe: WritingResource; resolved_recipe: RecipeContent; guidance: string
}
export interface RecipeSwitches {
  workspace_disabled: string[]; story_disabled: string[]; recipe_disabled: string[]; run_switches: Record<string, boolean>; effective_disabled: string[]
}
export interface RecipeRequest {
  step: string; task: RecipeTask; scope: string; profile: ModelProfile; profile_source: string
  instructions: string; task_instructions: string; reader: ReviewStep | null; content: string | null
  input_allowance: number; estimated_input_tokens: number | null; source_memory?: SourceMemoryReceipt | null
  output_limit?: number; exact?: boolean; awaiting?: string | null; overhead_margin?: number
}
export interface RecipePlanStage { task: RecipeTask; skipped: boolean; reason: string; requests: RecipeRequest[] }
export interface RecipeChanceSpec { applicable: boolean; source: string; settings: RngSettings; beat: Beat | null; tables: Record<string, unknown>; notice: string }
export interface RecipePlanPreview extends RecipeSelection {
  preview_hash: string; writing: RecipeGuidance; switches: RecipeSwitches; plan: RecipePlanStage[]
  chance: RecipeChanceSpec; maximum_calls: number; provider_cost: null; notice: string
}
export interface RecipeStepPreview { stage: number; jobs: RecipeRequest[]; revision: number; preview_hash: string; request_count: number; provider_cost: null }
export interface RecipeTextResult { replacement: string; explanation: string; source_ids: string[] }
export interface RecipeReviewResult { summary: string; findings: ReviewFinding[]; coverage?: unknown[] }
export interface RecipeJob {
  id: string; stage: number; step: string; status: string; output: string; error: string; attempt: number
  snapshot: RecipeRequest; result: RecipeTextResult | RecipeReviewResult | null; usage: Record<string, unknown>
}
export interface RecipeRun {
  id: string; branch_id: string; story_id: string; revision: number; created_at: string; target: TargetSnapshot
  chance: Opportunity['snapshot'] | null; proposal_id: string | null; proposals: TextProposal[]; jobs: RecipeJob[]
  snapshot: RecipeSelection & { direction: string; branch: { id: string; name: string }; guidance: RecipeGuidance; switches: RecipeSwitches;
    chance: RecipeChanceSpec; plan: (Omit<RecipePlanStage, 'requests'> & { templates: RecipeRequest[] })[] }
  progress: { status: 'ready' | 'running' | 'needs-attention' | 'complete'; stage: number | null }
}
export interface RecipeHistoryItem { id: string; created_at: string; revision: number; name: string; status: RecipeRun['progress']['status'] }
export const recipeStatus = { ready: 'Ready for your next step', running: 'Working', 'needs-attention': 'Needs your attention', complete: 'Complete' }
export const activeRecipeJob = (status: string) => status === 'queued' || status === 'running'
