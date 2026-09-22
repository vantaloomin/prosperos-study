import { api } from '../../api'
import type { Branch, Selection, Story } from '../../types'
import { resolveBranch } from '../chat/branchSelection'
import type { TargetSnapshot, TextSelection } from '../textEdits/types'
import type { PreparedContext } from './SendToCompanion'

export async function prepareTextContext(target: TargetSnapshot, selection: TextSelection): Promise<PreparedContext> {
  const story = await api<Story>(`/stories/${target.ref.story_id}`)
  let following: Selection | null = null
  try { following = JSON.parse(localStorage.getItem('roleplay:selection') ?? 'null') as Selection | null } catch { /* Use this Story's default branch. */ }
  const selected = 'branch_id' in target.ref ? target.ref.branch_id : following?.storyId === story.id ? following.branchId : ''
  const branch = await api<Branch>(`/branches/${resolveBranch(selected, story)}`)
  return { storyId: story.id, label: target.label, text: selection.text,
    source: { kind: 'text', branch_id: branch.id, expected_revision: branch.revision, target: target.ref, expected_version: target.version, selection } }
}
