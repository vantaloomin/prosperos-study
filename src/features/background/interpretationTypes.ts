export interface PrivateBasis { source_id: string; quote: string }
export interface PrivateDrive { target_id: string; motive: string; concealment: string; expression: string; basis: PrivateBasis[] }
export interface PrivateHook { target_id: string; event: string; foreshadowing: string; conditions: string; basis: PrivateBasis[] }
export interface PrivateContent { drives: PrivateDrive[]; hooks: PrivateHook[] }
export interface PrivateTargets {
  drives: { id: string; character: { name: string } }[]
  hooks: { id: string; day: number | null }[]
}
export interface PrivateJob {
  id: string; status: string; attempt: number; error: string; selected_state_id: string | null
  profile_name: string; model: string; prompt_version: number; estimated_input_tokens: number
  output?: string; result?: PrivateContent | null; usage?: Record<string, unknown>
  snapshot?: { prompt: { template: string }; content: string }
  targets?: PrivateTargets
}
export interface PrivateRun { id: string; branch_id: string; stale: boolean; background_state_id: string; jobs: PrivateJob[] }
export interface PrivatePreview {
  preview_hash: string; request_count: number; target_counts: { drives: number; hooks: number }
  jobs: { profile_name: string; model: string; prompt_version: number; estimated_input_tokens: number }[]
}
export const privateWorking = (job: PrivateJob) => ['queued', 'running'].includes(job.status)
