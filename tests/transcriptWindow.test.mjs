import assert from 'node:assert/strict'
import test from 'node:test'
import { findPassages, hasReadingAnchor, initialMessageIndex, passagePosition } from '../src/features/chat/transcriptWindow.ts'
import { VirtualReadingPosition } from '../src/features/chat/VirtualReadingPosition.ts'
import { PassageNavigation } from '../src/features/chat/passageNavigation.ts'
import { heapSnapshot } from '../src/features/chat/browserHeap.ts'

test('unsupported or malformed heap estimates remain unknown, not zero', () => {
  assert.equal(heapSnapshot(undefined), null)
  assert.equal(heapSnapshot({ usedJSHeapSize: 12 }), null)
  assert.equal(heapSnapshot({ usedJSHeapSize: NaN, totalJSHeapSize: 32, jsHeapSizeLimit: 64 }), null)
  assert.deepEqual(heapSnapshot({ usedJSHeapSize: 12, totalJSHeapSize: 32, jsHeapSizeLimit: 64 }),
    { usedBytes: 12, allocatedBytes: 32, limitBytes: 64 })
})

test('full-history search and direct navigation reach text outside the rendered window', () => {
  const messages = Array.from({ length: 10000 }, (_, index) => ({ id: `m${index}`, text: `Passage ${index}. Rain on the quay.` }))
  messages[9482].text = 'A silver lantern. 雨'
  assert.deepEqual(findPassages(messages, 'SILVER lantern'), [9482])
  assert.deepEqual(findPassages(messages, '雨'), [9482])
  assert.deepEqual(findPassages(messages, '10000'), [9999])
  assert.deepEqual(findPassages(messages, '10001'), [])
  assert.deepEqual(findPassages(messages, '0'), [])
  assert.equal(findPassages(messages, '').length, 10000)
  assert.equal(initialMessageIndex(messages, passagePosition('m9482')), 9482)
  assert.equal(initialMessageIndex(messages, null), 9999)
})

test('initial positioning tolerates missing legacy anchors and empty paths', () => {
  assert.equal(initialMessageIndex([], null), 0)
  assert.equal(initialMessageIndex([{ id: 'one' }], { ...passagePosition('missing'), pixels: 9000 }), 0)
  assert.equal(initialMessageIndex([{ id: 'one' }, { id: 'two' }], { ...passagePosition('one'), atEnd: true }), 1)
  assert.equal(hasReadingAnchor([{ id: 'one', text: 'First\n\nSecond' }], 'one:p1'), true)
  assert.equal(hasReadingAnchor([{ id: 'one', text: 'First' }], 'one:p9'), false)
  assert.equal(hasReadingAnchor([{ id: 'one', text: 'First' }], 'missing:header'), false)
})

function browser(t, saved) {
  const storage = new Map([['reading:branch', JSON.stringify(saved)]])
  const frames = new Map()
  let next = 1
  const observers = { resize: null, mutation: null }
  const replaced = {
    getComputedStyle: (element) => ({ visibility: element.visibility ?? 'visible' }),
    sessionStorage: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    requestAnimationFrame: (callback) => { const id = next++; frames.set(id, callback); return id },
    cancelAnimationFrame: (id) => frames.delete(id),
    window: { addEventListener() {}, removeEventListener() {} },
    ResizeObserver: class { constructor(callback) { observers.resize = callback } observe() {} disconnect() {} },
    MutationObserver: class { constructor(callback) { observers.mutation = callback } observe() {} disconnect() {} },
  }
  for (const [key, value] of Object.entries(replaced)) {
    const original = Object.getOwnPropertyDescriptor(globalThis, key)
    Object.defineProperty(globalThis, key, { value, configurable: true })
    t.after(() => { if (original) Object.defineProperty(globalThis, key, original); else delete globalThis[key] })
  }
  return { observers, saved: () => JSON.parse(storage.get('reading:branch')), frames,
    tick: () => { const pending = [...frames.values()]; frames.clear(); for (const callback of pending) callback() } }
}

