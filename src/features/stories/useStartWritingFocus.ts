import { useEffect, useRef, useState } from 'react'
import type { Selection } from '../../types'

/** Hand off setup focus once the new Story and its editable composer are ready. */
export function useStartWritingFocus(selection: Selection, writing: boolean, creating: boolean) {
  const [started, setStarted] = useState<Selection | null>(null)
  const focused = useRef('')
  useEffect(() => {
    if (!started || !writing || creating || focused.current === started.branchId) return
    if (started.storyId !== selection.storyId || started.branchId !== selection.branchId) return
    const focus = () => {
      if (!focusComposer(started.branchId)) return
      focused.current = started.branchId
      observer.disconnect()
    }
    const observer = new MutationObserver(focus)
    observer.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['disabled'] })
    const frame = requestAnimationFrame(focus)
    return () => { cancelAnimationFrame(frame); observer.disconnect() }
  }, [started, writing, creating, selection.storyId, selection.branchId])
  return setStarted
}

function focusComposer(branchId: string) {
  if (document.querySelector('[role="dialog"]')) return false
  const target = document.querySelector<HTMLTextAreaElement>(`[data-active-branch="${CSS.escape(branchId)}"] [aria-label="Story message"]`)
  if (!target || target.disabled || !target.getClientRects().length) return false
  target.focus()
  return document.activeElement === target
}
