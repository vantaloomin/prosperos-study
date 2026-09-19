import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'

interface Capability { supported: boolean; verified: boolean; blocked: boolean; reason: string; measurement?: { cancellation_seconds: number; followup_seconds: number } | null }

export function BackgroundVerification({ profileId, dirty }: { profileId: string; dirty: boolean }) {
  const query = useQuery({ queryKey: ['background-capability', profileId], queryFn: () => api<Capability>(`/profiles/${profileId}/background-capability`), refetchInterval: 30000 })
  const action = useAction()
  const verify = () => action.run(async () => {
    try { await api(`/profiles/${profileId}/verify-background`, {}) }
    finally { await query.refetch() }
  })
  const reset = () => action.run(async () => {
    await api(`/profiles/${profileId}/reset-background`, { server_restarted: true })
    await query.refetch()
  })
  return <section aria-label="Background interruption check" className="form-stack">
    <p>Cleanup while reading</p><p className="subtle" role="status">{query.data?.reason ?? 'Checking the saved connection…'}</p>
    <VerificationActions capability={query.data} disabled={dirty || action.busy} busy={action.busy} verify={() => void verify()} reset={() => void reset()} />
    {dirty && <p className="subtle">Save your profile changes, then reopen it to check the saved connection.</p>}
    <ErrorNotice message={action.error || query.error?.message} />
  </section>
}

function VerificationActions({ capability, disabled, busy, verify, reset }: { capability?: Capability; disabled: boolean; busy: boolean; verify: () => void; reset: () => void }) {
  if (!capability) return null
  return <>
    {capability.supported && !capability.blocked && <><p className="subtle">Run two short test requests with the loaded model: stop the first and confirm another request completes. No story text is sent. Verification lasts 30 minutes in this app session.</p><button className="button" disabled={disabled} onClick={verify}>{busy ? 'Checking interruption…' : 'Verify background interruption'}</button></>}
    {capability.blocked && <button className="button" disabled={disabled} onClick={reset}>I restarted the model server; reset check</button>}
    {capability.measurement && <p className="subtle">Observed stop acknowledgement: {capability.measurement.cancellation_seconds.toFixed(2)}s. Follow-up request: {capability.measurement.followup_seconds.toFixed(2)}s.</p>}
  </>
}
