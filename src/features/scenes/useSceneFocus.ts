import { useEffect, useRef } from 'react'

export function useSceneFocus(change: string) {
  const panel = useRef<HTMLElement>(null)
  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      const active = document.activeElement
      if (active === document.body || active?.getAttribute('role') === 'dialog') {
        panel.current?.focus({ preventScroll: true })
        panel.current?.scrollIntoView({ block: 'nearest' })
      }
    })
    return () => cancelAnimationFrame(frame)
  }, [change])
  return panel
}
