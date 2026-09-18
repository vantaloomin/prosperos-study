import assert from 'node:assert/strict'
import test from 'node:test'
import { composerCopy, composerOptions, composerRole, messageLabels, storyMode } from '../src/features/stories/storyMode.ts'

test('writing and scene composers start as prose while missing/unknown experiences preserve legacy behavior', () => {
  for (const experience of ['directed', 'scene']) {
    const mode = storyMode({ experience })
    assert.equal(composerRole(null, false, mode), 'narrator')
    assert.equal(composerOptions(mode)[0][0], 'narrator')
    assert.equal(messageLabels(mode).assistant, 'Story text')
  }
  for (const settings of [{}, { experience: 'roleplay' }, { experience: [] }]) {
    assert.equal(storyMode(settings), 'roleplay')
    assert.equal(composerRole(null, false, storyMode(settings)), 'user')
  }
})

test('a resumed note or legacy draft cannot silently become narration after navigation or mode changes', () => {
  for (const mode of ['directed', 'scene', 'roleplay']) {
    assert.equal(composerRole('ooc', true, mode), 'ooc')
    assert.equal(composerRole('narrator', true, mode), 'narrator')
    assert.equal(composerRole(null, true, mode), 'user')
    assert.equal(composerRole({ role: 'narrator' }, true, mode), 'user')
  }
  assert.equal(composerCopy('directed', 'ooc').submit, 'Add author’s note')
  assert.equal(messageLabels('roleplay').ooc, 'Out of character')
})
