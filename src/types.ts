export type AssetKind = 'character' | 'lorebook' | 'persona'
export type Role = 'user' | 'assistant' | 'narrator' | 'ooc'
export interface CharacterGreeting { id: string; label: string; text: string }
export interface OpeningSource { asset_id: string; version_id: string; greeting_id: string }
export interface AssetContent {
  canon_recall?: import('./features/library/canonCueTypes').CanonPolicy
  artwork_sha256?: string | null
  text?: string
  voice?: string
  address?: string
  pronouns?: string
  behavior_rules?: string
  scenario?: string
  example_dialogue?: string
  author_notes?: string
  greetings?: CharacterGreeting[]
  lorebook_versions?: string[]
  lore_definition?: import('./features/library/loreTypes').LoreDefinition
  lore_documents?: Record<string, string>
  [key: string]: unknown
}
export interface AssetVersion {
  restored_at?: string | null
  id: string
  asset_id: string
  number: number
  name: string
  content: AssetContent
  note: string
  created_at: string
  kind: AssetKind
}
export interface Attachment {
  asset_id: string
  version_id: string
  enabled: boolean
  priority: number
}
export interface AttachedAsset extends Attachment {
  version: AssetVersion
  kind: AssetKind
  update_available: boolean
}
export interface StorySummary {
  restored_at?: string | null
  id: string
  title: string
  premise: string
  settings: Record<string, unknown>
  archived: boolean
  revision: number
  manifest_id: string
  updated_at: string
}
export interface BranchSummary {
  id: string
  story_id: string
  name: string
  head_id: string | null
  manifest_id: string
  forked_from: string | null
  fork_node_id: string | null
  revision: number
  created_at: string
}
export interface Story extends StorySummary {
  branches: BranchSummary[]
  attachments: AttachedAsset[]
}
export interface Message {
  id: string
  parent_id: string | null
  role: Role
  text: string
  manifest_id: string
  metadata: Record<string, unknown>
  created_at: string
}
export interface Branch extends BranchSummary {
  messages: Message[]
  attachments: AttachedAsset[]
  mechanics: import('./features/mechanics/types').MechanicsBrief
}
export interface AdoptionTarget {
  story_id: string
  title: string
  expected_revision: number
  manifest_id: string
  old_version: number
  new_version: number
  changed: boolean
  archived: boolean
  changes: AdoptionChange[]
  conflicts: AdoptionConflict[]
}
export interface AdoptionChange {
  asset_id: string; name: string; before_version_id: string | null; after_version_id: string
  old_version: number | null; new_version: number; enabled_before: boolean | null; enabled_after: boolean
  reason: 'selected' | 'dependency'
}
export interface AdoptionConflict {
  asset_id: string; name: string; message: string
  references: { asset_id: string; version_id: string; name: string; number: number; requires_number: number; latest_version_id: string; latest_number: number }[]
}
export interface AdoptionPreview {
  version: AssetVersion
  targets: AdoptionTarget[]
  selected_versions: AssetVersion[]
  versions: AssetVersion[]
  preview_hash: string
  can_apply: boolean
}
export type VersionReference = Pick<AssetVersion, 'id' | 'asset_id' | 'name' | 'number' | 'kind'>
export interface Selection { storyId: string; branchId: string }
