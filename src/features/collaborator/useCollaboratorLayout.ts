import { useEffect, useState, type PointerEvent } from 'react'
import { usePersistent } from '../../hooks/usePersistent'
import { boundedGeometry, defaultGeometry, type WindowGeometry } from './windowGeometry'

export type CollaboratorMode = 'docked' | 'floating' | 'full'
function viewport() { return { width: window.innerWidth, height: window.innerHeight, font: parseFloat(getComputedStyle(document.documentElement).fontSize) } }

export function useCollaboratorLayout() {
  const [mode, setMode] = usePersistent<CollaboratorMode>('roleplay:collaborator-layout', 'docked')
  const [saved, save] = usePersistent('roleplay:collaborator-geometry', defaultGeometry)
  const [size, setSize] = useState(viewport)
  useEffect(() => {
    const resize = () => setSize(viewport())
    const observer = new MutationObserver(resize)
    observer.observe(document.documentElement, { attributes: true, attributeFilter: ['style'] })
    window.addEventListener('resize', resize)
    return () => { observer.disconnect(); window.removeEventListener('resize', resize) }
  }, [])
  const geometry = boundedGeometry(saved, size)
  const compact = size.width < 58 * size.font || size.height < 480
  const presentation = compact ? 'full' : mode
  const patch = (next: Partial<WindowGeometry>) => save(boundedGeometry({ ...geometry, ...next }, size))
  const drag = (event: PointerEvent<HTMLElement>, kind: 'move' | 'resize' | 'dock') => {
    event.preventDefault()
    const element = event.currentTarget, x = event.clientX, y = event.clientY, start = geometry
    element.setPointerCapture(event.pointerId)
    const move = (e: globalThis.PointerEvent) => {
      const dx = e.clientX - x, dy = e.clientY - y
      const delta = kind === 'move' ? { left: start.left + dx, top: start.top + dy } : resizeDelta(kind, start, dx, dy)
      save(boundedGeometry({ ...start, ...delta }, viewport()))
    }
    const stop = () => { element.removeEventListener('pointermove', move); element.removeEventListener('pointerup', stop); element.removeEventListener('pointercancel', stop) }
    element.addEventListener('pointermove', move)
    element.addEventListener('pointerup', stop)
    element.addEventListener('pointercancel', stop)
  }
  return { mode, setMode, presentation, compact, geometry, patch, drag, reset: () => save(boundedGeometry(defaultGeometry, size)) }
}
function resizeDelta(kind: string, start: WindowGeometry, dx: number, dy: number) {
  return kind === 'dock' ? { dockWidth: start.dockWidth - dx } : { width: start.width + dx, height: start.height + dy }
}