function view() {
  const listeners = new Map()
  const element = { scrollTop: 0, scrollHeight: 20000, clientHeight: 500, clientWidth: 700, dataset: {},
    getBoundingClientRect: () => ({ top: 0 }), addEventListener: (key, fn) => listeners.set(key, fn),
    removeEventListener: (key) => listeners.delete(key) }
  const anchors = [1000, 2000, 3000].map((top, index) => ({ top, height: 400, dataset: { readingAnchor: `m${index}:header` },
    getBoundingClientRect() { return { top: this.top - element.scrollTop, bottom: this.top + this.height - element.scrollTop, height: this.height } } }))
  const rendered = { indices: [0, 1, 2], visibility: 'visible' }
  element.querySelectorAll = (selector) => rendered.indices.map((index) => selector === '.message'
    ? { visibility: rendered.visibility, getBoundingClientRect: () => anchors[index].getBoundingClientRect(), querySelectorAll: () => [anchors[index]] }
    : anchors[index])
  return { element, anchors, rendered, listeners, emit: (key, event) => listeners.get(key)?.(event) }
}

test('an offscreen saved paragraph is retained until its window mounts', (t) => {
  const saved = { ...passagePosition('m1'), offset: 200, fraction: 0.5, pixels: 2200 }
  const environment = browser(t, saved)
  const page = view()
  page.rendered.indices = [0]
  const controller = new VirtualReadingPosition(page.element, 'branch', 'm2')
  environment.tick()
  assert.notEqual(page.element.dataset.transcriptReady, 'true')
  page.rendered.indices = [1, 2]
  environment.observers.mutation()
  environment.tick()
  environment.tick()
  assert.equal(page.element.scrollTop, 2200)
  assert.equal(page.element.dataset.transcriptReady, 'true')
  controller.dispose()
  assert.deepEqual(environment.saved(), saved)
})

test('reader scrolling replaces the anchor and resize preserves its paragraph fraction', (t) => {
  const environment = browser(t, passagePosition('m1'))
  const page = view()
  const controller = new VirtualReadingPosition(page.element, 'branch', 'm2')
  environment.tick()
  page.emit('wheel')
  page.element.scrollTop = 3100
  page.emit('scroll')
  environment.tick()
  assert.equal(environment.saved().block, 'm2:header')
  assert.equal(environment.saved().fraction, 0.25)
  page.anchors[2].top = 5000
  page.anchors[2].height = 800
  page.element.clientWidth = 350
  environment.observers.resize()
  environment.tick()
  assert.equal(page.element.scrollTop, 5200)
  controller.dispose()
  assert.equal(page.listeners.size, 0)
  assert.equal(environment.frames.size, 0)
})

test('an interim empty or nonvisible window cannot overwrite the last real reading anchor', (t) => {
  const saved = passagePosition('m1')
  const environment = browser(t, saved)
  const page = view()
  const controller = new VirtualReadingPosition(page.element, 'branch', 'm2')
  environment.tick()
  page.emit('keydown', { key: 'End' })
  page.rendered.indices = [0]
  page.element.scrollTop = 12000
  page.emit('scroll')
  environment.tick()
  controller.dispose()
  assert.deepEqual(environment.saved(), saved)
})

test('explicit passage selection does not reuse a previous scroll offset', (t) => {
  const environment = browser(t, null)
  const page = view()
  const controller = new VirtualReadingPosition(page.element, 'branch', 'm2')
  environment.tick()
  controller.seek(passagePosition('m0'))
  environment.tick()
  assert.equal(page.element.scrollTop, 1000)
  assert.equal(environment.saved().block, 'm0:header')
  controller.dispose()
})

test('an invalid old paragraph anchor falls back without waiting forever for a nonexistent element', (t) => {
  const environment = browser(t, { ...passagePosition('removed'), pixels: 2000 })
  const page = view()
  const controller = new VirtualReadingPosition(page.element, 'branch', 'm2', () => false)
  environment.tick()
  environment.tick()
  assert.equal(page.element.scrollTop, 2000)
  assert.equal(page.element.dataset.transcriptReady, 'true')
  controller.dispose()
})

