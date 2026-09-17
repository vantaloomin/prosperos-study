import type { DraftBlock } from './types'

export const patchSteps = [
  { key: 'scene-patch', name: 'Prose patch' },
  { key: 'scene-dialogue-patch', name: 'Dialogue patch' },
  { key: 'scene-patch-check', name: 'Changed-passage check' },
] as const
export interface PatchEdit {
  block_id: string; operation: string; before: string; after: string; anchor_id: string | null
  speaker: string; item_ids: string[]; reason: string
}
export interface PatchResolution { item_id: string; status: string; reason: string }
export interface PassageCheck { change_id: string; status: string; quotes: string[]; reason: string }
export interface PatchView {
  blocks: DraftBlock[]; text: string; changes: (PatchEdit & { id: string; neighbors: DraftBlock[] })[]
  resolutions: PatchResolution[]; complete: boolean; blocked: boolean; checked: boolean; no_changes_required: boolean
  check: { summary: string; checks: PassageCheck[]; resolutions: PatchResolution[] } | null
}
