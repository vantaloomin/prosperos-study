import { publishPersistent } from '../../hooks/usePersistent'
import type { Selection } from '../../types'

export const companionFocusKey = 'roleplay:companion-focus'
export const companionOpenEvent = 'prospero:companion-open'
export function pinCompanionFocus(selection: Selection, threadId: string) {
  publishPersistent(`roleplay:side-thread:${selection.storyId}`, threadId)
  publishPersistent(companionFocusKey, selection)
}
export function followCompanionFocus() { publishPersistent(companionFocusKey, null) }
export function showCompanion(selection: Selection) { window.dispatchEvent(new CustomEvent(companionOpenEvent, { detail: selection })) }