test('measurement-driven window replacement remounts the saved passage before declaring readiness', (t) => {
  const saved = passagePosition('m1')
  const environment = browser(t, saved)
  const page = view()
  const requested = []
  const controller = new VirtualReadingPosition(page.element, 'branch', 'm2', undefined, (position) => requested.push(position))
  environment.tick()
  environment.tick()
  assert.equal(page.element.dataset.transcriptReady, 'true')
  page.rendered.indices = [0]
  environment.observers.mutation()
  environment.tick()
  assert.equal(page.element.dataset.transcriptReady, 'false')
  assert.deepEqual(requested, [saved])
  assert.deepEqual(environment.saved(), saved)
  page.rendered.indices = [1, 2]
  environment.observers.mutation()
  environment.tick()
  environment.tick()
  assert.equal(page.element.dataset.transcriptReady, 'true')
  assert.equal(page.element.dataset.readingTarget, 'm1:header')
  assert.equal(page.element.scrollTop, 2000)
  controller.dispose()
})


test('mounted but hidden prose is not ready and cannot replace the saved reading anchor', (t) => {
  const saved = passagePosition('m1')
  const environment = browser(t, saved)
  const page = view()
  page.rendered.visibility = 'hidden'
  const controller = new VirtualReadingPosition(page.element, 'branch', 'm2')
  environment.tick()
  environment.tick()
  assert.notEqual(page.element.dataset.transcriptReady, 'true')
  page.emit('wheel')
  page.element.scrollTop = 3100
  page.emit('scroll')
  environment.tick()
  environment.tick()
  assert.deepEqual(environment.saved(), saved)
  page.rendered.visibility = 'visible'
  environment.observers.mutation()
  environment.tick()
  environment.tick()
  assert.equal(page.element.dataset.transcriptReady, 'true')
  assert.equal(environment.saved().block, 'm2:header')
  controller.dispose()
})

test('a list hidden between positioning and the ready frame must wait for visible prose', (t) => {
  const environment = browser(t, passagePosition('m1'))
  const page = view()
  const controller = new VirtualReadingPosition(page.element, 'branch', 'm2')
  environment.tick()
  page.rendered.visibility = 'hidden'
  environment.tick()
  assert.notEqual(page.element.dataset.transcriptReady, 'true')
  page.rendered.visibility = 'visible'
  environment.observers.mutation()
  environment.tick()
  environment.tick()
  assert.equal(page.element.dataset.transcriptReady, 'true')
  page.rendered.indices = [0]
  environment.observers.mutation()
  assert.equal(page.element.dataset.transcriptReady, 'false')
  controller.dispose()
})


test('visibility settling after the last observer notification is checked on a later frame', (t) => {
  const environment = browser(t, passagePosition('m1'))
  const page = view()
  page.rendered.visibility = 'hidden'
  const controller = new VirtualReadingPosition(page.element, 'branch', 'm2')
  environment.tick()
  environment.tick()
  assert.notEqual(page.element.dataset.transcriptReady, 'true')
  page.rendered.visibility = 'visible'
  environment.tick()
  environment.tick()
  assert.equal(page.element.dataset.transcriptReady, 'true')
  controller.dispose()
  assert.equal(environment.frames.size, 0)
})


test('a source request waits for its reader and is delivered once across re-renders', () => {
  const navigation = new PassageNavigation(), seen = []
  const reader = { branchId: 'accepted', show: id => { seen.push(id); return true } }
  navigation.request('accepted', 'earlier-scene')
  navigation.connect(reader)
  navigation.connect(null)
  navigation.connect(reader)
  assert.deepEqual(seen, ['earlier-scene'])
  navigation.request('accepted', 'earlier-scene')
  assert.deepEqual(seen, ['earlier-scene', 'earlier-scene'])
})

test('changing branches cancels an undelivered source request instead of moving another reader', () => {
  const navigation = new PassageNavigation(), seen = []
  navigation.request('old-branch', 'shared-ancestor')
  navigation.connect({ branchId: 'new-branch', show: id => seen.push(id) })
  navigation.connect({ branchId: 'old-branch', show: id => seen.push(id) })
  assert.deepEqual(seen, [])
  navigation.connect({ branchId: 'old-branch', show: () => false })
  assert.equal(navigation.request('old-branch', 'absent-node'), false)
})
