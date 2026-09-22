import type { ModelProfile } from '../models/types'
import type { WritingResource } from '../writing/types'

export interface PresetPreview {
  id: string; filename: string; format: string; name: string; source_sha256: string
  instructions: { key: string; label: string; text: string; supported: boolean }[]
  sampling: { source: string; target: string; value: unknown; supported: boolean; note: string }[]
  notes: string[]; source_fields: string[]; parameter_fields: string[]
  duplicates: { version_id: string; asset_id: string; name: string; match: string }[]
}
export interface PresetDraft {
  operation: string; name: string; instructions: string; instruction_keys: string[]; sampling_keys: string[]
  base_profile_id: string | null; expected_profile_version_id: string | null
  target_asset_id: string | null; expected_version_id: string | null; duplicate_action: 'skip' | 'new'; reviewed: boolean
}
export interface ConfigurationProposal { base_name: string; changes: { field: string; before: unknown; after: unknown }[]; config: unknown }
export interface PresetResult { status: 'imported' | 'skipped'; resource?: WritingResource; profile?: ModelProfile; activation?: string }
export const showValue = (value: unknown) => value === null || value === undefined ? 'Default' : JSON.stringify(value)
