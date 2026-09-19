import test from 'node:test'
import assert from 'node:assert/strict'
import { emptyPreferences, parsePreferences, preferenceKey, hiddenReason, rememberChoice, savePreferences, suggestion } from '../src/features/phrases/preferences.ts'

const finding = { id: 'a'.repeat(64), phrase_id: 'b'.repeat(64), phrase: 'silver birds gather quietly' }

test('phrase checks start off and branch preferences use independent keys', () => {
  assert.equal(emptyPreferences().enabled, false)
  assert.notEqual(preferenceKey('original'), preferenceKey('sibling'))
  assert.deepEqual(parsePreferences(null), emptyPreferences())
})

test('dismissal is specific to an observation; intentional wording survives new occurrences', () => {
  const changed = { ...finding, id: 'c'.repeat(64) }
  const dismissed = rememberChoice(emptyPreferences(), finding, 'dismissed')
  assert.equal(hiddenReason(dismissed, finding), 'dismissed')
  assert.equal(hiddenReason(dismissed, changed), null)
  const intentional = rememberChoice(emptyPreferences(), finding, 'intentional')
  assert.equal(hiddenReason(intentional, changed), 'intentional')
  assert.equal(hiddenReason(intentional, { ...changed, phrase_id: 'd'.repeat(64), phrase: 'the silver birds gather quietly today' }), 'intentional')
  assert.equal(hiddenReason(intentional, { ...changed, phrase_id: 'd'.repeat(64), phrase: 'silver birds gather quietlyish' }), null)
  assert.equal(hiddenReason({ ...intentional, intentional: [] }, changed), null)
})

test('saved choices roundtrip, duplicates remain singular, and malformed state fails visibly', () => {
  const chosen = rememberChoice(emptyPreferences(), finding, 'intentional')
  assert.deepEqual(parsePreferences(JSON.stringify(chosen)), chosen)
  assert.equal(rememberChoice(chosen, finding, 'intentional').intentional.length, 1)
  for (const value of ['null', '{}', 'bad json', JSON.stringify({ ...chosen, enabled: 'yes' }), JSON.stringify({ ...chosen, dismissed: [null] })]) {
    assert.throws(() => parsePreferences(value))
  }
})

test('preference writes reject stale tabs and storage failure without losing stored choices', () => {
  const values = new Map()
  const storage = { getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value) }
  const key = preferenceKey('branch')
  const raw = savePreferences(storage, key, null, emptyPreferences())
  assert.equal(storage.getItem(key), raw)
  assert.throws(() => savePreferences(storage, key, null, { ...emptyPreferences(), enabled: true }), /another view/)
  assert.throws(() => savePreferences({ ...storage, setItem: () => { throw new Error('quota') } }, key, raw, emptyPreferences()), /quota/)
  assert.equal(storage.getItem(key), raw)
})

test('suggestion templates preserve author choice and escape quoted phrases as data', () => {
  assert.match(suggestion(finding.phrase, 'vary'), /Preserve the meaning, character voice/)
  assert.match(suggestion(finding.phrase, 'trim'), /keep repetitions/)
  assert.ok(suggestion('a "quoted" phrase', 'vary').includes(JSON.stringify('a "quoted" phrase')))
})
