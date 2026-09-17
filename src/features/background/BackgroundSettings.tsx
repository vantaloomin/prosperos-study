import { useLayoutEffect, useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { Field } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { BackgroundSummary } from './types'

export function BackgroundSettings({ current, branchId, revision, onBranch, onReveal }: { current: BackgroundSummary; branchId: string; revision: number; onBranch: (id: string) => void; onReveal: (id: string) => void }) {
  const [drives, setDrives] = useState(current.drives_enabled)
  const [hooks, setHooks] = useState(current.hooks_enabled)
  const [day, setDay] = useState(current.day)
  const action = useAction()
  const title = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => {
    const active = document.activeElement
    if (active === document.body || active === title.current?.closest('[role="dialog"]')) title.current?.focus({ preventScroll: true })
  }, [])
  const save = () => action.run(async () => {
    await api(`/branches/${branchId}/background`, { operation_id: operationId(), expected_revision: revision, drives_enabled: drives, hooks_enabled: hooks, day }, 'PUT')
  })
  const reroll = () => action.run(async () => {
    const result = await api<{ branch_id: string }>(`/branches/${branchId}/background`, { operation_id: operationId(), expected_revision: revision, reroll_of: current.id })
    onBranch(result.branch_id)
  })
  const changed = drives !== current.drives_enabled || hooks !== current.hooks_enabled || day !== current.day
  return <div className="form-stack"><div className="prepared-card"><span className="eyebrow">Concealed background</span><h3 ref={title} tabIndex={-1}>Room for a surprise</h3><p>{current.character_count} character preparations · {current.hook_count} hook preparations</p><p className="subtle">Day {current.day} from “{current.origin}”. No-event and excluded results stay empty. Comparisons and retries reuse the recorded draws.</p></div>
    <label className="check-row"><input type="checkbox" checked={drives} disabled={current.character_count === 0} onChange={(event) => setDrives(event.target.checked)} />Use the prepared character drives</label>
    <label className="check-row"><input type="checkbox" checked={hooks} disabled={current.hook_count === 0} onChange={(event) => setHooks(event.target.checked)} />Use the prepared future hooks</label>
    <Field label="Current Story day" type="number" min={0} max={1000000} value={day} onChange={(event) => setDay(Number(event.target.value))} hint="Record an already established day. A due hook is guidance, never an automatic event." />
    <p className="subtle">Saving creates a new setup version from this point. Earlier messages and frozen drafts keep their original setup; pending drafts may become stale.</p>
    <ErrorNotice message={action.error} /><div className="mechanics-footer"><button className="button" disabled={!changed || action.busy} onClick={save}>Save background settings</button><button className="button" onClick={() => onReveal(current.id)}>Reveal background</button></div>
    <details><summary>Try another background</summary><div className="form-stack"><p className="subtle">Creates a new branch at this version’s original preparation point with a fresh seed and the same character and table versions. The current path stays available. Unsaved controls above are not applied.</p><button className="button" disabled={action.busy} onClick={reroll}>Reroll background on a new branch</button></div></details>
  </div>
}
