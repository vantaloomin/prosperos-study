import assert from 'node:assert/strict'
import test from 'node:test'
import { NavigationMetrics } from '../src/features/chat/navigationMetrics.ts'

test('uncached navigation records relative request, parse, layout and frame checkpoints', () => {
  const metrics = new NavigationMetrics()
  metrics.begin('a', false, 100, false)
  const trace = metrics.current('a')
  const ticket = metrics.request('a', 110, false)
  metrics.progress(ticket, 'headers', 150, false)
  metrics.progress(ticket, 'parsed', 180, false)
  metrics.mark(trace, 'layout', 400, false)
  metrics.mark(trace, 'transcript', 410, false)
  metrics.mark(trace, 'firstFrame', 420, false)
  metrics.mark(trace, 'ready', 440, false)
  assert.deepEqual(metrics.finish(trace), {
    version: 4, cached: false, hiddenObserved: false, longTasks: null,
    checkpoints: { layout: 300, transcript: 310, firstFrame: 320, ready: 340 },
    requests: [{ start: 10, headers: 50, parsed: 80 }],
  })
  assert.equal(metrics.current('a'), null)
})

test('A to B to A cannot attribute stale requests or frames to the new visit', () => {
  const metrics = new NavigationMetrics()
  metrics.begin('a', false, 0, false)
  const old = metrics.current('a')
  const ticket = metrics.request('a', 10, false)
  metrics.begin('b', false, 20, false)
  assert.equal(metrics.request('a', 30, false), null)
  metrics.begin('a', true, 40, false)
  const current = metrics.current('a')
  metrics.progress(ticket, 'parsed', 50, true)
  assert.equal(metrics.mark(old, 'ready', 60, true), false)
  assert.equal(metrics.finish(old), null)
  metrics.mark(current, 'ready', 70, false)
  assert.deepEqual(metrics.finish(current), {
    version: 4, cached: true, hiddenObserved: false, longTasks: null,
    checkpoints: { ready: 30 }, requests: [],
  })
})

test('concurrent or retried requests retain independent spans and snapshots freeze at readiness', () => {
  const metrics = new NavigationMetrics()
  metrics.begin('a', true, 100, false)
  const trace = metrics.current('a')
  const first = metrics.request('a', 110, false)
  const second = metrics.request('a', 120, false)
  metrics.progress(second, 'headers', 130, false)
  metrics.progress(first, 'headers', 140, false)
  metrics.progress(second, 'parsed', 150, false)
  metrics.mark(trace, 'ready', 160, false)
  const snapshot = metrics.finish(trace)
  metrics.progress(first, 'parsed', 200, true)
  assert.deepEqual(snapshot.requests, [{ start: 10, headers: 40 }, { start: 20, headers: 30, parsed: 50 }])
  assert.equal(snapshot.hiddenObserved, false)
  assert.equal(metrics.finish(trace), null)
})

test('hidden-page observations remain visible in the measurement without inventing missing spans', () => {
  const metrics = new NavigationMetrics()
  metrics.begin('a', true, 100, false)
  const trace = metrics.current('a')
  metrics.progress(null, 'headers', 110, true)
  metrics.mark(trace, 'layout', 120, true)
  metrics.mark(trace, 'ready', 140, false)
  const result = metrics.finish(trace)
  assert.equal(result.hiddenObserved, true)
  assert.equal(result.checkpoints.firstFrame, undefined)
  assert.deepEqual(result.requests, [])
})

test('server timings are numeric allowlisted phases tied to their request ticket', () => {
  const metrics = new NavigationMetrics()
  metrics.begin('a', false, 100, false)
  const ticket = metrics.request('a', 110, false)
  metrics.progress(ticket, 'headers', 250, false, 'path;dur=82.500, serialize;dur=29, prose;dur=1, total;dur=-1, lookup;dur=bad')
  metrics.mark(metrics.current('a'), 'ready', 500, false)
  assert.deepEqual(metrics.finish(metrics.current('a')).requests[0].server, { path: 82.5, serialize: 29 })
  metrics.begin('a', false, 600, false)
  metrics.progress(ticket, 'headers', 700, false, 'path;dur=9')
  assert.deepEqual(metrics.finish(metrics.current('a')).requests, [])
})

test('visibility changes between checkpoints and task overlap survive until readiness only', () => {
  const metrics = new NavigationMetrics()
  metrics.begin('a', true, 100, false)
  metrics.supportLongTasks(true)
  metrics.visibility(true)
  metrics.visibility(false)
  metrics.longTask(20, 60) // Finished before selection.
  metrics.longTask(50, 120) // Only 70 ms overlaps this navigation.
  metrics.longTask(200, 80)
  metrics.mark(metrics.current('a'), 'ready', 300, false)
  const result = metrics.finish(metrics.current('a'))
  assert.equal(result.hiddenObserved, true)
  assert.deepEqual(result.longTasks, { count: 2, overlapMs: 150, blockingOverlapMs: 100, maxOverlapMs: 80 })
  metrics.longTask(400, 200)
  metrics.visibility(true)
  assert.equal(result.longTasks.count, 2)
  metrics.begin('b', true, 700, false)
  metrics.supportLongTasks(false)
  assert.equal(metrics.finish(metrics.current('b')).longTasks, null)
})
