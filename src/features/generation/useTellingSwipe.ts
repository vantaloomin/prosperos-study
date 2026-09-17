import { useEffect, useRef, useState, type PointerEvent } from 'react'
import { animate, useMotionTemplate, useMotionValue, useReducedMotionConfig } from 'motion/react'
import { moveSwipe, swipeDirection, swipeOffset, swipeVelocity, type SwipePoint, type SwipeTrack } from './tellingSwipe'

function point(event: PointerEvent): SwipePoint {
  return { id: event.pointerId, x: event.clientX, y: event.clientY, time: event.timeStamp }
}

function swipeTarget(event: PointerEvent<HTMLElement>) {
  const target = event.target as HTMLElement
  if (target.closest('button, a, input, textarea, select, summary, [contenteditable="true"]')) return false
  if (event.pointerType === 'mouse') return !!target.closest('.telling-swipe-handle')
  return event.pointerType === 'touch' && !!target.closest('.candidate-prose, .telling-swipe-handle')
}

export function useTellingSwipe(index: number, count: number, identity: string, onMove: (direction: number) => void) {
  const track = useRef<SwipeTrack | null>(null)
  const capture = useRef<{ element: HTMLElement; id: number } | null>(null)
  const origin = useRef(0)
  const x = useMotionValue(0)
  const reduce = useReducedMotionConfig()
  const [hint, setHint] = useState(0)
  const suppressClick = useRef(false)
  const transform = useMotionTemplate`translateX(${x}px)`
  const release = () => {
    const held = capture.current
    capture.current = null
    if (held?.element.hasPointerCapture(held.id)) held.element.releasePointerCapture(held.id)
  }
  const settle = (velocity = 0) => {
    track.current = null
    release()
    setHint(0)
    if (reduce) x.jump(0)
    else animate(x, 0, { type: 'spring', duration: 0.3, bounce: 0, velocity: velocity * 1000 })
  }
  useEffect(() => { track.current = null; release(); x.jump(0); return () => { track.current = null; release(); x.stop() } }, [identity, reduce, x])
  const down = (event: PointerEvent<HTMLDivElement>) => {
    suppressClick.current = false
    if (!event.isPrimary) { settle(); return }
    if (count < 2 || event.button !== 0 || !swipeTarget(event) || !window.getSelection()?.isCollapsed) return
    x.stop()
    origin.current = x.get()
    const start = point(event)
    track.current = { start, points: [start], axis: 'pending' }
  }
  const move = (event: PointerEvent<HTMLDivElement>) => {
    if (!track.current || event.pointerId !== track.current.start.id) return
    const next = moveSwipe(track.current, point(event))
    track.current = next
    if (next.axis !== 'horizontal') return
    event.preventDefault()
    event.currentTarget.setPointerCapture(event.pointerId)
    capture.current = { element: event.currentTarget, id: event.pointerId }
    suppressClick.current = true
    const dx = event.clientX - next.start.x
    const direction = swipeDirection(next, point(event), event.currentTarget.clientWidth)
    setHint(index + direction >= 0 && index + direction < count ? direction : 0)
    if (!reduce) x.set(swipeOffset(origin.current + dx, index, count, event.currentTarget.clientWidth))
  }
  const up = (event: PointerEvent<HTMLDivElement>) => {
    const current = track.current
    if (!current || event.pointerId !== current.start.id) return
    const direction = swipeDirection(current, point(event), event.currentTarget.clientWidth)
    settle(swipeVelocity(current, event.timeStamp))
    if (direction) onMove(direction)
  }
  return { transform, hint, events: { onPointerDown: down, onPointerMove: move, onPointerUp: up,
    onPointerCancel: (event: PointerEvent) => { if (track.current?.start.id === event.pointerId) settle() },
    onLostPointerCapture: (event: PointerEvent) => { if (track.current?.start.id === event.pointerId) settle() },
    onClickCapture: (event: React.MouseEvent) => { if (suppressClick.current && event.detail > 0) { event.preventDefault(); event.stopPropagation(); suppressClick.current = false } },
  } }
}
