import { useQueryClient } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { ContextCard } from './ContextCard'
import { pinCompanionFocus } from './companionFocus'
import type { ContextHead } from './contextTypes'
import type { SideTurn } from './types'

export function ReplyContext({ turn }: { turn: SideTurn }) {
  const action = useAction(), cache = useQueryClient()
  const pin = () => action.run(async () => {
    const head = await api<ContextHead>(`/side-conversations/${turn.thread_id}/context`)
    const next = await api<ContextHead>(`/side-conversations/${turn.thread_id}/context`, { operation_id: operationId(), expected_revision: head.revision, source: { kind: 'turn', turn_id: turn.id } })
    cache.setQueryData(['side-context', turn.thread_id], next)
    pinCompanionFocus({ storyId: next.context!.story_id, branchId: next.context!.branch.id }, turn.thread_id)
  })
  return <details><summary>Context for this question</summary>{turn.snapshot.pinned_context && <ContextCard context={turn.snapshot.pinned_context} />}<p className="subtle">{turn.snapshot.branch.name} · saved revision {turn.snapshot.branch.revision}. Pinning restores this question’s frozen sources for discussion.</p><button type="button" className="text-button" disabled={action.busy} onClick={() => void pin()}>Pin this earlier context</button><ErrorNotice message={action.error} /></details>
}
