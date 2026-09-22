import { useEffect, useState } from 'react'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch } from '../../types'
import { composerRole, type StoryMode } from '../stories/storyMode'
import { legacyText, retainLegacy } from '../textEdits/draftStorage'
import { useTextDocument } from '../textEdits/useTextDocument'

export function useComposerDraft(branch: Branch, mode: StoryMode) {
  const key = `roleplay:draft:${branch.id}`
  const [legacy] = useState(() => legacyText(key))
  const [savedRole, setRole] = usePersistent<unknown>(`roleplay:draft-role:${branch.id}`, null)
  // Older drafts stored text only, while their composer always started as "user".
  const [legacyRole] = useState(() => composerRole(savedRole, !!legacy, mode))
  const role = composerRole(savedRole, !!legacy, mode)
  const prose = useTextDocument({ kind: 'document', story_id: branch.story_id, branch_id: branch.id, purpose: 'composer' })
  const note = useTextDocument({ kind: 'document', story_id: branch.story_id, branch_id: branch.id, purpose: 'author-note' })
  const draft = role === 'ooc' ? note : prose
  useEffect(() => {
    try {
      retainLegacy({ kind: 'document', story_id: branch.story_id, branch_id: branch.id, purpose: legacyRole === 'ooc' ? 'author-note' : 'composer' }, key, legacyText(key), () => localStorage.removeItem(key))
    } catch { /* Retain the old browser slot if recovery storage is unavailable. */ }
  }, [branch.story_id, branch.id, legacyRole, key])
  const edit = (next: string) => { setRole(role); draft.controller.edit(next) }
  return { ...draft, role, edit, setRole }
}
