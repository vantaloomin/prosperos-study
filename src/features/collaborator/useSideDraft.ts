import { useEffect, useMemo } from 'react'
import { api, operationId } from '../../api'
import { DraftController, type DraftSnapshot } from '../textEdits/draftState'
import { legacyText, retainedDrafts, retainDraft, removeDraft, retainLegacy } from '../textEdits/draftStorage'
import { useDraftSession } from '../textEdits/useDraftSession'

export interface SideDraftTarget { kind: 'side-draft'; story_id: string; thread_id: string }
export interface SideDraftSnapshot extends DraftSnapshot { ref: SideDraftTarget }

export function useSideDraft(storyId: string, threadId: string) {
  const controller = useMemo(() => {
    const ref: SideDraftTarget = { kind: 'side-draft', story_id: storyId, thread_id: threadId }
    const endpoint = `/side-conversations/${threadId}/draft`
    return new DraftController<SideDraftTarget, SideDraftSnapshot>(ref, {
      read: async () => {
        const result = await api<SideDraftSnapshot>(endpoint)
        if (result.ref.story_id !== storyId) throw new Error('This conversation belongs to another Story. Choose a conversation from this Story.')
        return result
      },
      write: (base, text) => api<SideDraftSnapshot>(endpoint, { expected_version: base.version, text }, 'PUT'),
      retain: retainDraft, remove: removeDraft, copies: () => retainedDrafts<SideDraftTarget, SideDraftSnapshot>(ref),
    }, operationId())
  }, [storyId, threadId])
  useEffect(() => {
    const key = `roleplay:side-draft:${threadId}`
    try { retainLegacy(controller.target, key, legacyText(key), () => localStorage.removeItem(key)) } catch { /* Retain the old slot if recovery storage is unavailable. */ }
  }, [controller, threadId])
  return useDraftSession(controller)
}
