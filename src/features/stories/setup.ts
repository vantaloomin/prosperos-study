import type { AssetVersion, OpeningSource } from '../../types'
import type { ProfileList } from '../models/types'

export const setupSteps = ['Experience', 'Writer', 'Story', 'People', 'Assistance', 'Begin']
export const experiences = [
  { id: 'directed', name: 'Write a story', description: 'Guide the cast and the direction. Work with your writing partner on the next passage.' },
  { id: 'scene', name: 'Build a scene', description: 'Plan beats, draft, invite specialist reviews and accept a checked scene when it is ready.' },
  { id: 'roleplay', name: 'Inhabit a character', description: 'You choose your character’s actions. Your writing partner describes the world and everyone around you.' },
] as const
export const agencyOptions = [
  ['user', 'Keep my character’s choices and inner life mine'],
  ['shared', 'Let the writer describe my character too'],
] as const
export interface SetupAsset { asset_id: string; version_id: string; name: string; kind: string; number: number }
export interface WritingPreferences {
  experience: string; genre: string; tone: string; persona: string; pov: string; tense: string; response_length: string; player_agency: string
}
export interface StoryStart {
  operation_id: string; title: string; premise: string; opening_text: string
  opening_source?: OpeningSource | null
  settings: Record<string, unknown>; attachments: { asset_id: string; version_id: string }[]
}
export interface SetupDraft extends WritingPreferences {
  schema: number; step: number; furthestStep: number; title: string; premise: string; opening: string; primary_profile_id: string
  randomness: string; assets: SetupAsset[]; legacyAssets: string[]; pending: StoryStart | null
  opening_source: OpeningSource | null
}
const legacyPreferences: WritingPreferences = { experience: 'roleplay', genre: '', tone: '', persona: '', pov: 'second person', tense: 'present', response_length: 'A few paragraphs', player_agency: 'user' }
export const preferenceDefaults: WritingPreferences = { ...legacyPreferences, experience: 'directed', pov: 'third person', tense: 'past', player_agency: 'shared' }
export const experienceChange = (experience: string): Partial<WritingPreferences> => ({ experience, ...(experience === 'roleplay' ? { player_agency: 'user' } : {}) })
export const freshSetup = (): SetupDraft => ({ ...preferenceDefaults, schema: 2, step: 0, furthestStep: 0, title: '', premise: '', opening: '', opening_source: null, primary_profile_id: '', randomness: 'off', assets: [], legacyAssets: [], pending: null })
export const pinAsset = (asset: AssetVersion): SetupAsset => ({ asset_id: asset.asset_id, version_id: asset.id, name: asset.name, kind: asset.kind, number: asset.number })

function isAsset(value: unknown): value is SetupAsset {
  if (!value || typeof value !== 'object') return false
  return ['asset_id', 'version_id', 'name', 'kind'].every((key) => typeof (value as Record<string, unknown>)[key] === 'string') && typeof (value as SetupAsset).number === 'number'
}

export function restoreSetup(value: unknown): SetupDraft {
  const base = freshSetup()
  if (!value || typeof value !== 'object') return base
  const saved = value as Record<string, unknown>
  const strings = Object.keys(base).filter((key) => typeof base[key as keyof SetupDraft] === 'string' && typeof saved[key] === 'string')
  const draft = { ...base, ...legacyPreferences, ...Object.fromEntries(strings.map((key) => [key, saved[key]])) }
  draft.step = setupStep(saved.step)
  draft.assets = Array.isArray(saved.assets) ? saved.assets.filter(isAsset) : []
  draft.legacyAssets = legacySelections(saved)
  draft.pending = pendingStart(saved.pending)
  draft.opening_source = restoreOpeningSource(saved.opening_source)
  if (saved.schema !== 2) draft.step = 2
  if (draft.pending) draft.step = 5
  draft.furthestStep = Math.max(draft.step, setupStep(saved.furthestStep))
  return normalizeChoices(draft)
}

function setupStep(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? Math.max(0, Math.min(5, Math.floor(value))) : 0
}

function normalizeChoices(draft: SetupDraft): SetupDraft {
  return { ...draft, experience: ['roleplay', 'directed', 'scene'].includes(draft.experience) ? draft.experience : preferenceDefaults.experience,
    player_agency: ['user', 'shared'].includes(draft.player_agency) ? draft.player_agency : preferenceDefaults.player_agency,
    randomness: ['off', 'quiet', 'balanced'].includes(draft.randomness) ? draft.randomness : 'off' }
}

function legacySelections(saved: Record<string, unknown>): string[] {
  const values = saved.schema === 2 ? saved.legacyAssets : saved.assets
  return Array.isArray(values) ? values.filter((value): value is string => typeof value === 'string') : []
}

function pendingStart(value: unknown): StoryStart | null {
  if (!value || typeof value !== 'object') return null
  const item = value as StoryStart
  return typeof item.operation_id === 'string' && typeof item.title === 'string' && Array.isArray(item.attachments) ? item : null
}

export function selectedAssets(draft: SetupDraft, library: AssetVersion[]): SetupAsset[] {
  const selected = new Map(draft.assets.map((asset) => [asset.asset_id, asset]))
  for (const asset of library) if (draft.legacyAssets.includes(asset.asset_id) && !selected.has(asset.asset_id)) selected.set(asset.asset_id, pinAsset(asset))
  return [...selected.values()]
}

export function writingPreferences(value: Record<string, unknown>): WritingPreferences {
  return Object.fromEntries(Object.entries(legacyPreferences).map(([key, fallback]) => [key, typeof value[key] === 'string' ? value[key] : fallback])) as unknown as WritingPreferences
}

export function storyStart(draft: SetupDraft, profiles: ProfileList, library: AssetVersion[], operation: string): StoryStart {
  if (draft.legacyAssets.some((id) => !library.some((asset) => asset.asset_id === id))) throw new Error('A Library choice from your previous setup is unavailable. Review People before starting.')
  if (draft.primary_profile_id && !profiles.profiles.some((profile) => profile.profile_id === draft.primary_profile_id)) throw new Error('Your selected writing profile is unavailable. Choose a profile again in Writer.')
  if (!openingSourceAttached(draft.opening_source, selectedAssets(draft, library))) throw new Error('Your greeting source no longer matches the selected character version. Review the opening in People.')
  const presets: Record<string, { enabled: boolean; chance: number; cooldown: number }> = {
    off: { enabled: false, chance: 15, cooldown: 3 }, quiet: { enabled: true, chance: 10, cooldown: 4 }, balanced: { enabled: true, chance: 15, cooldown: 3 },
  }
  return { operation_id: operation, title: draft.title.trim(), premise: draft.premise, opening_text: draft.opening,
    ...(draft.opening_source ? { opening_source: draft.opening_source } : {}),
    settings: { ...writingPreferences(draft as unknown as Record<string, unknown>), primary_profile_id: draft.primary_profile_id || profiles.primary_profile_id,
      randomness: presets[draft.randomness] ?? presets.off },
    attachments: selectedAssets(draft, library).map(({ asset_id, version_id }) => ({ asset_id, version_id })) }
}

function restoreOpeningSource(value: unknown): OpeningSource | null {
  if (!value || typeof value !== 'object') return null
  const source = value as OpeningSource
  return [source.asset_id, source.version_id, source.greeting_id].every((id) => typeof id === 'string' && id.length > 0) ? source : null
}

export function openingSourceAttached(source: OpeningSource | null, assets: SetupAsset[]): boolean {
  return !source || assets.some((item) => item.kind !== 'lorebook' && item.asset_id === source.asset_id && item.version_id === source.version_id)
}
