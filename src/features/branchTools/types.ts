import type { BranchCuration } from '../../types'

export interface ComparisonSource { branch_id: string; head_id: string | null; revision: number; name: string; curation: BranchCuration }
export interface SavedComparison { id: string; story_id: string; created_at: string; left: ComparisonSource; right: ComparisonSource }
export interface ComparedPassage {
  node_id: string; original_node_id: string; role: string; text: string; removed: boolean; omitted_text: string | null
  changes: { kind: 'equal' | 'added' | 'removed'; text: string }[]
}
export type DifferenceStatus = 'unchanged' | 'changed' | 'added' | 'removed' | 'omitted' | 'restored'
export interface ComparedRow { index: number; status: DifferenceStatus; left: ComparedPassage | null; right: ComparedPassage | null; diff_mode: 'words' | 'common-edges' }
export interface Comparison extends SavedComparison {
  total: number; counts: Partial<Record<DifferenceStatus, number>>; difference_indices: number[]
  shared_prefix_count: number; shared_prefix_node_id: string | null; shared_source_count: number
  rows: ComparedRow[]; next_offset: number | null
}
export interface SearchRequest { query: string; branch_ids: string[]; include_archived: boolean; include_removed: boolean; offset: number }
export interface SearchOccurrence { branch_id: string; branch_name: string; branch_revision: number; node_id: string; archived: boolean; favorite: boolean }
export interface SearchMatch {
  group_id: string; original_node_id: string; role: string; removed: boolean
  before: string; match: string; after: string; truncated_before: boolean; truncated_after: boolean; occurrences: SearchOccurrence[]
}
export interface SearchResults { story_id: string; query: string; total: number; searched_branches: number; results: SearchMatch[]; next_offset: number | null; scope: string }
export type OpenPassage = (branchId: string, nodeId: string) => void
