import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch, StorySummary } from '../../types'
import { defaultMaintenance, type BatchSummary, type MaintenanceSettings, type MaintenanceStatus } from './maintenanceTypes'

export function MaintenancePanel({ branch, onBackfill, onBatch }: { branch: Branch; onBackfill: () => void; onBatch: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const story = useQuery({ queryKey: ['story', branch.story_id], queryFn: () => api<StorySummary>('/stories/' + branch.story_id) })
  const status = useQuery({ queryKey: ['maintenance', branch.id], queryFn: () => api<MaintenanceStatus>('/branches/' + branch.id + '/summary-maintenance'), enabled: open, refetchInterval: open ? 1500 : false })
  return <details open={open} className="advanced-settings" onToggle={event => setOpen(event.currentTarget.open)}><summary>Automatic suggestions & backfill</summary><div className="form-stack authoring-history">
    <ErrorNotice message={story.error?.message || status.error?.message} />
    {story.data && <MaintenanceForm story={story.data} />}
    {status.data && <WaitingStatus branchId={branch.id} status={status.data} />}
    <button className="button" onClick={() => { setOpen(false); onBackfill() }}>Prepare earlier passages</button>
    <p className="subtle">Backfill is a separate, capped request with a preview. Previously requested ranges, including excluded suggestions, are skipped. Retry failed requests in their saved batch.</p>
    {open && <BatchHistory branchId={branch.id} onOpen={id => { setOpen(false); onBatch(id) }} />}
  </div></details>
}

function MaintenanceForm({ story }: { story: StorySummary }) {
  const memory = (story.settings.memory ?? {}) as { mode?: string; maintenance?: MaintenanceSettings }
  const saved = memory.maintenance ?? defaultMaintenance
  const [draft, setDraft] = useState<{ value: MaintenanceSettings; revision: number } | null>(null)
  const value = draft?.value ?? saved
  const action = useAction()
  const patch = (next: Partial<MaintenanceSettings>) => setDraft({ value: { ...value, ...next }, revision: draft?.revision ?? story.revision })
  const save = () => action.run(async () => {
    await api('/stories/' + story.id, { title: story.title, premise: story.premise, expected_revision: draft?.revision ?? story.revision,
      archived: story.archived, settings: { ...story.settings, memory: { ...memory, maintenance: value } } }, 'PUT')
    setDraft(null)
  })
  return <div className="prepared-card form-stack"><h3>After accepted prose</h3>
    <label className="check-row"><input type="checkbox" checked={value.enabled} onChange={event => patch({ enabled: event.target.checked })} />Automatically prepare summary suggestions for this Story</label>
    <p className="subtle">Uses the saved Story memory summary profile, falling back to Primary Writer. New accepted contributions are grouped after a brief quiet moment. Enabling leaves older history alone. Suggestions still need your review.</p>
    <BatchLimits value={value} onChange={patch} />
    <p>Up to {value.max_batches} model request(s) per grouped update, covering at most {value.max_batches * value.batch_size} excerpts. Smaller model contexts may reduce each batch.</p>
    {memory.mode !== 'long' && <p className="subtle">Automatic work waits until this Story uses Long story mode. Disabling the summary prompt also pauses future dispatch.</p>}
    <ErrorNotice message={action.error} /><button className="button" disabled={action.busy || draft === null} onClick={save}>Save maintenance settings</button>
  </div>
}

export function BatchLimits({ value, onChange }: { value: { batch_size: number; max_batches: number }; onChange: (next: Partial<MaintenanceSettings>) => void }) {
  return <div className="form-grid"><label className="field"><span>Maximum excerpts per batch</span><input type="number" min={1} max={8} value={value.batch_size} onChange={event => onChange({ batch_size: Math.max(1, Math.min(8, Number(event.target.value) || 1)) })} /></label>
    <label className="field"><span>Maximum batches</span><input type="number" min={1} max={4} value={value.max_batches} onChange={event => onChange({ max_batches: Math.max(1, Math.min(4, Number(event.target.value) || 1)) })} /></label>
  </div>
}

function WaitingStatus({ branchId, status }: { branchId: string; status: MaintenanceStatus }) {
  const action = useAction()
  const wake = status.wakeup
  const resume = () => action.run(async () => { await api('/branches/' + branchId + '/summary-maintenance/resume', { operation_id: operationId(), expected_revision: wake!.revision }) })
  if (!wake) return <p className="subtle">No automatic work is waiting on this path.</p>
  const resumable = ['limited', 'paused', 'error', 'interrupted'].includes(wake.status)
  return <div className="prepared-card"><p role="status">Automatic queue: {wake.status} · {status.waiting_contributions} accepted contribution(s) waiting</p>
    <p className="subtle">A contribution can span several excerpt batches. Remaining ranges wait for another accepted update or an explicit request to continue. Stopped and interrupted queues require a resume.</p>
    <ErrorNotice message={wake.error || action.error} />{resumable && <button className="button" disabled={!status.active || !status.waiting_contributions || action.busy} onClick={resume}>Process another capped batch</button>}
  </div>
}

function BatchHistory({ branchId, onOpen }: { branchId: string; onOpen: (id: string) => void }) {
  const [page, setPage] = useState(0)
  const query = useQuery({ queryKey: ['summary-batches', branchId, page], queryFn: () => api<BatchSummary[]>('/branches/' + branchId + '/summary-batches?offset=' + page * 25), refetchInterval: 1500 })
  return <div className="form-stack"><h3>Maintenance on this path</h3><ErrorNotice message={query.error?.message} />
    {query.data?.map(batch => <button className="prompt-row" key={batch.id} onClick={() => onOpen(batch.id)}>{batch.kind === 'automatic' ? 'After accepted prose' : 'Earlier passages'} · {batch.status} · {new Date(batch.created_at).toLocaleString()}</button>)}
    <div className="import-downloads"><button className="button" disabled={!page || query.isFetching} onClick={() => setPage(page - 1)}>Newer batches</button><button className="button" disabled={query.data?.length !== 25 || query.isFetching} onClick={() => setPage(page + 1)}>Older batches</button></div>
  </div>
}
