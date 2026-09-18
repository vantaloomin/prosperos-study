import type { Preview } from './types'

export interface MaintenanceSettings { enabled: boolean; batch_size: number; max_batches: number }
export const defaultMaintenance: MaintenanceSettings = { enabled: false, batch_size: 4, max_batches: 1 }
export interface MaintenanceStatus {
  settings: MaintenanceSettings; active: boolean; waiting_contributions: number
  wakeup: { revision: number; status: string; error: string; allowance: number } | null
}
export interface BackfillPreview { preview_hash: string; eligible_count: number; selected_count: number; covered_count: number; batch_count: number; request_count: number; batches: Preview[] }
export interface BatchSummary { id: string; kind: string; status: string; error: string; created_at: string }
export interface Batch extends BatchSummary {
  snapshot: { request_count: number; selected_count: number; eligible_count: number }
  runs: { id: string; run_id: string; ordinal: number }[]
  requests: { id: string; run_id: string; status: string; error: string; profile_name: string }[]
}
export const batchWorking = (status: string) => ['queued', 'running'].includes(status)
