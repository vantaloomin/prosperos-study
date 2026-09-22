import type { ActorRequest } from './CharacterDialogue'
import type { SourceMemoryReceipt } from '../workflow/SourceMemoryCoverage'
import type { ModelProfile } from '../models/types'
import type { RevisionPlan, TriageItem, Evidence } from './revisionTypes'
import type { PatchEdit, PatchResolution, PassageCheck, PatchView, patchSteps } from './patchTypes'
import type { ContinuityChange, ContinuityProposal, SceneReceipt } from './continuityTypes'
import type { ChanceBoundary, ChanceSnapshot, SceneChancePlan } from './SceneChance'

export const sceneSteps = [
  { key: 'scene-options', name: 'Options' }, { key: 'scene-beats', name: 'Beat plan' }, { key: 'scene-brief', name: 'Continuity brief' },
  { key: 'scene-draft', name: 'Scene draft' }, { key: 'scene-dialogue', name: 'Dialogue' }, { key: 'scene-coverage', name: 'Beat coverage' },
] as const
export type SceneKey = typeof sceneSteps[number]['key'] | 'scene-triage' | 'scene-verify' | 'scene-continuity' | typeof patchSteps[number]['key']
export interface SceneOption { id: string; title: string; direction: string; opens: string; closes: string }
export interface SceneBeat { id: string; title: string; development: string; decision: string; constraints: string; chance?: ChanceBoundary | null }
export interface BeatPlan { summary: string; beats: SceneBeat[]; ending: string }
export interface BriefFact { source_id: string; quote: string; relevance: string }
export type DraftBlock = { id: string; kind: 'prose'; text: string } | { id: string; kind: 'dialogue'; speaker: string; instruction: string; text?: string | null }
export interface BeatCoverage { beat_id: string; status: 'rendered' | 'compressed' | 'missing' | 'moved'; quotes: string[]; explanation: string }
export interface CoverageIssue { category: string; quote: string; explanation: string }
export interface SceneResult {
  summary: string; options?: SceneOption[]; beats?: SceneBeat[] | BeatCoverage[]; ending?: string; facts?: BriefFact[]; unknowns?: string[]
  blocks?: DraftBlock[]; proposed_facts?: string[]; lines?: { slot_id: string; text: string }[]; issues?: CoverageIssue[]
  approach?: 'patch' | 'redraft'; items?: TriageItem[]; verdict?: string; evidence?: Evidence[]; smallest_fix?: string
  edits?: PatchEdit[]; resolutions?: PatchResolution[]; checks?: PassageCheck[]
  scene_summary?: string; summary_quote?: string; changes?: ContinuityChange[]
}
export interface SceneJob {
  id: string; step: SceneKey; status: string; output: string; error: string; attempt: number; current_inputs: boolean
  usage: Record<string, unknown>; result: SceneResult | null
  snapshot: { prompt_sections?: import('../../components/PromptInstructions').PromptSection[]; dialogue_actors?: ActorRequest[]; source_memory?: SourceMemoryReceipt; profile: ModelProfile; prompt: { id: string; number: number; template: string }; content: string; estimated_input_tokens: number; item_id?: string | null }
}
export interface SceneRun {
  text_targets?: import('../textEdits/types').TargetSnapshot[]
  id: string; branch_id: string; title: string; revision: number; stale: boolean; next_step: SceneKey | null; created_at: string
  snapshot: ChanceSnapshot & { workflow_version?: number; branch: { name: string; revision: number; story_id: string }; direction: string; propose_options: boolean; dialogue_split?: boolean; disabled_steps?: string[] }
  state: { selections: Record<string, string>; option_id: string | null; beat_edit: BeatPlan | null; gate_a: { approved_at: string; note: string; mechanics?: SceneChancePlan } | null; verifications: Record<string, string>; gate_b: { approved_at: string; note: string; package: string; items: TriageItem[] } | null; patch_round: number; repair_selections: Record<string, string>; accepted: SceneReceipt | null; draft_edits?: Record<string, { text: string; receipt_id: string; job_id: string }> }
  manual_acceptance?: { text: string; source: string; disabled_steps: string[] } | null
  revision_plan: RevisionPlan | null
  patch: PatchView | null
  continuity_proposal: ContinuityProposal | null
  jobs: SceneJob[]; plan: BeatPlan | null
  draft: { blocks: DraftBlock[]; text: string | null; complete: boolean; proposed_facts: string[] } | null; coverage_passes: boolean
  decisions: { id: string; kind: string; revision: number; created_at: string; payload: Record<string, unknown> }[]
}
export interface StagePreview {
  preview_hash: string; request_count: number
  jobs: { dialogue_actors?: ActorRequest[]; step: string; name: string; profile_name: string; model: string; estimated_input_tokens: number; prompt_version: number; source_count: number; source_memory?: SourceMemoryReceipt | null; writing: import('../collaborator/workTypes').WritingLabels; instructions: string; content: string | null; input_allowance: number; output_limit: number; cost: null }[]
}
export const sceneWorking = (job: SceneJob) => ['queued', 'running'].includes(job.status)
export const planningStep = (key: SceneKey) => ['scene-options', 'scene-beats', 'scene-brief'].includes(key)
export const sceneWritingPurpose = (key: SceneKey) => ['scene-draft', 'scene-dialogue'].includes(key) ? 'draft' : ['scene-patch', 'scene-dialogue-patch'].includes(key) ? 'revise' : undefined
export const consolidatedScene = (run: SceneRun) => (run.snapshot.workflow_version ?? 1) >= 2
export const enabledSceneSteps = (run: SceneRun) => sceneSteps.filter((step) => !(consolidatedScene(run) && ['scene-brief', 'scene-coverage'].includes(step.key)) && !run.snapshot.disabled_steps?.includes(step.key) && (step.key !== 'scene-options' || run.snapshot.propose_options) && (step.key !== 'scene-dialogue' || run.snapshot.dialogue_split))
