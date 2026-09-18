import { states } from './controlTypes.ts'
import { draftKey, saveBody, type DecisionDraft, type DraftScope } from './decisionDraft.ts'

interface Storage { getItem: (key: string) => string | null; setItem: (key: string, value: string) => void; removeItem: (key: string) => void }
export interface LoadedDraft { value: DecisionDraft | null; raw: string | null; error: string }
const READ_ERROR = 'The recovery copy could not be read. It has not been overwritten. Download it or explicitly discard it before starting a new draft.'

function object(value: unknown): value is Record<string, unknown> { return typeof value === 'object' && value !== null && !Array.isArray(value) }
function strings(value: Record<string, unknown>, keys: string[]) { return keys.every(key => typeof value[key] === 'string') }
function optionalStrings(value: Record<string, unknown>, keys: string[]) { return keys.every(key => value[key] === undefined || typeof value[key] === 'string') }
function nullableString(value: unknown) { return value === null || typeof value === 'string' }
function source(value: unknown) {
  if (!object(value) || !strings(value, ['id', 'title', 'text', 'sha256'])) return false
  if (!optionalStrings(value, ['node_id', 'asset_id', 'version_id', 'field', 'name', 'role'])) return false
  return Number.isSafeInteger(value.start) && Number.isSafeInteger(value.end) && Number(value.start) >= 0 && Number(value.end) > Number(value.start)
}
function entry(value: unknown): boolean {
  if (!object(value) || !strings(value, ['id', 'kind', 'subject', 'text', 'stance'])) return false
  if (!optionalStrings(value, ['character_id'])) return false
  const kind = value.kind as keyof typeof states
  if (!Object.hasOwn(states, kind) || !states[kind].some(([key]) => key === value.stance)) return false
  return typeof value.enabled === 'boolean' && Array.isArray(value.sources) && value.sources.length <= 8 && value.sources.every(source)
}
function validBase(value: unknown) { return object(value) && Object.values(value).every(item => typeof item === 'string') }
function validDraft(value: unknown, scope: DraftScope): value is DecisionDraft {
  if (!object(value) || value.schema !== 1 || value.story_id !== scope.story_id || value.branch_id !== scope.id) return false
  if (!strings(value, ['stamp']) || !Number.isSafeInteger(value.revision) || Number(value.revision) < 0 || !nullableString(value.version_id)) return false
  return validFields(value)
}
function validFields(value: Record<string, unknown>) {
  if (!validBase(value.base) || !Array.isArray(value.entries) || value.entries.length > 64 || !value.entries.every(entry)) return false
  if (new Set(value.entries.map(item => item.id)).size !== value.entries.length) return false
  return (value.editing === null || entry(value.editing)) && validPending(value)
}
function validPending(value: Record<string, unknown>) {
  if (value.pending === null) return true
  if (!object(value.pending) || typeof value.pending.operation_id !== 'string') return false
  return JSON.stringify(value.pending) === JSON.stringify(saveBody(value as unknown as DecisionDraft, value.pending.operation_id))
}

export function readDraft(storage: Storage, scope: DraftScope): LoadedDraft {
  let raw: string | null = null
  try {
    raw = storage.getItem(draftKey(scope))
    if (raw === null) return { value: null, raw, error: '' }
    const value: unknown = JSON.parse(raw)
    if (!validDraft(value, scope)) throw new Error(READ_ERROR)
    return { value, raw, error: '' }
  } catch { return { value: null, raw, error: READ_ERROR } }
}

export function writeDraft(storage: Storage, key: string, expected: string | null, value: DecisionDraft | null): string | null {
  if (storage.getItem(key) !== expected) throw new Error('Another view changed this branch’s recovery copy. Your work is still here; download it before leaving. The other copy has been preserved.')
  const raw = value ? JSON.stringify(value) : null
  if (raw === null) storage.removeItem(key)
  else storage.setItem(key, raw)
  return raw
}
