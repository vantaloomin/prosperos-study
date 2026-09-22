import assert from 'node:assert/strict'
import test from 'node:test'
import { experienceChange, experiences, freshSetup, pinAsset, restoreSetup, selectedAssets, storyStart, writingPreferences } from '../src/features/stories/setup.ts'

const book = { asset_id: 'city', id: 'city-v1', name: 'The city', number: 1, kind: 'lorebook' }
const writer = { profile_id: 'writer-1' }
const profiles = { profiles: [writer], primary_profile_id: writer.profile_id }

test('migrate unfinished older setup without losing its story or Library choices', () => {
  const draft = restoreSetup({ step: 2, title: 'My story', premise: 'A beginning', persona: 'Wren', genre: 'Mystery', assets: ['city'] })
  assert.equal(draft.step, 2)
  assert.equal(draft.title, 'My story')
  assert.equal(draft.persona, 'Wren')
  assert.deepEqual(selectedAssets(draft, [book]), [pinAsset(book)])
  assert.equal(storyStart(draft, profiles, [book], 'operation-one').attachments[0].version_id, 'city-v1')
  assert.throws(() => storyStart(draft, profiles, [], 'operation-one'), /unavailable/)
})

test('selected versions and submitted payload survive resume and later defaults', () => {
  const draft = { ...freshSetup(), title: 'Story', primary_profile_id: writer.profile_id, randomness: 'quiet', assets: [pinAsset(book)] }
  const later = { ...book, id: 'city-v2', number: 2 }
  const payload = storyStart(draft, profiles, [later], 'operation-two')
  const restored = restoreSetup(JSON.parse(JSON.stringify({ ...draft, pending: payload })))
  assert.equal(restored.step, 5)
  assert.deepEqual(restored.pending, payload)
  assert.equal(payload.attachments[0].version_id, 'city-v1')
  assert.deepEqual(payload.settings.randomness, { enabled: true, chance: 10, cooldown: 4 })
  assert.equal(payload.settings.primary_profile_id, writer.profile_id)
  assert.throws(() => storyStart(draft, { profiles: [], primary_profile_id: null }, [book], 'operation-three'), /profile is unavailable/)
})

test('invalid stored choices recover safe defaults and finite step indexes', () => {
  assert.deepEqual(restoreSetup(null), freshSetup())
  const draft = restoreSetup({ schema: 2, step: NaN, title: 'Keep me', experience: 'unknown', randomness: 'unknown', player_agency: 'unknown', assets: [null, 'bad'] })
  assert.equal(draft.step, 0)
  assert.equal(draft.title, 'Keep me')
  assert.equal(draft.experience, 'directed')
  assert.equal(draft.randomness, 'off')
  assert.equal(draft.player_agency, 'shared')
  assert.deepEqual(draft.assets, [])
})

test('new onboarding leads with writing while existing stories and resumed drafts keep their choices', () => {
  assert.deepEqual(experienceChange('roleplay'), { experience: 'roleplay', player_agency: 'user', response_length: 'Flexible — stop when the next meaningful move belongs to the user.' })
  assert.deepEqual(experienceChange('directed'), { experience: 'directed' })
  assert.equal(experiences[0].id, 'directed')
  const fresh = freshSetup()
  assert.equal(fresh.experience, 'directed')
  assert.equal(fresh.pov, 'third person')
  assert.equal(fresh.player_agency, 'shared')
  assert.equal(storyStart(fresh, profiles, [], 'writing-first').settings.experience, 'directed')
  assert.deepEqual(restoreSetup(fresh), fresh)
  assert.equal(restoreSetup({ schema: 2, title: 'Existing draft' }).experience, 'roleplay')
  assert.equal(writingPreferences({}).experience, 'roleplay')
  const explicit = { experience: 'roleplay', pov: 'first person', tense: 'present', player_agency: 'user' }
  for (const [key, value] of Object.entries(explicit)) {
    assert.equal(restoreSetup({ schema: 2, ...explicit })[key], value)
    assert.equal(writingPreferences(explicit)[key], value)
  }
})

