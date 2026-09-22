import test from 'node:test'
import assert from 'node:assert/strict'
import { DraftController } from '../src/features/textEdits/draftState.ts'

const target = { kind: 'document', story_id: 'story', branch_id: 'branch', purpose: 'composer' }
function fixture(text = '', revision = 0) {
  let current = { ref: target, text, basis: { revision }, version: String(revision), label: 'Draft', limit: 100000 }
  let writes = 0
  const copies = new Map()
  const io = {
    read: async () => structuredClone(current),
    write: async (base, value) => {
      assert.equal(base.version, current.version, 'conflicting write')
      writes++
      current = { ...current, text: value, basis: { revision: current.basis.revision + 1 }, version: String(current.basis.revision + 1) }
      return structuredClone(current)
    },
    copies: () => [...copies.values()], retain: copy => copies.set(copy.id, structuredClone(copy)), remove: id => copies.delete(id),
  }
  return { io, copies, current: () => current, writes: () => writes, controller: id => new DraftController(target, io, id) }
}

test('two writers retain both drafts and require an explicit reviewed save', async () => {
  const f = fixture('Original', 1), a = f.controller('a'), b = f.controller('b')
  await a.refresh(); await b.refresh()
  a.edit('First window'); b.edit('Second window')
  await a.flush()
  await assert.rejects(b.flush(), /Review both/)
  assert.equal(f.current().text, 'First window')
  assert.equal(b.getState().remote.text, 'First window')
  assert.equal(b.getState().text, 'Second window')
  assert.equal(f.copies.get('b').text, 'Second window')
  await b.refresh()
  assert.equal(b.getState().phase, 'conflict')
  b.edit('First window + second window')
  await b.saveReviewed()
  assert.equal(f.current().text, 'First window + second window')
  assert.equal(f.writes(), 2)
})

test('a remote change to a clean view is shown before any dependent action', async () => {
  const f = fixture('Reviewed', 1), a = f.controller('a'), b = f.controller('b')
  await a.refresh(); await b.refresh()
  b.edit('Changed elsewhere'); await b.flush()
  await assert.rejects(a.flush(), /Review its current text/)
  assert.equal(a.getState().text, 'Changed elsewhere')
  assert.equal((await a.flush()).text, 'Changed elsewhere')
  assert.equal(f.writes(), 1)
})

test('typing during a save remains a distinct pending working copy', async () => {
  const f = fixture('Original', 1)
  let release, entered
  const started = new Promise(resolve => { entered = resolve })
  const delayed = new Promise(resolve => { release = resolve })
  const original = f.io.write
  let first = true
  f.io.write = async (...args) => { if (first) { first = false; entered(); await delayed } return original(...args) }
  const a = f.controller('a'); await a.refresh(); a.edit('First keystrokes')
  const saving = a.flush(); await started
  a.edit('Later keystrokes'); release(); await saving
  assert.equal(f.current().text, 'Later keystrokes')
  assert.equal(f.writes(), 2)
  assert.equal(f.copies.size, 0)
})

test('lost save acknowledgement reconciles committed text without replaying', async () => {
  const f = fixture('Original', 1), original = f.io.write
  f.io.write = async (...args) => { await original(...args); throw new Error('Disconnected after commit') }
  const a = f.controller('a'); await a.refresh(); a.edit('Committed')
  await assert.rejects(a.flush(), /Disconnected/)
  assert.equal(a.getState().text, 'Committed')
  assert.equal(a.getState().dirty, false)
  assert.equal((await a.flush()).text, 'Committed')
  assert.equal(f.writes(), 1)
})

test('offline work survives a new view and is reviewed against current saved text', async () => {
  const f = fixture('Original', 1), a = f.controller('a'), read = f.io.read
  await a.refresh(); a.edit('Offline words')
  f.io.read = async () => { throw new Error('Offline') }
  await assert.rejects(a.flush(), /Offline/)
  assert.equal(f.copies.get('a').text, 'Offline words')
  f.io.read = read
  const b = f.controller('b'); await b.refresh()
  assert.equal(b.getState().copies.length, 1)
  b.reviewLocal('a')
  assert.equal(b.getState().phase, 'conflict')
  await b.saveReviewed()
  assert.equal(f.current().text, 'Offline words')
  assert.equal(f.copies.get('a').text, 'Offline words', 'the source recovery might still be active')
})

test('using the saved draft discards only this working copy', async () => {
  const f = fixture('Original', 1), a = f.controller('a'), b = f.controller('b')
  await a.refresh(); await b.refresh(); a.edit('A'); b.edit('B')
  await a.flush(); await b.refresh()
  f.io.retain({ id: 'another', target, text: 'Keep me', base: null, savedAt: '2026-01-01' })
  b.useRemote()
  assert.equal(b.getState().text, 'A')
  assert.equal(f.copies.has('b'), false)
  assert.equal(f.copies.has('another'), true)
})

test('one legacy draft migrates only into a never-saved destination', async () => {
  const f = fixture(), a = f.controller('a')
  f.io.retain({ id: 'legacy:key', target, text: '  Old 🦉 draft.\n', base: null, savedAt: '2026-01-01' })
  await a.refresh(); a.importLegacy(); await a.flush()
  assert.equal(f.current().text, '  Old 🦉 draft.\n')
  assert.equal(f.copies.size, 0)
  f.io.retain({ id: 'legacy:second', target, text: 'Never overwrite', base: null, savedAt: '2026-01-01' })
  const b = f.controller('b'); await b.refresh(); b.importLegacy()
  assert.equal(b.getState().text, '  Old 🦉 draft.\n')
  assert.equal(b.getState().copies.length, 1)
})

test('a second remote change during conflict review still requires a fresh review', async () => {
  const f = fixture('Original', 1), a = f.controller('a'), b = f.controller('b')
  await a.refresh(); await b.refresh(); a.edit('A'); b.edit('B')
  await a.flush(); await b.refresh()
  a.edit('A again'); await a.flush()
  await assert.rejects(b.saveReviewed(), /Review both/)
  assert.equal(f.current().text, 'A again')
  assert.equal(b.getState().text, 'B')
})

test('slow connections do not accumulate a queue of background refreshes', async () => {
  const f = fixture(), original = f.io.read
  let release, reads = 0
  const pending = new Promise(resolve => { release = resolve })
  f.io.read = async () => { reads++; await pending; return original() }
  const a = f.controller('a'), first = a.refresh()
  for (let i = 0; i < 20; i++) assert.equal(a.refresh(), first)
  release(); await first
  assert.equal(reads, 1)
})
