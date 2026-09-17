const serverPhases = new Set(['lookup', 'path', 'attachments', 'mechanics', 'close', 'serialize', 'total'])

/** Our fixed numeric timing fields only, never arbitrary header descriptions. */
export function parseServerTiming(header?: string | null) {
  const phases: Record<string, number> = {}
  for (const field of (header ?? '').split(',')) {
    const match = /^\s*(\w+);dur=(\d+(?:\.\d+)?)\s*$/.exec(field)
    if (!match || !serverPhases.has(match[1])) continue
    const duration = Number(match[2])
    if (Number.isFinite(duration)) phases[match[1]] = duration
  }
  return Object.keys(phases).length ? phases : undefined
}

export interface LongTaskSummary {
  count: number
  overlapMs: number
  blockingOverlapMs: number
  maxOverlapMs: number
}

export function addLongTask(summary: LongTaskSummary, navigationStart: number, taskStart: number, duration: number) {
  const end = taskStart + duration
  const overlap = end - Math.max(navigationStart, taskStart)
  if (!Number.isFinite(overlap) || overlap <= 0) return
  summary.count += 1
  summary.overlapMs += overlap
  summary.blockingOverlapMs += Math.max(0, end - Math.max(navigationStart, taskStart + 50))
  summary.maxOverlapMs = Math.max(summary.maxOverlapMs, overlap)
}
