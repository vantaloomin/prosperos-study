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

test('reviewed previews cannot follow a branch, direction, comparison or assessment selection change', async () => {
  const { contextRequestKey, reviewedInput } = await import('../src/features/generation/reviewedContext.ts')
  const request = { expected_revision: 7, profile_ids: ['primary'], use_prepared_beat: true,
    assess_beat: true, assessment_profile_ids: [], direction: 'Follow the missing key.' }
  const reviewed = { key: contextRequestKey('original', request), fingerprint: 'verified-inputs' }
  assert.deepEqual(reviewedInput('original', { ...request }, reviewed), { reviewed_fingerprint: 'verified-inputs' })
  for (const changed of [{ expected_revision: 8 }, { direction: 'Move to the next scene.' },
    { profile_ids: ['primary', 'comparison'] }, { use_prepared_beat: false },
    { assess_beat: false }, { assessment_profile_ids: ['other-assessor'] }, { knowledge_subject: 'Elin' }, { knowledge_character_id: 'character-id' }]) {
    assert.deepEqual(reviewedInput('original', { ...request, ...changed }, reviewed), {})
  }
  assert.deepEqual(reviewedInput('fork', request, reviewed), {})
  assert.deepEqual(reviewedInput('original', request, null), {})
})

test('character requests explicitly exclude chance without changing author-view defaults', async () => {
  const { characterRequest } = await import('../src/features/generation/knowledgeRequest.ts')
  const original = { expected_revision: 3, profile_ids: ['writer'], use_prepared_beat: true, assess_beat: true, assessment_profile_ids: ['assessor'] }
  assert.strictEqual(characterRequest(original, ''), original)
  assert.deepEqual(characterRequest(original, 'Elin'), { ...original, knowledge_subject: 'Elin', use_prepared_beat: false, assess_beat: false, assessment_profile_ids: [] })
  assert.equal(original.assess_beat, true)
})

test('Character identity requests do not depend on display names', async () => {
  const { characterRequest } = await import('../src/features/generation/knowledgeRequest.ts')
  const request = { expected_revision: 7, profile_ids: [] }
  assert.deepEqual(characterRequest(request, 'character:stable-id'), { ...request, knowledge_character_id: 'stable-id', use_prepared_beat: false, assess_beat: false, assessment_profile_ids: [] })
  assert.equal(characterRequest(request, 'name:character:Elin').knowledge_subject, 'character:Elin')
  assert.deepEqual(request, { expected_revision: 7, profile_ids: [] })
})


test('scene character briefings keep identity and deliberately empty assignments for validation', async () => {
  const { actorInputs } = await import('../src/features/scenes/characterDialogueRequest.ts')
  const actors = [
    { view: 'character:stable-id', slot_ids: ['s1'], briefing: 'Visible first situation.' },
    { view: 'name:character:Elin', slot_ids: ['s2'], briefing: 'Visible second situation.' },
  ]
  assert.deepEqual(actorInputs({ enabled: false, actors }), [])
  assert.deepEqual(actorInputs({ enabled: true, actors }), [
    { character_id: 'stable-id', slot_ids: ['s1'], briefing: 'Visible first situation.' },
    { subject: 'character:Elin', slot_ids: ['s2'], briefing: 'Visible second situation.' },
  ])
  assert.deepEqual(actorInputs({ enabled: true, actors: [] }), [])
  assert.equal(actorInputs({ enabled: true, actors: [{ view: '', slot_ids: [], briefing: '' }] })[0].subject, '')
  assert.equal(actors[1].view, 'name:character:Elin')
})


test('rehearsal snapshots become earlier results after branch, edition or decision changes', async () => {
  const { sameRehearsalBoundary, viewpointLabel } = await import('../src/features/storyMemory/rehearsalTypes.ts')
  const boundary = { branch_id: 'branch', head_id: 'head', revision: 3, manifest_id: 'edition', version_id: 'decisions' }
  assert.equal(sameRehearsalBoundary(boundary, { ...boundary }), true)
  for (const field of Object.keys(boundary)) assert.equal(sameRehearsalBoundary(boundary, { ...boundary, [field]: 'changed' }), false)
  assert.notEqual(viewpointLabel({ key: 'a', subject: 'Elin', character_id: '12345678long' }), viewpointLabel({ key: 'b', subject: 'Elin', character_id: '87654321long' }))
  assert.match(viewpointLabel({ key: 'name:elin', subject: 'Elin', character_id: null }), /name-only/)
})
