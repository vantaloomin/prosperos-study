export interface WindowGeometry { left: number; top: number; width: number; height: number; dockWidth: number }
export const defaultGeometry: WindowGeometry = { left: 160, top: 90, width: 580, height: 620, dockWidth: 380 }
const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value))
export function boundedGeometry(value: WindowGeometry, viewport: { width: number; height: number }): WindowGeometry {
  value = Object.fromEntries(Object.entries(defaultGeometry).map(([key, fallback]) => [key, Number.isFinite(value?.[key as keyof WindowGeometry]) ? value[key as keyof WindowGeometry] : fallback])) as unknown as WindowGeometry
  const width = clamp(value.width, Math.min(360, viewport.width - 24), viewport.width - 24)
  const height = clamp(value.height, Math.min(360, viewport.height - 24), viewport.height - 24)
  return { width, height, left: clamp(value.left, 12, viewport.width - width - 12), top: clamp(value.top, 12, viewport.height - height - 12),
    dockWidth: clamp(value.dockWidth, 320, Math.max(320, viewport.width * .55)) }
}
