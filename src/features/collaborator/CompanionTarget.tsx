import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import { ContextCard } from './ContextCard'
import { useCompanionContext } from './useCompanionContext'
import { useSavedCompanionFocus } from './useSavedCompanionFocus'

export function CompanionTarget({ threadId, branch }: { threadId: string; branch: Branch }) {
  const context = useCompanionContext(threadId), action = useAction()
  const focusError = useSavedCompanionFocus(threadId, context.data)
  return <div className="companion-target-control"><ErrorNotice message={context.error?.message || action.error || focusError} />{context.data?.context ? <ContextCard context={context.data.context} /> : <div className="side-context-badge"><span>Following {branch.name} · revision {branch.revision}</span><small>Each reply keeps the context it started with.</small></div>}
    <div className="companion-context-controls">{context.data?.context ? <button type="button" className="text-button" disabled={action.busy} onClick={() => void action.run(context.follow)}>Follow the active workspace</button> : <button type="button" className="text-button" disabled={action.busy || !context.data} onClick={() => void action.run(() => context.pin({ kind: 'branch', branch_id: branch.id, expected_revision: branch.revision }))}>Pin this telling and revision</button>}{context.error && <button type="button" className="text-button" onClick={() => void context.refetch()}>Refresh target</button>}</div>
  </div>
}
