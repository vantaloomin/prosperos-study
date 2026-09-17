import test from 'node:test'
import assert from 'node:assert/strict'
import { moveSwipe, swipeDirection, swipeOffset, tellingIndex } from '../src/features/generation/tellingSwipe.ts'

const point = (x, y = 0, time = 0, id = 1) => ({ x, y, time, id })
const start = () => ({ start: point(0), points: [point(0)], axis: 'pending' })

test('horizontal previews need deliberate travel; boundaries resist without wrapping', () => {
  const short = moveSwipe(start(), point(-20, 0, 200))
  assert.equal(swipeDirection(short, point(-20, 0, 300), 390), 0)
  const long = moveSwipe(short, point(-100, 3, 400))
  assert.equal(swipeDirection(long, point(-100, 3, 500), 390), 1)
  assert.equal(swipeOffset(-100, 1, 3, 390), -100)
  assert.ok(swipeOffset(100, 0, 3, 390) > 0 && swipeOffset(100, 0, 3, 390) < 36)
  assert.ok(swipeOffset(-100, 2, 3, 390) < 0 && swipeOffset(-100, 2, 3, 390) > -36)
})

test('vertical reading and diagonal intent cannot turn into a horizontal preview', () => {
  let track = moveSwipe(start(), point(9, 14, 40))
  track = moveSwipe(track, point(-160, 25, 100))
  assert.equal(track.axis, 'vertical')
  assert.equal(swipeDirection(track, point(-160, 25, 100), 390), 0)
  assert.equal(moveSwipe(start(), point(12, 10, 30)).axis, 'pending')
})

test('long presses and small taps preserve selection and text-selection intent', () => {
  assert.equal(moveSwipe(start(), point(4, 5, 20)).axis, 'pending')
  const held = moveSwipe(start(), point(-130, 0, 500))
  assert.equal(swipeDirection(held, point(-130, 0, 510), 390), 0)
})

test('a short fast flick is accepted, but a paused or reversed flick is not', () => {
  let track = moveSwipe(start(), point(-35, 2, 40))
  assert.equal(swipeDirection(track, point(-35, 2, 50), 390), 1)
  assert.equal(swipeDirection(track, point(-35, 2, 250), 390), 0)
  track = moveSwipe(track, point(-130, 2, 90))
  track = moveSwipe(track, point(-95, 2, 170))
  assert.equal(swipeDirection(track, point(-95, 2, 175), 390), 0)
})

test('a different pointer cannot move or release an active gesture', () => {
  const track = moveSwipe(start(), point(-100, 0, 60))
  assert.equal(moveSwipe(track, point(180, 0, 80, 2)), track)
  assert.equal(swipeDirection(track, point(-100, 0, 90, 2), 390), 0)
})

test('keyboard navigation stays within the same alternative list', () => {
  assert.equal(tellingIndex('ArrowLeft', 0, 3), 0)
  assert.equal(tellingIndex('ArrowRight', 2, 3), 2)
  assert.equal(tellingIndex('Home', 2, 3), 0)
  assert.equal(tellingIndex('End', 0, 3), 2)
  assert.equal(tellingIndex('ArrowDown', 1, 3), 1)
})
