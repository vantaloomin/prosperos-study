import { useState } from 'react'
import { usePersistent } from '../../hooks/usePersistent'
import { composerRole, type StoryMode } from '../stories/storyMode'

export function useComposerDraft(branchId: string, mode: StoryMode) {
  const [text, setText] = usePersistent(`roleplay:draft:${branchId}`, '')
  const [savedRole, setRole] = usePersistent<unknown>(`roleplay:draft-role:${branchId}`, null)
  // Older drafts stored text only, while their composer always started as "user".
  const [legacyDraft] = useState(() => text.length > 0)
  const role = composerRole(savedRole, legacyDraft, mode)
  const edit = (next: string) => { setRole(role); setText(next) }
  return { text, role, edit, setRole, clear: () => setText('') }
}
