import type { Outcome } from '../mechanics/types'
import type { PrivateContent } from './interpretationTypes'

export interface BackgroundSummary {
  id: string; branch_id: string; head_id: string | null; previous_id: string | null; created_at: string
  origin: string; day: number; character_count: number; hook_count: number
  drives_enabled: boolean; hooks_enabled: boolean
  interpreted: boolean; interpretation_run_id: string | null
}
export interface BackgroundContext { current: string | null; revision: number; history: BackgroundSummary[] }
export interface BackgroundRecord {
  id: string
  snapshot: {
    recipe: { origin: string; day: number; horizon: number }
    day: number; drives_enabled: boolean; hooks_enabled: boolean
    interpretation?: { run_id: string; job_id: string; content: PrivateContent }
    result: {
      algorithm: string; seed: string
      drives: { character: { name: string; version_id: string }; results: Outcome[] }[]
      hooks: { day: number | null; result: Outcome }[]
    }
  }
}
