export interface LoreEntry {
  id: string; title: string; text: string; enabled: boolean; kind: 'required' | 'flavor'
  activation: 'always' | 'keywords'; keywords: string[]; match: 'any' | 'all'
  secondary: string[]; secondary_mode: 'none' | 'require' | 'exclude'; case_sensitive: boolean; whole_words: boolean
  placement: 'header' | 'recent' | 'tail'; priority: number; minimum_beats: number; sticky_beats: number
  cooldown_beats: number; chance_enabled: boolean; chance: number
}
export interface LoreDefinition { schema_version: 1; scan_messages: number; flavor_budget_tokens: number; entries: LoreEntry[] }
export const emptyLore: LoreDefinition = { schema_version: 1, scan_messages: 12, flavor_budget_tokens: 1200, entries: [] }
export function newEntry(): LoreEntry {
  return { id: crypto.randomUUID(), title: 'Untitled entry', text: '', enabled: true, kind: 'required', activation: 'always',
    keywords: [], match: 'any', secondary: [], secondary_mode: 'none', case_sensitive: false, whole_words: true,
    placement: 'recent', priority: 0, minimum_beats: 0, sticky_beats: 0, cooldown_beats: 0, chance_enabled: false, chance: 100 }
}
export interface LoreAudit { entry_id: string; title: string; kind: string; included: boolean; reason: string; estimated_tokens: number; roll: number | null; matched: { primary: string[]; secondary: string[] } }
export interface LoreScan {
  isolated: boolean; notice: string; entries: LoreAudit[]; sources: { id: string; title: string; text: string; placement: string }[]
  budgets: { flavor_budget_tokens: number; flavor_used_tokens: number; required_tokens: number; scanned_messages: number }[]
  draws: unknown[]; after: { clock: number }; timeline: LoreScan[]
}
export interface EntryFile {
  entry_id: string; title: string; version_id: string; file_path: string; markdown: string | null
  sha256: string | null; published_sha256: string; missing: boolean; changed: boolean
  snapshot_hash: string | null; snapshot_needs_recovery: boolean; retained_file?: string | null
}
