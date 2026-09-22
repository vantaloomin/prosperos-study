import test from 'node:test'
import assert from 'node:assert/strict'
import { pendingQuestions, retainQuestion, forgetQuestion } from '../src/features/collaborator/pendingQuestions.ts'
import { retainedDrafts, retainDraft } from '../src/features/textEdits/draftStorage.ts'
import { resolveBranch } from '../src/features/chat/branchSelection.ts'

const values = new Map()
globalThis.localStorage = {
  get length() { return values.size }, key: index => [...values.keys()][index] ?? null,
  getItem: key => values.get(key) ?? null, setItem: (key, value) => values.set(key, value), removeItem: key => values.delete(key),
}
const request = (thread, id, question) => ({ kind: 'side-question', path: `/side-conversations/${thread}/questions`, body: { operation_id: id, question, expected_draft_version: 'version' } })

test('independent windows retain separate operations and receipt cleanup removes only its own request', () => {
  values.clear()
  const first = request('thread', 'a', 'First question'), second = request('thread', 'b', 'Second question')
  retainQuestion('thread', first); retainQuestion('thread', second); retainQuestion('other', request('other', 'c', 'Other conversation'))
  assert.deepEqual(pendingQuestions('thread'), [first, second])
  forgetQuestion('thread', first)
  assert.deepEqual(pendingQuestions('thread'), [second])
  assert.equal(pendingQuestions('other').length, 1)
  assert.throws(() => retainQuestion('thread', { ...second, body: { ...second.body, question: 'Changed inputs' } }), /different inputs/)
  assert.deepEqual(pendingQuestions('thread'), [second])
})

test('damaged or mismatched records block new questions without deleting recoverable data', () => {
  for (const value of ['null', '{broken', JSON.stringify(request('other', 'a', 'Wrong scope')), JSON.stringify(request('thread', 'b', 'Wrong operation'))]) {
    values.clear(); values.set('roleplay:side-pending:thread:a', value)
    assert.throws(() => pendingQuestions('thread'), /cannot be read/)
    assert.equal(values.get('roleplay:side-pending:thread:a'), value)
  }
})

test('recovery drafts are isolated by complete target identity across documents and conversations', () => {
  values.clear()
  const first = { kind: 'side-draft', story_id: 'story', thread_id: 'a' }, second = { ...first, thread_id: 'b' }
  const document = { kind: 'document', story_id: 'story', branch_id: 'branch', purpose: 'composer' }
  for (const [index, target] of [first, second, document].entries()) retainDraft({ id: String(index), target, text: `Copy ${index}`, base: null, savedAt: '2026-09-20' })
  assert.deepEqual(retainedDrafts({ thread_id: 'a', story_id: 'story', kind: 'side-draft' }).map(item => item.text), ['Copy 0'])
  assert.deepEqual(retainedDrafts(second).map(item => item.text), ['Copy 1'])
  assert.deepEqual(retainedDrafts(document).map(item => item.text), ['Copy 2'])
  assert.deepEqual(retainedDrafts({ ...first, story_id: 'other' }), [])
})

test('main workspace and Pop Out follow the same default path while explicit archived sources stay openable', () => {
  const story = { branches: [{ id: 'archived', curation: { archived: true } }, { id: 'active' }] }
  assert.equal(resolveBranch('', story), 'active')
  assert.equal(resolveBranch('archived', story), 'archived')
  assert.equal(resolveBranch('', { branches: [story.branches[0]] }), 'archived')
  assert.equal(resolveBranch('', undefined), '')
})
