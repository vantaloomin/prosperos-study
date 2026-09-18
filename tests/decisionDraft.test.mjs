import assert from 'node:assert/strict'
import test from 'node:test'
import { draftKey, finishMerge, mergeDraft, saveBody, staleDraft, startDraft } from '../src/features/storyMemory/decisionDraft.ts'
import { readDraft, writeDraft } from '../src/features/storyMemory/decisionDraftStorage.ts'

const scope = { story_id: 'story-a', id: 'branch-a' }
const source = { id: 'message:one@0:4:hash', node_id: 'one', title: 'The gate', text: '雨 🔑', start: 0, end: 3, sha256: 'a'.repeat(64) }
const entry = (id = 'decision-a', text = 'Opening the gate is uncertain.') => ({ id, kind: 'knowledge', subject: 'Elin', text, stance: 'uncertain', enabled: true, sources: [source] })
const state = (entries = [entry()], revision = 4, version_id = 'saved-one') => ({ entries, revision, version_id, characters: [] })
const draft = () => startDraft(scope, state(), 'stamp-one')
function memoryStorage() {
  const map = new Map()
  return { getItem: key => map.get(key) ?? null, setItem: (key, value) => map.set(key, value), removeItem: key => map.delete(key) }
}

test('incomplete typing, Unicode evidence and staged decisions recover only on the originating branch', () => {
  const storage = memoryStorage(), value = draft()
  value.editing = { ...entry('unfinished'), subject: '', text: 'Typed but not kept', sources: [] }
  const raw = writeDraft(storage, draftKey(scope), null, value)
  assert.deepEqual(readDraft(storage, scope).value, value)
  assert.equal(readDraft(storage, { ...scope, id: 'sibling' }).value, null)
  storage.setItem(draftKey({ ...scope, id: 'sibling' }), raw)
  const wrong = readDraft(storage, { ...scope, id: 'sibling' })
  assert.equal(wrong.value, null)
  assert.ok(wrong.error)
  assert.equal(wrong.raw, raw)
})

test('unreadable or future drafts remain intact for recovery rather than becoming empty data', () => {
  const storage = memoryStorage(), key = draftKey(scope)
  for (const raw of ['broken json', JSON.stringify({ ...draft(), schema: 2 }), JSON.stringify({ ...draft(), entries: [{ id: 'bad' }] })]) {
    storage.setItem(key, raw)
    const recovered = readDraft(storage, scope)
    assert.equal(recovered.value, null)
    assert.ok(recovered.error)
    assert.equal(storage.getItem(key), raw)
  }
})

test('quota, read failure, and another view changing the copy cannot silently erase a draft', () => {
  const storage = memoryStorage(), key = draftKey(scope)
  const original = writeDraft(storage, key, null, draft())
  assert.throws(() => writeDraft({ ...storage, setItem() { throw Error('Quota') } }, key, original, { ...draft(), stamp: 'next' }), /Quota/)
  assert.equal(storage.getItem(key), original)
  const later = writeDraft(storage, key, original, { ...draft(), stamp: 'another-view' })
  assert.throws(() => writeDraft(storage, key, original, null), /Another view/)
  assert.equal(storage.getItem(key), later)
  assert.ok(readDraft({ ...storage, getItem() { throw Error('disabled') } }, scope).error)
})

test('path or decision-version changes mark a recovered draft stale without mutating it', () => {
  const value = draft(), before = structuredClone(value)
  assert.equal(staleDraft(value, state()), false)
  assert.equal(staleDraft(value, state(undefined, 5)), true)
  assert.equal(staleDraft(value, state(undefined, 4, 'saved-two')), true)
  assert.deepEqual(value, before)
})

test('three-way review preserves independent additions and changes from each view', () => {
  const value = draft()
  value.entries = [{ ...entry(), text: 'My revised interpretation' }, entry('my-new')]
  const current = state([entry(), entry('remote-new', 'Another view added this.')], 5, 'saved-two')
  const merge = mergeDraft(value, current)
  assert.equal(merge.conflicts.length, 0)
  const reviewed = finishMerge(value, current, merge, {})
  assert.deepEqual(reviewed.entries.map(item => item.id), ['decision-a', 'my-new', 'remote-new'])
  assert.equal(reviewed.entries[0].text, 'My revised interpretation')
  assert.equal(staleDraft(reviewed, current), false)
  assert.equal(value.revision, 4)
  assert.equal(value.entries.length, 2)
})

