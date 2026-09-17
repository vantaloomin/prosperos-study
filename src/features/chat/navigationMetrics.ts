import { addLongTask, parseServerTiming } from './navigationDiagnostics.ts'
import type { LongTaskSummary } from './navigationDiagnostics.ts'

type RenderStage = 'layout' | 'transcript' | 'firstFrame' | 'ready'
type RequestStage = 'headers' | 'parsed'
interface RequestTiming { start: number; headers?: number; parsed?: number; server?: Record<string, number> }
interface NavigationTrace {
  branchId: string
  cached: boolean
  startedAt: number
  hiddenObserved: boolean
  checkpoints: Partial<Record<RenderStage, number>>
  requests: RequestTiming[]
  longTasks: LongTaskSummary | null
}
interface RequestTicket { trace: NavigationTrace; timing: RequestTiming }

/** Relative checkpoints only: no prose, provider inputs, or persisted telemetry. */
export class NavigationMetrics {
  private active: NavigationTrace | null = null

  begin(branchId: string, cached: boolean, now: number, hidden: boolean) {
    this.active = { branchId, cached, startedAt: now, hiddenObserved: hidden, checkpoints: {}, requests: [], longTasks: null }
  }

  current(branchId: string) {
    return this.active?.branchId === branchId ? this.active : null
  }

  request(branchId: string, now: number, hidden: boolean): RequestTicket | null {
    const trace = this.current(branchId)
    if (!trace) return null
    const timing = { start: now - trace.startedAt }
    trace.requests.push(timing)
    trace.hiddenObserved ||= hidden
    return { trace, timing }
  }

  progress(ticket: RequestTicket | null, stage: RequestStage, now: number, hidden: boolean, serverTiming?: string | null) {
    if (!ticket || this.active !== ticket.trace) return
    ticket.timing[stage] = now - ticket.trace.startedAt
    ticket.trace.hiddenObserved ||= hidden
    if (stage === 'headers' && serverTiming) ticket.timing.server = parseServerTiming(serverTiming)
  }

  visibility(hidden: boolean) {
    if (this.active) this.active.hiddenObserved ||= hidden
  }

  supportLongTasks(supported: boolean) {
    if (this.active) this.active.longTasks = supported ? { count: 0, overlapMs: 0, blockingOverlapMs: 0, maxOverlapMs: 0 } : null
  }

  longTask(start: number, duration: number) {
    if (this.active?.longTasks) addLongTask(this.active.longTasks, this.active.startedAt, start, duration)
  }

  mark(trace: NavigationTrace, stage: RenderStage, now: number, hidden: boolean) {
    if (this.active !== trace) return false
    trace.checkpoints[stage] = now - trace.startedAt
    trace.hiddenObserved ||= hidden
    return true
  }

  finish(trace: NavigationTrace) {
    if (this.active !== trace) return null
    this.active = null
    return {
      version: 4, cached: trace.cached, hiddenObserved: trace.hiddenObserved,
      checkpoints: { ...trace.checkpoints }, requests: trace.requests.map((request) => ({ ...request })),
      longTasks: trace.longTasks ? { ...trace.longTasks } : null,
    }
  }
}
