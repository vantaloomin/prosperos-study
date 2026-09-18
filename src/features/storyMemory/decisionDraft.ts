import type { Entry, State } from './controlTypes'

export interface DraftScope { story_id: string; id: string }
export interface SaveBody { operation_id: string; expected_revision: number; expected_version_id: string | null; entries: ReturnType<typeof entryInput>[] }
export interface DecisionDraft {
  schema: 1; story_id: string; branch_id: string; stamp: string
  revision: number; version_id: string | null; base: Record<string, string>
  entries: Entry[]; editing: Entry | null; pending: SaveBody | null
}
export interface MergeConflict { id: string; local?: Entry; saved?: Entry; unavailable?: Entry }
export interface DraftMerge { entries: Entry[]; conflicts: MergeConflict[] }

export function draftKey(scope: DraftScope) { return `roleplay:author-decisions:v1:${scope.story_id}:${scope.id}` }

export function entryInput({ sources, ...entry }: Entry) {
  return { id: entry.id, kind: entry.kind, subject: entry.subject, text: entry.text, stance: entry.stance,
    enabled: entry.enabled, character_id: entry.character_id ?? null, source_ids: sources.map(source => source.id) }
}

export function signature(entry?: Entry) { return entry ? JSON.stringify(entryInput(entry)) : undefined }
export function baseOf(state: Pick<State, 'entries'>) { return Object.fromEntries(state.entries.map(entry => [entry.id, signature(entry)!])) }
export function startDraft(scope: DraftScope, state: State, stamp: string): DecisionDraft {
  return { schema: 1, story_id: scope.story_id, branch_id: scope.id, stamp, revision: state.revision,
    version_id: state.version_id, base: baseOf(state), entries: state.entries, editing: null, pending: null }
}
export function saveBody(draft: DecisionDraft, operation_id: string): SaveBody {
  return { operation_id, expected_revision: draft.revision, expected_version_id: draft.version_id, entries: draft.entries.map(entryInput) }
}
export function staleDraft(draft: DecisionDraft | null, current?: State) {
  return !!draft && !!current && (draft.revision !== current.revision || draft.version_id !== current.version_id)
}

export function mergeDraft(draft: DecisionDraft, current: State): DraftMerge {
  const local = new Map(draft.entries.map(entry => [entry.id, entry]))
  const saved = new Map(current.entries.map(entry => [entry.id, entry]))
  const unavailable = new Map((current.unavailable_entries ?? []).map(entry => [entry.id, entry]))
  const result: DraftMerge = { entries: [], conflicts: [] }
  const ids = new Set([...Object.keys(draft.base), ...local.keys(), ...saved.keys()])
  for (const id of ids) {
    const mine = local.get(id), theirs = saved.get(id)
    if (mine && unavailable.has(id)) { result.conflicts.push({ id, local: mine, unavailable: unavailable.get(id) }); continue }
    const choice = mergeEntry(Object.hasOwn(draft.base, id) ? draft.base[id] : undefined, mine, theirs)
    if (choice === 'conflict') result.conflicts.push({ id, local: mine, saved: theirs })
    else if (choice) result.entries.push(choice)
  }
  return result
}

function mergeEntry(base: string | undefined, local?: Entry, saved?: Entry): Entry | 'conflict' | undefined {
  if (signature(local) === signature(saved)) return local
  if (signature(local) === base) return saved
  if (signature(saved) === base) return local
  return 'conflict'
}

export function finishMerge(draft: DecisionDraft, current: State, merge: DraftMerge, choices: Record<string, 'local' | 'saved'>): DecisionDraft {
  const entries = [...merge.entries]
  for (const conflict of merge.conflicts) {
    const choice = mergeChoice(choices, conflict.id)
    if (!choice) throw new Error('Choose which version to keep for each conflicting decision.')
    const entry = conflict[choice]
    if (entry) entries.push(entry)
  }
  if (entries.length > 64) throw new Error('The combined draft exceeds 64 decisions. Keep a smaller set before saving.')
  return { ...draft, revision: current.revision, version_id: current.version_id, base: baseOf(current), entries }
}

export function mergeChoice(choices: Record<string, 'local' | 'saved'>, id: string) {
  if (!Object.hasOwn(choices, id)) return undefined
  const choice = choices[id]
  return choice === 'local' || choice === 'saved' ? choice : undefined
}
