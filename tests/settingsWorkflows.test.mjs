import assert from 'node:assert/strict'
import test from 'node:test'
import { filterModels } from '../src/features/models/modelFilter.ts'
import { profileSaveState, readyProfiles } from '../src/features/models/profileReadiness.ts'
import { initialConfig } from '../src/features/models/types.ts'
import { sectionState } from '../src/features/prompts/sectionState.ts'
import { appearanceStyles, defaultAppearance } from '../src/features/settings/appearance.ts'
import { continuationRequest } from '../src/features/generation/continuation.ts'

test('445 models can be narrowed by case-insensitive name and provider ID words', () => {
  const models = Array.from({ length: 445 }, (_, index) => ({ id: `vendor/model-${index}`, name: `Writer ${index}` }))
  assert.equal(filterModels(models, '').length, 445)
  assert.deepEqual(filterModels(models, ' VENDOR  writer 444 '), [models[444]])
  assert.deepEqual(filterModels(models, 'missing'), [])
  assert.equal(models.length, 445)
})
test('key-only draft can save but cannot enter the runnable profile list', () => {
  const initial = { config: initialConfig, savedKey: false }
  assert.equal(profileSaveState(initialConfig, 'secret', initial).canSave, true)
  assert.equal(profileSaveState(initialConfig, 'secret', initial).ready, false)
  const saved = { ...initial, savedKey: true }
  assert.equal(profileSaveState(initialConfig, '', saved).canSave, true)
  const draft = { profile_id: 'draft', config: initialConfig }
  const ready = { profile_id: 'ready', config: { ...initialConfig, model: 'writer' } }
  assert.deepEqual(readyProfiles({ profiles: [draft, ready], primary_profile_id: 'draft' }), { profiles: [ready], primary_profile_id: null })
})
test('section mixed state advances to enable all', () => {
  assert.equal(sectionState([{ enabled: true }, { enabled: false }]), 'mixed')
  for (const prompts of [[{ enabled: false }], [{ enabled: false }, { enabled: true }]]) assert.equal(sectionState(prompts) !== 'all', true)
  assert.equal(sectionState([{ enabled: true }, {}]), 'all')
})
test('interface type choices do not change prose and older saved preferences still work', () => {
  const original = appearanceStyles(defaultAppearance)
  const next = appearanceStyles({ ...defaultAppearance, interfaceFont: 'arimo', interfaceSize: 20 })
  assert.equal(next['--prose-font'], original['--prose-font'])
  assert.equal(next['--prose-size'], original['--prose-size'])
  assert.match(next['--interface-font'], /Arimo/)
  assert.equal(next['--interface-size'], '20px')
  const legacy = appearanceStyles({ fontSize: 22, font: 'lora', theme: 'ink', reducedMotion: false })
  assert.equal(legacy['--interface-size'], '16px')
  assert.match(legacy['--prose-font'], /Lora/)
})
test('continuation uses refreshed revision, selected writer, and stable operation identity', () => {
  const branch = { id: 'branch', head_id: 'new-node', revision: 8, mechanics: { pending: null } }
  const receipt = { branch_id: 'branch', node_id: 'new-node' }
  const choice = { assess_beat: false, assessment_profile_ids: ['reviewer'] }
  const first = continuationRequest(branch, receipt, 'writer', true, choice)
  assert.deepEqual(first, { operation_id: 'continue-new-node', expected_revision: 8, profile_ids: ['writer'], use_prepared_beat: false, ...choice })
  assert.deepEqual(continuationRequest(branch, receipt, 'writer', true, choice), first)
  assert.throws(() => continuationRequest({ ...branch, head_id: 'other-node' }, receipt, '', true, choice), /path changed/)
  assert.throws(() => continuationRequest({ ...branch, id: 'other-branch' }, receipt, '', true, choice), /path changed/)
})
