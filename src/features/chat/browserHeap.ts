/** Optional Chromium estimate. This is not a process-memory or peak measurement. */
export function heapSnapshot(value: unknown) {
  if (!value || typeof value !== 'object') return null
  const memory = value as Record<string, unknown>
  const { usedJSHeapSize, totalJSHeapSize, jsHeapSizeLimit } = memory
  const valid = [usedJSHeapSize, totalJSHeapSize, jsHeapSizeLimit]
    .every((size) => typeof size === 'number' && Number.isFinite(size) && size > 0)
  return valid ? { usedBytes: usedJSHeapSize as number, allocatedBytes: totalJSHeapSize as number,
    limitBytes: jsHeapSizeLimit as number } : null
}

export function browserHeap() {
  return heapSnapshot((performance as Performance & { memory?: unknown }).memory)
}
