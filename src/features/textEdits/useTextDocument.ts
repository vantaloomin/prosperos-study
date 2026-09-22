import { useMemo } from 'react'
import { api, operationId } from '../../api'
import { DraftController, type DocumentTarget } from './draftState'
import { retainedDrafts, retainDraft, removeDraft } from './draftStorage'
import type { TargetSnapshot } from './types'
import { useDraftSession } from './useDraftSession'

export function useTextDocument(target: DocumentTarget) {
  const { story_id, branch_id, purpose } = target
  const controller = useMemo(() => {
    const ref: DocumentTarget = { kind: 'document', story_id, branch_id, purpose }
    return new DraftController(ref, {
      read: () => api<TargetSnapshot>('/text-targets/read', { target: ref }),
      write: (base, text) => api<TargetSnapshot>('/text-documents/autosave', { target: ref, expected_version: base.version, text }, 'PUT'),
      retain: retainDraft, remove: removeDraft, copies: () => retainedDrafts(ref),
    }, operationId())
  }, [story_id, branch_id, purpose])
  return useDraftSession(controller)
}
