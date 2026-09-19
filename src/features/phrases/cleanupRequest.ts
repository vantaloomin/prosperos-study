import { parsePreferences, preferenceKey, type ChoiceStorage } from './preferences.ts'

// Freeze author choices once with the durable writing request. Never reread on retry.
export function cleanupChoices(branchId: string, storage: Pick<ChoiceStorage, 'getItem'> = localStorage) {
  try {
    const { intentional, dismissed } = parsePreferences(storage.getItem(preferenceKey(branchId)))
    if ([...intentional, ...dismissed].some(choice => !choice.phrase || choice.phrase.length > 1000)) return null
    return { intentional, dismissed }
  } catch { return null }
}
