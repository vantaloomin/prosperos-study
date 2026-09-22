import { useEffect, useState } from 'react'
import { companionFocusKey, followCompanionFocus, pinCompanionFocus } from './companionFocus'
import type { ContextHead } from './contextTypes'

// A conversation's persisted head is authoritative after restore or selection.
// Local focus only remembers which Story to keep open across workspace changes.
export function useSavedCompanionFocus(threadId: string, head: ContextHead | undefined) {
  const [error, setError] = useState('')
  useEffect(() => {
    if (!head) return
    // Cancel a superseded conversation before publishing its window focus.
    const frame = requestAnimationFrame(() => {
      try {
        const selection = head.context ? { storyId: head.context.story_id, branchId: head.context.branch.id } : null
        if (localStorage.getItem(companionFocusKey) !== JSON.stringify(selection)) {
          if (selection) pinCompanionFocus(selection, threadId)
          else followCompanionFocus()
        }
        setError('')
      } catch { setError('The saved target is available, but this browser could not retain its Story focus. Check browser storage before switching Stories.') }
    })
    return () => cancelAnimationFrame(frame)
  }, [head, threadId])
  return error
}
