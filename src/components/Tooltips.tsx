import { useEffect, useState } from 'react'
import { createPortal } from 'react-dom'

interface Tip { text: string; x: number; y: number; above: boolean }
const tipId = 'workspace-control-tooltip'

function control(event: Event) {
  if (!(event.target instanceof Element)) return null
  const element = event.target.closest<HTMLElement>('button[aria-label], a[aria-label], [data-tooltip]')
  if (element?.innerText?.trim() && !element.dataset.tooltip) return null
  return element
}

/** Shared hover/focus help also covers controls rendered in dialog portals. */
export function Tooltips() {
  const [tip, setTip] = useState<Tip | null>(null)
  useEffect(() => {
    let target: HTMLElement | null = null
    let previous = ''
    let timer = 0
    const close = () => {
      window.clearTimeout(timer)
      if (target) {
        if (previous) target.setAttribute('aria-describedby', previous)
        else target.removeAttribute('aria-describedby')
      }
      target = null
      setTip(null)
    }
    const show = (element: HTMLElement) => {
      close()
      target = element
      previous = element.getAttribute('aria-describedby') ?? ''
      const text = element.dataset.tooltip ?? element.getAttribute('aria-label') ?? ''
      const rect = element.getBoundingClientRect()
      target.setAttribute('aria-describedby', [previous, tipId].filter(Boolean).join(' '))
      const above = rect.bottom > window.innerHeight - 110
      setTip({ text, x: Math.max(12, Math.min(window.innerWidth - 292, rect.left)), y: above ? rect.top - 8 : rect.bottom + 8, above })
    }
    const enter = (event: Event) => {
      const element = control(event)
      if (!element || element === target) return
      window.clearTimeout(timer)
      if (event.type === 'focusin') show(element)
      else timer = window.setTimeout(() => show(element), 350)
    }
    const leave = (event: Event) => {
      const related = (event as PointerEvent).relatedTarget as Node | null
      if (target?.contains(related) || document.getElementById(tipId)?.contains(related)) return
      if (event.type === 'pointerout' && target === document.activeElement) return
      close()
    }
    const escape = (event: KeyboardEvent) => {
      if (event.key !== 'Escape' || !target) return
      event.preventDefault()
      event.stopPropagation()
      close()
    }
    const listeners = { pointerover: enter, focusin: enter, pointerout: leave, focusout: leave, pointerdown: close }
    for (const [name, handler] of Object.entries(listeners)) document.addEventListener(name, handler)
    document.addEventListener('keydown', escape, true)
    window.addEventListener('resize', close)
    document.addEventListener('scroll', close, true)
    return () => {
      close()
      for (const [name, handler] of Object.entries(listeners)) document.removeEventListener(name, handler)
      document.removeEventListener('keydown', escape, true)
      window.removeEventListener('resize', close)
      document.removeEventListener('scroll', close, true)
    }
  }, [])
  return tip && createPortal(<div id={tipId} role="tooltip" className="control-tooltip" style={{ left: tip.x, top: tip.y, transform: tip.above ? 'translateY(-100%)' : undefined }}>{tip.text}</div>, document.body)
}
