export interface SwipePoint { id: number; x: number; y: number; time: number }
type Axis = 'pending' | 'horizontal' | 'vertical'
export interface SwipeTrack { start: SwipePoint; points: SwipePoint[]; axis: Axis }

export function moveSwipe(track: SwipeTrack, point: SwipePoint): SwipeTrack {
  if (point.id !== track.start.id) return track
  const dx = point.x - track.start.x
  const dy = point.y - track.start.y
  const axis = swipeAxis(track, dx, dy, point.time)
  const points = [...track.points, point].filter((item) => point.time - item.time <= 100).slice(-8)
  return { ...track, axis, points }
}

function swipeAxis(track: SwipeTrack, dx: number, dy: number, time: number): Axis {
  if (track.axis !== 'pending') return track.axis
  if (time - track.start.time > 450) return 'vertical'
  if (Math.max(Math.abs(dx), Math.abs(dy)) < 10) return 'pending'
  if (Math.abs(dx) > Math.abs(dy) * 1.35) return 'horizontal'
  if (Math.abs(dy) >= Math.abs(dx)) return 'vertical'
  return 'pending'
}

export function swipeVelocity(track: SwipeTrack, time: number) {
  const points = track.points.filter((point) => time - point.time <= 100)
  if (points.length < 2) return 0
  const first = points[0], last = points[points.length - 1]
  return (last.x - first.x) / Math.max(1, last.time - first.time)
}

export function swipeDirection(track: SwipeTrack, point: SwipePoint, width: number): number {
  if (point.id !== track.start.id || track.axis !== 'horizontal') return 0
  const dx = point.x - track.start.x
  const velocity = swipeVelocity(track, point.time)
  if (velocity * dx < 0 && Math.abs(velocity) > 0.25) return 0
  const threshold = Math.min(96, Math.max(48, width * 0.22))
  const deliberate = Math.abs(dx) >= threshold
  const flick = Math.abs(dx) >= 28 && Math.abs(velocity) >= 0.55 && Math.abs(dx + velocity * 120) >= threshold
  return deliberate || flick ? -Math.sign(dx) : 0
}

export function swipeOffset(dx: number, index: number, count: number, width: number) {
  const blocked = dx > 0 ? index === 0 : index === count - 1
  if (!blocked) return Math.max(-width, Math.min(width, dx))
  return dx * 36 / (36 + Math.abs(dx))
}

export function tellingIndex(key: string, index: number, count: number) {
  const destinations: Record<string, number> = { ArrowLeft: index - 1, ArrowRight: index + 1, Home: 0, End: count - 1 }
  const next = destinations[key]
  return next === undefined ? index : Math.max(0, Math.min(count - 1, next))
}
