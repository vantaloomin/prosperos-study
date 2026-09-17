import { useLayoutEffect } from 'react'
import type { RefObject } from 'react'
import type { Branch } from '../../types'
import { api } from '../../api'
import { NavigationMetrics } from './navigationMetrics'
import { observeNavigation } from './navigationObserver'
import { browserHeap } from './browserHeap'

const metrics = new NavigationMetrics()
const hidden = () => document.visibilityState !== 'visible'
let stopObserving: (() => void) | undefined

export function beginBranchNavigation(branchId: string, cached: boolean) {
  const current = document.querySelector<HTMLElement>('[data-active-branch]')
  if (current?.dataset.activeBranch === branchId) return
  stopObserving?.()
  metrics.begin(branchId, cached, performance.now(), hidden())
  stopObserving = observeNavigation(metrics)
}

export function loadBranch(branchId: string) {
  const ticket = metrics.request(branchId, performance.now(), hidden())
  return api<Branch>(`/branches/${branchId}`, undefined, undefined,
    (stage, serverTiming) => metrics.progress(ticket, stage, performance.now(), hidden(), serverTiming))
}

export function useBranchReadiness(branch: Branch, element: RefObject<HTMLDivElement | null>) {
  useLayoutEffect(() => {
    const start = metrics.current(branch.id)
    if (!start) return
    element.current?.removeAttribute('data-branch-ready-ms')
    element.current?.removeAttribute('data-branch-timing')
    element.current?.removeAttribute('data-branch-heap')
    metrics.mark(start, 'layout', performance.now(), hidden())
    let frame = 0
    const finish = () => {
        if (!element.current?.querySelector('[data-transcript-ready="true"]')) {
          frame = requestAnimationFrame(waitForTranscript)
          return
        }
        if (!element.current || !metrics.mark(start, 'ready', performance.now(), hidden())) return
        stopObserving?.()
        stopObserving = undefined
        const timing = metrics.finish(start)!
        element.current.dataset.branchReadyMs = timing.checkpoints.ready!.toFixed(1)
        element.current.dataset.branchTiming = JSON.stringify(timing)
        element.current.dataset.branchHeap = JSON.stringify(browserHeap())
        element.current.dataset.branchCached = String(start.cached)
        element.current.dataset.branchResponseCount = String(branch.messages.filter((message) => message.role === 'assistant').length)
        element.current.dataset.branchTextCharacters = String(branch.messages.reduce((sum, message) => sum + message.text.length, 0))
        if (document.activeElement === document.body) element.current.querySelector<HTMLButtonElement>('.chat-heading button')?.focus()
    }
    const waitForTranscript = () => {
      if (!element.current?.querySelector('[data-transcript-ready="true"]')) {
        frame = requestAnimationFrame(waitForTranscript)
        return
      }
      metrics.mark(start, 'transcript', performance.now(), hidden())
      frame = requestAnimationFrame(() => {
        metrics.mark(start, 'firstFrame', performance.now(), hidden())
        frame = requestAnimationFrame(finish)
      })
    }
    frame = requestAnimationFrame(waitForTranscript)
    return () => cancelAnimationFrame(frame)
  }, [branch, element])
}
