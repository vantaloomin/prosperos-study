import type { PhraseChoice, PhraseFinding, PhrasePreferences } from './types'

export const preferenceKey = (branchId: string) => `prospero:phrase-check:v1:${branchId}`
export const emptyPreferences = (): PhrasePreferences => ({ version: 1, enabled: false, dismissed: [], intentional: [] })
const LIMIT = 200

function validChoices(value: unknown): value is PhraseChoice[] {
  return Array.isArray(value) && value.length <= LIMIT && value.every(item =>
    item && typeof item.id === 'string' && /^[a-f0-9]{64}$/.test(item.id) &&
    typeof item.phrase === 'string' && item.phrase.length <= 100000)
}

export function parsePreferences(raw: string | null): PhrasePreferences {
  if (raw === null) return emptyPreferences()
  const value = JSON.parse(raw)
  if (value?.version !== 1 || typeof value.enabled !== 'boolean' || !validChoices(value.dismissed) || !validChoices(value.intentional)) {
    throw new Error('These phrase-check choices could not be read. Reset the local choices to continue.')
  }
  return value
}

export function hiddenReason(preferences: PhrasePreferences, finding: PhraseFinding) {
  if (preferences.intentional.some(choice => choice.id === finding.phrase_id || ` ${finding.phrase} `.includes(` ${choice.phrase} `))) return 'intentional'
  if (preferences.dismissed.some(choice => choice.id === finding.id)) return 'dismissed'
  return null
}

export function rememberChoice(preferences: PhrasePreferences, finding: PhraseFinding, kind: 'dismissed' | 'intentional'): PhrasePreferences {
  const id = kind === 'intentional' ? finding.phrase_id : finding.id
  const kept = preferences[kind].filter(choice => choice.id !== id)
  if (kept.length >= LIMIT) throw new Error('Restore an earlier choice before saving more phrase-check choices.')
  return { ...preferences, [kind]: [...kept, { id, phrase: finding.phrase }] }
}

export interface ChoiceStorage { getItem: (key: string) => string | null; setItem: (key: string, value: string) => void }
export function savePreferences(storage: ChoiceStorage, key: string, previous: string | null, value: PhrasePreferences) {
  if (storage.getItem(key) !== previous) throw new Error('Phrase-check choices changed in another view. Reopen this tool before saving a choice.')
  const raw = JSON.stringify(value)
  storage.setItem(key, raw)
  return raw
}

export function suggestion(phrase: string, kind: 'vary' | 'trim') {
  const quoted = JSON.stringify(phrase)
  return kind === 'vary'
    ? `Vary the wording around ${quoted} where repetition is accidental. Preserve the meaning, character voice, and any deliberate echo.`
    : `Review repeated uses of ${quoted}. Consider trimming an occurrence that adds no new meaning; keep repetitions that serve rhythm, emphasis, or character voice.`
}
