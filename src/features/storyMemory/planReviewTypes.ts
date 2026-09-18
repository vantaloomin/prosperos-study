import type { ContinuityChange } from '../scenes/continuityTypes'
import type { ReviewJob } from '../workflow/types'

export interface PlanReviewPreview {
  preview_hash: string; request_count: number; remaining_passages: number; omitted_plans: number
  passages: { id: string; title: string; text: string }[]
  jobs: { profile_name: string; model: string; prompt_version: number; estimated_input_tokens: number }[]
}
export interface PlanReviewJob extends Omit<ReviewJob, 'result'> {
  result: { summary: string; scene_summary: string; changes: ContinuityChange[] } | null
}
export interface PlanReviewRun {
  id: string; jobs: PlanReviewJob[]
  snapshot: { branch: { id: string; revision: number }; remaining_passages: number }
}
