import assert from 'node:assert/strict'
import test from 'node:test'
import { TranscriptPosition } from '../src/features/chat/readingPosition.ts'

function environment(t, saved) {
  const storage = new Map([['reading:branch', JSON.stringify(saved)]])
  const frames = new Map()
  let nextFrame = 1
  let resize
  const replacements = {
    sessionStorage: { getItem: (key) => storage.get(key) ?? null, setItem: (key, value) => storage.set(key, value) },
    requestAnimationFrame: (callback) => { const id = nextFrame++; frames.set(id, callback); return id },
    cancelAnimationFrame: (id) => frames.delete(id),
    window: { addEventListener() {}, removeEventListener() {} },
    ResizeObserver: class {
      constructor(callback) { resize = callback }
      observe() {}
      unobserve() {}
      disconnect() {}
    },
  }
  for (const [key, value] of Object.entries(replacements)) {
    const original = Object.getOwnPropertyDescriptor(globalThis, key)
    Object.defineProperty(globalThis, key, { value, writable: true, configurable: true })
    t.after(() => { if (original) Object.defineProperty(globalThis, key, original); else delete globalThis[key] })
  }
  return { resize: () => resize(), saved: () => JSON.parse(storage.get('reading:branch')) }
}

function transcript() {
  const listeners = new Map()
  const element = {
    scrollTop: 0, scrollHeight: 10000, clientHeight: 500, firstElementChild: {},
    getBoundingClientRect: () => ({ top: 0 }),
    addEventListener: (event, callback) => listeners.set(event, callback),
    removeEventListener: (event) => listeners.delete(event),
  }
  const anchors = [1000, 2000, 3000].map((top, index) => ({
    top, height: 400, dataset: { readingAnchor: `passage-${index}` },
    getBoundingClientRect() { return { top: this.top - element.scrollTop, bottom: this.top + this.height - element.scrollTop, height: this.height } },
  }))
  const messages = anchors.map((anchor) => ({ getBoundingClientRect: () => anchor.getBoundingClientRect(), querySelectorAll: () => [anchor] }))
  element.querySelectorAll = (selector) => selector === '.message' ? messages : anchors
  return { element, anchors, scroll: () => listeners.get('scroll')() }
}

const position = { block: 'passage-1', offset: 200, fraction: 0.5, pixels: 2200, atEnd: false }

test('restoration retains the intended passage through deferred layout and its own scroll events', (t) => {
  const browser = environment(t, position)
  const view = transcript()
  const controller = new TranscriptPosition(view.element, 'branch')
  assert.equal(view.element.scrollTop, 2200)
  // Contained prose expands before the programmatic scroll event is delivered.
  view.anchors[1].top += 600
  view.anchors[1].height = 800
  view.scroll()
  browser.resize()
  assert.equal(view.element.scrollTop, 3000)
  view.scroll()
  controller.dispose()
  assert.equal(browser.saved().block, 'passage-1')
  assert.equal(browser.saved().fraction, 0.5)
})

test('a reader scroll supersedes restoration and survives later reflow', (t) => {
  const browser = environment(t, position)
  const view = transcript()
  const controller = new TranscriptPosition(view.element, 'branch')
  view.element.scrollTop = 3100
  view.scroll()
  view.anchors[2].height = 800
  browser.resize()
  assert.equal(view.element.scrollTop, 3200)
  view.scroll()
  controller.dispose()
  assert.equal(browser.saved().block, 'passage-2')
  assert.equal(browser.saved().fraction, 0.25)
})

test('a new end-following transcript stays at the end until the reader scrolls away', (t) => {
  const browser = environment(t, null)
  const view = transcript()
  const controller = new TranscriptPosition(view.element, 'branch')
  assert.equal(view.element.scrollTop, 10000)
  view.scroll()
  view.element.scrollHeight = 12000
  browser.resize()
  assert.equal(view.element.scrollTop, 12000)
  view.element.scrollTop = 2100
  view.scroll()
  browser.resize()
  assert.equal(view.element.scrollTop, 2100)
  controller.dispose()
  assert.equal(browser.saved().block, 'passage-1')
})


test('reading a cited source persists the explicit target through dock-close reflow', (t) => {
  const browser = environment(t, position), view = transcript()
  const controller = new TranscriptPosition(view.element, 'branch')
  controller.seek({ block: 'passage-0', offset: 0, fraction: 0, pixels: 0, atEnd: false })
  assert.equal(view.element.scrollTop, 1000)
  assert.equal(browser.saved().block, 'passage-0')
  view.anchors[0].top = 700
  browser.resize()
  assert.equal(view.element.scrollTop, 700)
  view.scroll()
  controller.dispose()
  assert.equal(browser.saved().block, 'passage-0')
})
