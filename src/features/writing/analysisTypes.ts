import type { ProfileConfig } from '../models/types'
import type { StyleContent } from './types'

export type StyleField = Exclude<keyof StyleContent, 'examples'>
export type StylePatch = Partial<Pick<StyleContent, StyleField>>
export const styleLabels: Record<StyleField, string> = { prose: 'Prose preferences', viewpoint: 'Point of view', tense: 'Tense', dialogue: 'Dialogue conventions', rhythm: 'Rhythm', description: 'Descriptive detail', avoid: 'Unwanted habits' }
export interface AnalysisBody { draft_id: string; name: string; source_version_id: string | null; samples: StyleContent['examples']; profile_id: string | null }
export interface AnalysisStart extends AnalysisBody { operation_id: string; preview_hash: string }
export interface AnalysisSnapshot {
  name: string; samples: StyleContent['examples']; instructions: string; content: string
  profile: { name: string; config: ProfileConfig }; input_allowance: number; estimated_input_tokens: number; overhead_margin: number
}
export interface AnalysisPreview { preview_hash: string; request_count: number; snapshot: AnalysisSnapshot; cost: null }
export interface AnalysisSuggestion { field: StyleField; value: string; reason: string; evidence: { sample_id: string; quote: string }[] }
export interface AnalysisJob { id: string; status: string; snapshot: AnalysisSnapshot; output: string; error: string; attempt: number; result: { summary: string; suggestions: AnalysisSuggestion[] } | null }
export interface AnalysisListItem { id: string; name: string; status: string; updated_at: string }
export const analysisWorking = (status?: string) => status === 'queued' || status === 'running'

export function mergeStyleSuggestions(current: StyleContent, changes: StylePatch, expected: StylePatch): StyleContent {
  for (const key of Object.keys(changes) as StyleField[]) {
    if (current[key] !== expected[key]) throw new Error('A selected style field changed in another view. Review its current wording before copying suggestions.')
  }
  return { ...current, ...changes }
}
