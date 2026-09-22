import { libraryKind } from './kinds.ts'
import type { AssetContent, AssetKind, AssetVersion } from '../../types'

export interface ImportDraft { part: AssetKind; kind: AssetKind; name: string; content: AssetContent }
export interface ImportAsset {
  label: string; kind: string; uri: string; path?: string; sha256?: string
  status: 'image' | 'reference' | 'missing'; reason: string; width?: number; height?: number
}
export interface ImportPreview {
  id: string; filename: string; source_sha256: string; format: 'card' | 'png-card' | 'markdown' | 'sgc-brain' | 'native-character' | 'lorebook-json' | 'charx' | 'byaf'; card_version: string | null
  source_format?: string; format_label?: string
  assets?: ImportAsset[]
  mapping?: { source: string; target: string; handling: 'mapped' | 'review' | 'reference' }[]
  issues: { path: string; message: string }[]; files: { path: string; characters: number }[]; drafts: ImportDraft[]
  duplicates: ImportDuplicate[]
}
export interface ImportDuplicate { part: AssetKind; version_id: string; asset_id: string; name: string; match: 'exact-source' | 'proposal-content' }
export interface ImportResult { versions: AssetVersion[]; skipped?: { part: AssetKind; duplicates: ImportDuplicate[] }[] }
export interface ImportChoice extends ImportDraft { included: boolean; duplicate_action?: 'skip' | 'new'; target?: AssetVersion; sourceHash?: string | null }

export function importChoices(preview: ImportPreview, target?: AssetVersion): ImportChoice[] {
  return preview.drafts.map((draft) => ({ ...draft, included: true, duplicate_action: 'skip', target: target && libraryKind(draft.kind) === libraryKind(target.kind) ? target : undefined }))
}

export function publicationChoices(choices: ImportChoice[]) {
  return choices.filter((choice) => choice.included).map((choice) => ({ part: choice.part, name: choice.name,
    content: choice.content, target_asset_id: choice.target?.asset_id ?? null, expected_version_id: choice.target?.id ?? null,
    expected_source_hash: choice.sourceHash ?? null, ...(choice.duplicate_action ? { duplicate_action: choice.duplicate_action } : {}) }))
}

export function readImportFile(file: File): Promise<string> {
  if (file.size > 10 * 1024 * 1024) return Promise.reject(new Error('Choose a file no larger than 10 MiB.'))
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onerror = () => reject(new Error('This file could not be read. Choose it again.'))
    reader.onload = () => resolve(String(reader.result).split(',')[1])
    reader.readAsDataURL(file)
  })
}
