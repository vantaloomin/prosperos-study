import test from 'node:test'
import assert from 'node:assert/strict'
import { sameAssignments } from '../src/features/workflow/routingState.ts'

test('a prompt-only revision permits retaining unsaved routing edits', () => {
  const before = { story_revision: 1, primary_profile_id: null, step_profiles: { writer: 'a', 'beat-assessment': 'b' } }
  const after = { ...before, story_revision: 2, step_profiles: { 'beat-assessment': 'b', writer: 'a' } }
  assert.equal(sameAssignments(before, after), true)
})

test('rebasing a routing save must not overwrite another assignment change', () => {
  const before = { primary_profile_id: null, step_profiles: { writer: 'a' } }
  assert.equal(sameAssignments(before, { ...before, primary_profile_id: 'b' }), false)
  assert.equal(sameAssignments(before, { ...before, step_profiles: { writer: 'b' } }), false)
  assert.equal(sameAssignments(before, { ...before, step_profiles: {} }), false)
  assert.equal(sameAssignments(before, { ...before, step_profiles: { writer: 'a', 'beat-assessment': 'b' } }), false)
})