test('competing edits and removal versus editing require an explicit choice', () => {
  const value = draft()
  value.entries[0] = { ...entry(), stance: 'unaware' }
  for (const saved of [[{ ...entry(), text: 'Remote changed this.' }], []]) {
    const current = state(saved, 5, 'saved-two'), merge = mergeDraft(value, current)
    assert.equal(merge.conflicts.length, 1)
    assert.throws(() => finishMerge(value, current, merge, {}), /Choose/)
    assert.deepEqual(finishMerge(value, current, merge, { 'decision-a': 'local' }).entries, value.entries)
    assert.deepEqual(finishMerge(value, current, merge, { 'decision-a': 'saved' }).entries, saved)
  }
})

test('an unavailable edition cannot silently retire an unchanged does-not-know restriction', () => {
  const original = { ...entry(), stance: 'unaware' }, value = startDraft(scope, state([original]), 'one')
  const current = { ...state([], 5), unavailable_entries: [original] }
  const merge = mergeDraft(value, current)
  assert.equal(merge.conflicts.length, 1)
  assert.ok(merge.conflicts[0].unavailable)
  assert.throws(() => finishMerge(value, current, merge, {}), /Choose/)
  assert.deepEqual(finishMerge(value, current, merge, { 'decision-a': 'local' }).entries, [original])
  assert.deepEqual(finishMerge(value, current, merge, { 'decision-a': 'saved' }).entries, [])
})

test('an ambiguous save keeps the exact operation and payload through recovery', () => {
  const storage = memoryStorage(), value = draft()
  value.pending = saveBody(value, 'operation-one')
  writeDraft(storage, draftKey(scope), null, value)
  const recovered = readDraft(storage, scope)
  assert.deepEqual(recovered.value.pending, value.pending)
  assert.equal(recovered.value.pending.operation_id, 'operation-one')
  assert.deepEqual(recovered.value.pending.entries[0].source_ids, [source.id])
  assert.equal('sources' in recovered.value.pending.entries[0], false)
  value.pending.entries[0].text = 'mismatched request'
  storage.setItem(draftKey(scope), JSON.stringify(value))
  assert.ok(readDraft(storage, scope).error)
})

test('review will not silently trim decisions when combining exceeds the 64-entry limit', () => {
  const value = startDraft(scope, state([]), 'one')
  value.entries = Array.from({ length: 40 }, (_, i) => entry('local-' + i))
  const current = state(Array.from({ length: 40 }, (_, i) => entry('saved-' + i)), 5, 'two')
  assert.throws(() => finishMerge(value, current, mergeDraft(value, current), {}), /exceeds 64/)
  assert.equal(value.entries.length, 40)
})

test('valid decision IDs matching object properties never bypass conflict choices', () => {
  for (const id of ['constructor', '__proto__']) {
    const value = startDraft(scope, state([entry(id)]), 'one')
    value.entries = [entry(id, 'Mine')]
    const current = state([entry(id, 'Theirs')], 5, 'two'), merge = mergeDraft(value, current)
    assert.equal(merge.conflicts.length, 1)
    assert.throws(() => finishMerge(value, current, merge, {}), /Choose/)
    assert.equal(finishMerge(value, current, merge, { [id]: 'local' }).entries[0].text, 'Mine')
  }
})

test('malformed optional display metadata is preserved as an unreadable copy', () => {
  const storage = memoryStorage(), value = draft()
  value.entries[0].sources[0] = { ...source, name: { invalid: true } }
  const raw = JSON.stringify(value)
  storage.setItem(draftKey(scope), raw)
  assert.ok(readDraft(storage, scope).error)
  assert.equal(storage.getItem(draftKey(scope)), raw)
})
