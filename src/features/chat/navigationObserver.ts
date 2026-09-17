import type { NavigationMetrics } from './navigationMetrics'

/** Observation is bounded to one navigation, with no stored content or task list. */
export function observeNavigation(metrics: NavigationMetrics) {
  const visibility = () => metrics.visibility(document.visibilityState !== 'visible')
  document.addEventListener('visibilitychange', visibility)
  const record = (entries: PerformanceEntry[]) => {
    for (const entry of entries) metrics.longTask(entry.startTime, entry.duration)
  }
  let observer: PerformanceObserver | null = null
  try {
    if (PerformanceObserver.supportedEntryTypes.includes('longtask')) {
      observer = new PerformanceObserver((list) => record(list.getEntries()))
      observer.observe({ type: 'longtask' })
    }
  } catch { observer?.disconnect(); observer = null }
  metrics.supportLongTasks(observer !== null)
  return () => {
    if (observer) record(observer.takeRecords())
    observer?.disconnect()
    document.removeEventListener('visibilitychange', visibility)
  }
}
