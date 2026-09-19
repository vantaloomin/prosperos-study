import { useQuery } from '@tanstack/react-query'
import { api, ApiError, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { useRecovery } from '../generation/useRecovery'

interface Setting { branch_id: string; enabled: number; version: number; timing: 'before_ready' | 'reading' }
interface Change { operation_id: string; expected_version: number; enabled: boolean; timing?: Setting['timing'] }

export function CleanupToggle({ branchId }: { branchId: string }) {
  const path = `/branches/${branchId}/cleanup`
  const query = useQuery({ queryKey: ['cleanup-setting', branchId], queryFn: () => api<Setting>(path), refetchInterval: 5000 })
  const action = useAction()
  const recovery = useRecovery<Change>(`prospero:cleanup-setting:${branchId}`)
  const execute = async (change: Change) => {
    try {
      const receipt = await api<{ kind: string | null; result: Setting | null }>(`/operations/${change.operation_id}`)
      if (receipt.kind && receipt.kind !== 'cleanup_setting') throw new Error('This saved setting belongs to another action.')
      if (!receipt.result) await api(path, change, 'PUT')
      recovery.store(null)
    } catch (error) {
      if (error instanceof ApiError && [400, 409, 422].includes(error.status)) recovery.store(null)
      throw error
    } finally { await query.refetch() }
  }
  const change = (enabled: boolean, timing = query.data?.timing ?? 'before_ready') => action.run(async () => {
    if (!query.data || recovery.latest()) return
    const request = { operation_id: operationId(), expected_version: query.data.version, enabled, timing }
    recovery.store(request)
    await execute(request)
  })
  return <section className="cleanup-setting" aria-label="Automated cleanup settings" aria-busy={action.busy}>
    <label className="check-row"><input type="checkbox" checked={Boolean(query.data?.enabled)} aria-disabled={action.busy} disabled={!query.data || (Boolean(recovery.pending) && !action.busy)} onChange={event => void change(event.target.checked)} /><span>Automated cleanup</span></label>
    <CleanupTiming setting={query.data} blocked={action.busy || Boolean(recovery.pending)} change={timing => void change(Boolean(query.data?.enabled), timing)} />
    <p className="subtle">Check repeated phrases and polish flagged wording with up to one extra model call per draft. The original stays available.</p>
    <p className="subtle">Applies to new requests on this path. Saved intentional and dismissed wording from this browser is protected at request start. Turning off stops pending cleanup.</p>
    <ErrorNotice message={recovery.problem || action.error || query.error?.message} />
    {recovery.pending && <button className="button" disabled={action.busy} onClick={() => void action.run(() => execute(recovery.pending!))}>Check saved cleanup setting</button>}
  </section>
}

function CleanupTiming({ setting, blocked, change }: { setting?: Setting; blocked: boolean; change: (timing: Setting['timing']) => void }) {
  const timing = setting?.timing ?? 'before_ready'
  return <><label className="field"><span>Cleanup timing</span><select aria-label="Cleanup timing" value={timing} disabled={!setting || blocked} onChange={event => change(event.target.value as Setting['timing'])}><option value="before_ready">Finish before draft is ready</option><option value="reading">While I read</option></select></label>
    {timing === 'reading' ? <p className="subtle">Keep or continue with the original immediately. Cleaned wording appears as a separate choice. Verify interruption in the saved model profile first; otherwise cleanup is skipped. New writing takes priority.</p> : <p className="subtle">The draft becomes ready after cleanup finishes. This timing works with every supported writer connection.</p>}
  </>
}
