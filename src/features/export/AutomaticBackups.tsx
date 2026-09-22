import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { Field } from '../../components/Fields'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { ArchiveFile } from './Archives'

interface Settings {
  revision: number; enabled: boolean; interval_minutes: number; keep_count: number
  destination: string; include_sidebar: boolean; next_run_at: string | null; effective_directory: string
}
interface BackupRun {
  id: string; trigger: 'manual' | 'scheduled'; status: 'running' | 'ready' | 'error' | 'interrupted' | 'pruned'
  started_at: string; finished_at: string | null; directory: string; byte_count: number; error: string; available: boolean
  settings: { include_sidebar: boolean }
}
const labels = { running: 'Preparing copy', ready: 'Saved', error: 'Failed', interrupted: 'Interrupted', pruned: 'Removed by retention' }

export function AutomaticBackups({ onReview }: { onReview: (file: ArchiveFile) => void }) {
  const settings = useQuery({ queryKey: ['backup-settings'], queryFn: () => api<Settings>('/backups/settings'), refetchInterval: 30000 })
  const history = useQuery({ queryKey: ['backup-history'], queryFn: () => api<BackupRun[]>('/backups'), refetchInterval: 5000 })
  return <section className="automatic-backups form-stack" aria-label="Automatic backups">
    <div><h3>Automatic backups</h3><p className="subtle">Keep private workspace copies on a schedule while the app server is running. After downtime, one catch-up copy is made. Backups remain off until you enable them.</p></div>
    <ErrorNotice message={settings.error?.message || history.error?.message} />
    {settings.isPending && <Loading label="Loading backup settings…" />}
    {settings.data && <BackupControls current={settings.data} />}
    <BackupHistory runs={history.data ?? []} onReview={onReview} />
  </section>
}

function draftFrom(current: Settings) {
  return { expected_revision: current.revision, enabled: current.enabled, interval_minutes: current.interval_minutes,
    keep_count: current.keep_count, destination: current.destination, include_sidebar: current.include_sidebar }
}

function BackupControls({ current }: { current: Settings }) {
  const [draft, setDraft] = useState(() => draftFrom(current))
  const [notice, setNotice] = useState('')
  const action = useAction()
  const save = () => action.run(async () => {
    const saved = await api<Settings>('/backups/settings', draft, 'PUT')
    setDraft(draftFrom(saved)); setNotice('Backup settings saved.')
  })
  const reload = () => { setDraft(draftFrom(current)); setNotice('Loaded saved settings.'); action.clearError() }
  const stale = current.revision !== draft.expected_revision
  return <div className="form-stack">
    <label className="check-row"><input type="checkbox" checked={draft.enabled} onChange={(event) => setDraft({ ...draft, enabled: event.target.checked })} />Enable scheduled backups</label>
    <div className="backup-fields">
      <Field label="Backup interval (minutes)" type="number" min={15} max={43200} value={draft.interval_minutes} onChange={(event) => setDraft({ ...draft, interval_minutes: Number(event.target.value) })} hint="15 minutes to 30 days. 1,440 minutes is one day." />
      <Field label="Scheduled copies to keep" type="number" min={1} max={365} value={draft.keep_count} onChange={(event) => setDraft({ ...draft, keep_count: Number(event.target.value) })} hint="Per destination; older scheduled copies are removed only after a successful new copy. Manual copies are kept." />
    </div>
    <Field label="Backup destination folder" value={draft.destination} onChange={(event) => setDraft({ ...draft, destination: event.target.value })} placeholder="Default folder beside this workspace" hint="Leave blank for the default. Otherwise enter an existing absolute folder path on this computer or a mounted drive; it must be available to the app server." />
    <label className="check-row"><input type="checkbox" checked={draft.include_sidebar} onChange={(event) => setDraft({ ...draft, include_sidebar: event.target.checked })} />Include private sidebar conversations and saved unsent questions in scheduled and on-demand copies</label>
    <p className="subtle">Credentials are excluded. Backup settings and destination paths stay on this installation and are never activated by restoring a copy.</p>
    {stale && <p role="status">Saved settings changed. Reload them before saving your edits.</p>}
    <ErrorNotice message={action.error} />
    <div className="backup-actions"><button className="button primary" disabled={action.busy || stale} onClick={save}>{action.busy ? 'Saving…' : 'Save backup settings'}</button><button className="button" disabled={action.busy} onClick={reload}>Reload saved settings</button></div>
    {notice && <p role="status">{notice}</p>}
    <div className="backup-saved-state"><p>{current.enabled ? `Next scheduled copy: ${new Date(current.next_run_at!).toLocaleString()}` : 'Scheduled backups are off.'}</p><p className="subtle">Saved destination: <span>{current.effective_directory}</span></p></div>
    <BackupNow current={current} />
  </div>
}

function BackupNow({ current }: { current: Settings }) {
  const action = useAction()
  const pending = useRef<{ operation_id: string; expected_revision: number } | null>(null)
  const [notice, setNotice] = useState('')
  const create = () => action.run(async () => {
    pending.current ??= { operation_id: operationId(), expected_revision: current.revision }
    const run = await api<BackupRun>('/backups', pending.current)
    pending.current = null
    setNotice(run.status === 'ready' ? 'Your copy is saved. Choose Review & recover below to inspect it.' : `${labels[run.status]}. ${run.error}`)
  })
  return <div className="form-stack"><button className="button" disabled={action.busy} onClick={create}>{action.busy ? 'Preparing your copy…' : 'Back up now using saved settings'}</button><small className="subtle">This on-demand copy is kept until you remove its file yourself. Unsaved settings above do not apply.</small><ErrorNotice message={action.error} />{action.error && <button className="button" onClick={() => { pending.current = null; action.clearError() }}>Use current saved settings for a new attempt</button>}{notice && <p role="status">{notice}</p>}</div>
}

function BackupHistory({ runs, onReview }: { runs: BackupRun[]; onReview: (file: ArchiveFile) => void }) {
  const action = useAction()
  const review = (run: BackupRun) => action.run(async () => onReview(await api<ArchiveFile>(`/backups/${run.id}/review`, {})))
  return <div className="backup-history form-stack"><h4>Backup history</h4><p className="subtle">Most recent 100 attempts. Review checks the saved file and prepares a local recovery copy. You can then download it or restore it as new Stories.</p><ErrorNotice message={action.error} />
    {!runs.length && <p className="subtle">No scheduled or on-demand copies yet.</p>}
    {runs.map((run) => <div className="backup-history-row form-stack" key={run.id}>
      <p><strong>{labels[run.status]}</strong> · {run.trigger === 'scheduled' ? 'Scheduled' : 'On demand'} · {new Date(run.started_at).toLocaleString()}</p>
      <small>{run.directory}</small><small>{run.settings.include_sidebar ? 'Includes private sidebar conversations' : 'Sidebar conversations excluded'}{run.byte_count > 0 && ` · ${(run.byte_count / 1024 / 1024).toFixed(2)} MB`}</small>
      {run.error && <p role="status">{run.error}</p>}
      {run.status === 'ready' && <button className="button" disabled={action.busy} onClick={() => review(run)}>{run.available ? 'Review & recover' : 'Check unavailable copy again'}</button>}
    </div>)}
  </div>
}
