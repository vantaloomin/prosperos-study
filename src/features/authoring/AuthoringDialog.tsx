import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice } from '../../components/Feedback'
import { AuthoringSetup } from './AuthoringSetup'
import { AuthoringRun } from './AuthoringRun'
import { actions, type EditorProps, type RunSummary } from './types'

export function AuthoringDialog({ onClose, ...editor }: EditorProps & { onClose: () => void }) {
  const [runId, setRunId] = useState<string | null>(null)
  return <Modal open wide onClose={onClose} title="Library writing assistant" description="Work on a chosen passage. Applying changes only your local draft; Save new version publishes it separately.">
    <div className="dialog-body form-stack">{runId ? <AuthoringRun key={runId} {...editor} runId={runId} onNew={() => setRunId(null)} /> : <AuthoringSetup {...editor} onStarted={setRunId} />}
      <details className="advanced-settings"><summary>Saved assistant history</summary><AuthoringHistory assetId={editor.asset?.asset_id} onOpen={setRunId} /></details>
    </div><footer className="dialog-footer"><button className="button" onClick={onClose}>Back to Library draft</button></footer>
  </Modal>
}

function AuthoringHistory({ assetId, onOpen }: { assetId?: string; onOpen: (id: string) => void }) {
  const [all, setAll] = useState(!assetId)
  const [page, setPage] = useState(0)
  const suffix = `?offset=${page * 100}${!all && assetId ? `&asset_id=${assetId}` : ''}`
  const history = useQuery({ queryKey: ['authoring-history', suffix], queryFn: () => api<RunSummary[]>(`/authoring${suffix}`) })
  return <div className="form-stack authoring-history"><label className="check-row"><input type="checkbox" checked={all} disabled={!assetId} onChange={(event) => { setAll(event.target.checked); setPage(0) }} />Show all Library runs, including unpublished additions</label>
    <p className="subtle">Page {page + 1} · up to 100 runs, newest first. Closing the editor leaves these records available. Runs from another item can be inspected here.</p><ErrorNotice message={history.error?.message} />
    {history.data?.map((run) => <button className="prompt-row" key={run.id} onClick={() => onOpen(run.id)}><span><strong>{run.name || 'Untitled draft'} · {actions[run.step]}</strong><small>{run.target_label} · {new Date(run.created_at).toLocaleString()}</small></span></button>)}
    {history.data?.length === 0 && <p className="subtle">No assistant requests yet.</p>}
    <div className="authoring-alternatives"><button className="button" disabled={page === 0 || history.isFetching} onClick={() => setPage(page - 1)}>Newer runs</button><button className="button" disabled={history.data?.length !== 100 || history.isFetching} onClick={() => setPage(page + 1)}>Older runs</button></div>
  </div>
}
