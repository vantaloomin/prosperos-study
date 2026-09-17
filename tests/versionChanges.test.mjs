import assert from 'node:assert/strict'
import test from 'node:test'
import { changeAssetKind, migrateAssetDraft, versionChanges, versionDraft } from '../src/features/library/versionChanges.ts'

const before = { id: 'v1', asset_id: 'person', kind: 'character', number: 1, name: 'Reader', note: '', created_at: '',
  content: { text: 'Rain.', voice: 'Quiet.', lorebook_versions: ['book-1'], activation: { priority: 7, tags: ['harbor'] } } }

test('switching a new asset type preserves each draft without sending character-only fields to a persona', () => {
  const initial = versionDraft(before)
  const next = changeAssetKind(initial, 'persona')
  assert.deepEqual(next.content, { text: 'Rain.' })
  next.content.address = 'The Reader'
  const character = changeAssetKind(next, 'character')
  assert.deepEqual(character.content, initial.content)
  assert.equal(changeAssetKind(character, 'persona').content.address, 'The Reader')
})

test('restoring an older draft preserves all content and does not mutate the published version', () => {
  const draft = versionDraft(before)
  assert.deepEqual(draft.content, before.content)
  draft.content.lorebook_versions[0] = 'book-2'
  draft.content.activation.tags.push('night')
  assert.deepEqual(before.content.lorebook_versions, ['book-1'])
  assert.deepEqual(before.content.activation.tags, ['harbor'])
})

test('legacy saved editor drafts keep their edits and preserved asset metadata', () => {
  const result = migrateAssetDraft({ kind: 'character', name: 'Renamed', text: 'An unsaved edit.', voice: 'Soft.', note: 'Draft' }, before)
  assert.equal(result.content.text, 'An unsaved edit.')
  assert.equal(result.name, 'Renamed')
  assert.deepEqual(result.content.activation, before.content.activation)
  assert.deepEqual(result.content.lorebook_versions, ['book-1'])
})

test('version comparison includes removed fields and link changes, and ignores object-key order', () => {
  const after = { ...before, content: { text: 'Dry.', lorebook_versions: ['book-2'], activation: { tags: ['harbor'], priority: 7 } } }
  const changes = versionChanges(before, after)
  assert.deepEqual(changes.map((change) => change.key), ['text', 'voice', 'lorebook_versions'])
  assert.equal(changes.find((change) => change.key === 'voice').after, undefined)
  assert.deepEqual(versionChanges(before, { ...before, number: 2, note: 'Note only' }), [])
})
