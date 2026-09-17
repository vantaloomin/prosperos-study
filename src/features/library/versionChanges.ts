import type { AssetContent, AssetKind, AssetVersion } from '../../types'

export interface AssetDraft { kind: AssetKind; name: string; content: AssetContent; note: string; kind_drafts?: Partial<Record<AssetKind, AssetContent>>; assistance_id?: string; source_hash?: string | null; entry_hashes?: Record<string, string> }
export interface FieldChange { key: string; label: string; before: unknown; after: unknown }

export function versionDraft(version?: AssetVersion, initialKind: AssetKind = 'character'): AssetDraft {
  return { kind: version?.kind ?? initialKind, name: version?.name ?? '', content: structuredClone(version?.content ?? {}), note: '' }
}

export function changeAssetKind(draft: AssetDraft, kind: AssetKind): AssetDraft {
  const kind_drafts = { ...draft.kind_drafts, [draft.kind]: draft.content }
  return { ...draft, kind, kind_drafts, content: kind_drafts[kind] ?? { text: draft.content.text ?? '' } }
}

export function migrateAssetDraft(saved: AssetDraft & { text?: string; voice?: string }, asset?: AssetVersion): AssetDraft {
  if (saved.content) return saved
  return { kind: saved.kind, name: saved.name, note: saved.note,
    content: { ...asset?.content, text: saved.text ?? '', voice: saved.voice ?? '' } }
}

function canonical(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonical)
  if (value && typeof value === 'object') return Object.fromEntries(Object.entries(value).sort(([a], [b]) => a.localeCompare(b)).map(([key, item]) => [key, canonical(item)]))
  return value
}

const labels: Record<string, string> = { artwork_sha256: 'Artwork', text: 'Details', voice: 'Voice & manner', address: 'Form of address', pronouns: 'Pronouns', lorebook_versions: 'Linked Canon collections',
  behavior_rules: 'Behavior & boundaries', scenario: 'Scenario', example_dialogue: 'Example dialogue', author_notes: 'Editor notes', greetings: 'Opening greetings', lore_definition: 'Lore entries and rules', lore_documents: 'Entry Markdown sources' }

export function versionChanges(before: AssetVersion | undefined, after: AssetVersion): FieldChange[] {
  const changes: FieldChange[] = [{ key: 'name', label: 'Name', before: before?.name, after: after.name }]
  for (const key of new Set([...Object.keys(before?.content ?? {}), ...Object.keys(after.content)])) {
    changes.push({ key, label: labels[key] ?? key, before: before?.content[key], after: after.content[key] })
  }
  return changes.filter((change) => JSON.stringify(canonical(change.before)) !== JSON.stringify(canonical(change.after)))
}
