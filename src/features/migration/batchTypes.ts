import type { Selection } from '../../types'
import type { ImportResult } from '../library/importTypes'

export type BatchKind = 'library' | 'transcript' | 'preset' | 'archive' | 'writing-bundle'
export type BatchStatus = 'choose' | 'preparing' | 'preparation-error' | 'review' | 'publishing' | 'complete' | 'omitted' | 'rejected'
export interface BatchMatch { item_id: string; filename: string; kind: BatchKind; parts: string[]; match: string }
export interface BatchOutcome extends ImportResult {
  status?: string; story_id?: string; branch_id?: string; story_ids?: string[]; selection?: Selection
  selected_messages?: number; resource?: { name: string; number: number }; resources?: { name: string; number: number }[]
  profile?: { name: string }; activation?: string
}
export interface BatchItem {
  id: string; batch_id: string; filename: string; source_sha256: string; position: number; kind: BatchKind | ''; import_id: string | null
  status: BatchStatus; revision: number; error: string; candidates: Partial<Record<BatchKind, { filename: string; label: string; proposals: Record<string, string> }>>
  batch_duplicates: BatchMatch[]; prior_duplicates: BatchMatch[]; result: BatchOutcome | null
}
export interface MigrationBatch { id: string; created_at: string; items: BatchItem[] }
export const batchKindLabels: Record<BatchKind, string> = { library: 'Character / Canon', transcript: 'Transcript → new Story', preset: 'Generation preset → recipe', archive: 'Private Study archive', 'writing-bundle': 'Native writing bundle' }
export const batchStatusLabels: Record<BatchStatus, string> = { choose: 'Choose interpretation', preparing: 'Preparation interrupted', 'preparation-error': 'Preparation needs attention', review: 'Ready to review', publishing: 'Recover saved publication', complete: 'Result saved', omitted: 'Omitted by you', rejected: 'Rejected file' }
export type BatchPublisher = (choices: object) => Promise<unknown>
