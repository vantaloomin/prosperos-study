import test from 'node:test'
import assert from 'node:assert/strict'
import { cleanupChoices } from '../src/features/phrases/cleanupRequest.ts'
import { draftWording, originalWords } from '../src/features/phrases/cleanupTypes.ts'

test('cleanup freezes choices for the originating path and fails closed on unreadable preferences', () => {
  const saved = { version: 1, enabled: false, intentional: [{ id: 'a'.repeat(64), phrase: 'she let out a breath' }], dismissed: [] }
  const storage = { getItem: key => key.endsWith(':original') ? JSON.stringify(saved) : null }
  const frozen = cleanupChoices('original', storage)
  assert.deepEqual(frozen, { intentional: saved.intentional, dismissed: [] })
  saved.intentional = []
  assert.equal(frozen.intentional.length, 1)
  assert.deepEqual(cleanupChoices('sibling', storage), { intentional: [], dismissed: [] })
  assert.equal(cleanupChoices('original', { getItem: () => '{invalid' }), null)
  assert.equal(cleanupChoices('original', { getItem: () => { throw new Error('storage unavailable') } }), null)
})

test('only a completed selected current cleanup supplies displayed draft wording', () => {
  const cleanup = { selected: 'cleaned', status: 'done', stale: false, cleaned: 'Polished text' }
  assert.equal(draftWording('Original text', cleanup), 'Polished text')
  for (const change of [{ stale: true }, { selected: 'original' }, { status: 'running' }, { status: 'cancelled' }, { status: 'interrupted' }]) {
    assert.equal(draftWording('Original text', { ...cleanup, ...change }), 'Original text')
  }
  assert.equal(draftWording('Original text'), 'Original text')
})

test('comparison offsets preserve Unicode characters before the flagged wording', () => {
  assert.equal(originalWords('😀 Café: she let out a breath.', 8, 28), 'she let out a breath')
})
