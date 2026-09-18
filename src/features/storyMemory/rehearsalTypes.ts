import type { Source } from './types'

export interface RehearsalBoundary { branch_id: string; head_id: string | null; revision: number; manifest_id: string; version_id: string | null }
export interface RehearsalView { key: string; subject: string; character_id: string | null }
export interface RehearsalCatalogue { boundary: RehearsalBoundary; views: RehearsalView[] }
export interface RehearsalDraft { query: string; views: string[]; include_library: boolean }
export interface RehearsalDecision { id: string; subject: string; stance: string; text: string; sources: Source[] }
export interface RehearsalItem { source: Source; matched: string[]; different_states: boolean; knowledge: { view: string; states: string[]; decision_ids: string[] }[] }
export interface RehearsalReport extends RehearsalCatalogue {
  algorithm: string; query: string; include_library: boolean; source_count: number; items: RehearsalItem[]
  more_matches: boolean; conflicts: RehearsalDecision[]; more_conflicts: boolean
  decisions: RehearsalDecision[]; unavailable_decisions: number
}

export const knowledgeLabels: Record<string, string> = { knows: 'Knows', believes: 'Believes', uncertain: 'Uncertain', unaware: 'Explicitly does not know', unrecorded: 'No recorded grant' }
export const conflictLabels: Record<string, string> = { unresolved: 'Needs review', intentional: 'Intentional ambiguity', resolved: 'Author resolution' }

export function sameRehearsalBoundary(left: RehearsalBoundary, right: RehearsalBoundary) {
  return left.branch_id === right.branch_id && left.head_id === right.head_id && left.revision === right.revision && left.manifest_id === right.manifest_id && left.version_id === right.version_id
}

export function viewpointLabel(view: RehearsalView) {
  return view.subject + (view.character_id ? ' · Character ' + view.character_id.slice(0, 8) : ' · name-only')
}