test('greeting provenance resumes with pinned versions and requires review after changing characters', () => {
  const character = { ...book, asset_id: 'iona', id: 'iona-v1', name: 'Iona', kind: 'character' }
  const source = { asset_id: character.asset_id, version_id: character.id, greeting_id: 'rain' }
  const draft = restoreSetup({ ...freshSetup(), title: 'Rain', opening: 'An adapted greeting.', opening_source: source, assets: [pinAsset(character)] })
  const payload = storyStart(draft, profiles, [], 'greeting-operation')
  assert.deepEqual(payload.opening_source, source)
  assert.deepEqual(restoreSetup({ ...draft, pending: payload }).pending, payload)
  assert.throws(() => storyStart({ ...draft, assets: [] }, profiles, [], 'new-operation'), /greeting source/)
  assert.throws(() => storyStart({ ...draft, assets: [pinAsset({ ...character, id: 'iona-v2' })] }, profiles, [], 'new-operation'), /greeting source/)
  const custom = storyStart({ ...draft, assets: [], opening_source: null }, profiles, [], 'custom-operation')
  assert.equal(custom.opening_text, draft.opening)
  assert.equal('opening_source' in custom, false)
  assert.equal(restoreSetup({ schema: 2, opening: 'Old unfinished opening' }).opening_source, null)
})

test('skip setup permits an untitled manual Story and reuses an available primary writer', () => {
  for (const title of ['', '  \t\n']) {
    const draft = { ...freshSetup(), title }
    const manual = storyStart(draft, { profiles: [], primary_profile_id: null }, [], 'skip-manual', true)
    assert.equal(manual.title, 'Untitled Story')
    assert.equal(manual.settings.primary_profile_id, null)
    assert.equal(manual.settings.experience, 'directed')
    assert.equal(manual.settings.randomness.enabled, false)
    assert.equal(manual.premise, '')
    assert.equal(manual.opening_text, '')
    assert.deepEqual(manual.attachments, [])
    assert.equal(storyStart(draft, profiles, [], 'skip-writer', true).settings.primary_profile_id, writer.profile_id)
    assert.equal(storyStart(draft, profiles, [], 'guided-title').title, '')
    assert.equal(draft.title, title)
  }
})

test('skipping the remaining steps preserves all entered choices and pinned versions', () => {
  const draft = { ...freshSetup(), title: '  夜の庭  ', premise: 'A quiet reunion.', opening: '  An exact opening.\n',
    ...experienceChange('roleplay'), genre: 'Mystery', tone: 'Quiet', persona: 'Wren', pov: 'first person', tense: 'present',
    randomness: 'quiet', primary_profile_id: writer.profile_id, assets: [pinAsset(book)] }
  const newer = { ...book, id: 'city-v2', number: 2 }
  const skipped = storyStart(draft, profiles, [newer], 'same-operation', true)
  assert.deepEqual(skipped, storyStart(draft, profiles, [newer], 'same-operation'))
  assert.equal(skipped.title, '夜の庭')
  assert.equal(skipped.opening_text, draft.opening)
  assert.equal(skipped.attachments[0].version_id, 'city-v1')
  const untitled = storyStart({ ...draft, title: '' }, profiles, [newer], 'saved-skip', true)
  const restored = restoreSetup(JSON.parse(JSON.stringify({ ...draft, title: untitled.title, pending: untitled })))
  assert.equal(restored.step, 5)
  assert.equal(restored.title, 'Untitled Story')
  assert.deepEqual(restored.pending, untitled)
})

test('skip setup cannot silently discard invalid writer, legacy Library or greeting choices', () => {
  const manual = { profiles: [], primary_profile_id: null }
  assert.throws(() => storyStart({ ...freshSetup(), primary_profile_id: 'missing' }, manual, [], 'skip-stale-model', true), /profile is unavailable/)
  assert.throws(() => storyStart({ ...freshSetup(), legacyAssets: ['missing'] }, manual, [], 'skip-stale-library', true), /Library choice.*unavailable/)
  assert.throws(() => storyStart({ ...freshSetup(), opening: 'Keep my greeting.', opening_source: { asset_id: 'missing', version_id: 'missing-v1', greeting_id: 'start' } }, manual, [], 'skip-stale-opening', true), /greeting source/)
})
