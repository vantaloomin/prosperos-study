import assert from 'node:assert/strict'
import test from 'node:test'
import { ownsRun, proseTargets, replaceProse } from '../src/features/authoring/targets.ts'

test('apply and undo preserve later edits outside the chosen prose field', () => {
  const draft = { kind: 'character', name: 'Mara', note: 'draft', content: { text: '  Original\n', voice: 'Quiet', custom: { retained: true } } }
  const applied = replaceProse(draft, 'text', '  Original\n', 'New prose\n')
  const later = { ...applied, content: { ...applied.content, voice: 'Dry humor' } }
  const undone = replaceProse(later, 'text', 'New prose\n', '  Original\n')
  assert.equal(undone.content.voice, 'Dry humor')
  assert.deepEqual(undone.content.custom, { retained: true })
  assert.equal(undone.content.text, draft.content.text)
  assert.equal(draft.content.voice, 'Quiet')
})

test('changed or deleted fields reject apply and undo instead of replacing newer work', () => {
  const draft = { kind: 'character', content: { text: 'Later edit' } }
  assert.throws(() => replaceProse(draft, 'text', 'Earlier', 'Suggestion'), /field changed/)
  assert.throws(() => replaceProse(draft, 'greeting:deleted', '', 'Suggestion'), /field changed/)
})

test('entry assistance changes only prose and preserves activation, unknown metadata and siblings', () => {
  const entry = { id: 'a', title: 'Harbor', text: 'Fog', enabled: false, chance: 20, other: { custom: true } }
  const sibling = { id: 'b', title: 'Hill', text: 'Sun' }
  const draft = { kind: 'lorebook', content: { text: 'World', lore_definition: { budget: 99, entries: [entry, sibling] } } }
  assert.equal(proseTargets(draft).find((item) => item.key === 'entry:a').text, 'Fog')
  const next = replaceProse(draft, 'entry:a', 'Fog', '# Fog\n\nSilver lamps.')
  assert.deepEqual(next.content.lore_definition.entries[0], { ...entry, text: '# Fog\n\nSilver lamps.' })
  assert.deepEqual(next.content.lore_definition.entries[1], sibling)
  assert.equal(next.content.text, 'World')
})

test('unsaved additions have independent identities even when both passages are empty', () => {
  const run = { asset_id: null, snapshot: { draft_id: 'first-addition', kind: 'character' } }
  const first = { draftId: 'first-addition', draft: { kind: 'character', content: { text: '' } } }
  assert.equal(ownsRun(run, first), true)
  assert.equal(ownsRun(run, { ...first, draftId: 'different-addition' }), false)
  assert.equal(ownsRun(run, { ...first, asset: { asset_id: 'published-item' } }), false)
  assert.equal(ownsRun({ ...run, asset_id: 'published-item' }, { ...first, asset: { asset_id: 'published-item' } }), true)
})
