import test from 'node:test'
import assert from 'node:assert/strict'
import { mergeStyleSuggestions } from '../src/features/writing/analysisTypes.ts'

const original = { prose: 'Existing prose preference.', viewpoint: '', tense: '', dialogue: 'Keep the dialogue.', rhythm: 'An earlier rhythm.', description: '', avoid: '', examples: [{ label: 'Keep', text: 'Exact sample.\n' }] }

test('copying selected analysis fields preserves independent draft edits and exact samples', () => {
  const current = { ...original, prose: 'A newer independent preference.' }
  const result = mergeStyleSuggestions(current, { rhythm: 'Reviewed suggestion.' }, { rhythm: original.rhythm })
  assert.deepEqual(result, { ...current, rhythm: 'Reviewed suggestion.' })
  assert.equal(current.rhythm, original.rhythm)
})

test('a concurrent edit to the selected field is refused without changing the draft', () => {
  const current = { ...original, rhythm: 'Newer rhythm.' }
  assert.throws(() => mergeStyleSuggestions(current, { rhythm: 'Old suggestion.' }, { rhythm: original.rhythm }), /changed in another view/)
  assert.equal(current.rhythm, 'Newer rhythm.')
})
