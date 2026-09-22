import { useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { publishPersistent, usePersistent } from '../../hooks/usePersistent'
import type { ProfileList } from '../models/types'
import { readyProfiles } from '../models/profileReadiness'
import { AnalysisHistoryList, AnalysisInputs, AnalysisResult } from './AnalysisResult'
import { useAnalysis } from './useStyleAnalysis'
import { analysisWorking, type AnalysisBody, type AnalysisPreview, type AnalysisStart, type StylePatch } from './analysisTypes'
import type { StyleContent } from './types'

interface Props { value: StyleContent; name: string; draftKey: string; sourceVersionId?: string; onApply: (changes: StylePatch, expected: StylePatch) => void }

export function SampleAnalysis(props: Props) {
  const [open, setOpen] = useState(false)
  const [draftId, setDraftId] = usePersistent(`${props.draftKey}:analysis-id`, operationId())
  const trigger = useRef<HTMLButtonElement>(null)
  return <section className="form-stack"><button ref={trigger} className="button" onClick={() => { setDraftId(draftId); setOpen(true) }}>Analyze writing samples</button><p className="subtle">Choose examples, preview one model request, and review editable style suggestions before using them.</p>{open && <AnalysisDialog {...props} draftId={draftId} onClose={() => setOpen(false)} focusOnClose={() => trigger.current} />}</section>
}

function AnalysisDialog({ value, name, draftId, sourceVersionId, onApply, onClose, focusOnClose }: Props & { draftId: string; onClose: () => void; focusOnClose: () => HTMLElement | null }) {
  const [pending, setPending] = usePersistent<AnalysisStart | null>(`prospero:style-analysis-request:${draftId}`, null, true)
  const [historyId, setHistoryId] = useState<string | null>(null)
  const [history, setHistory] = useState(false)
  const receipt = useQuery({ queryKey: ['style-analysis-operation', pending?.operation_id], queryFn: () => api<{ id: string } | null>(`/writing-analyses/operations/${pending!.operation_id}`), enabled: !!pending, refetchInterval: query => query.state.data ? false : 1000 })
  const jobId = historyId ?? receipt.data?.id ?? null
  const action = useAction()
  const send = (request: AnalysisStart) => action.run(async () => {
    publishPersistent(`prospero:style-analysis-request:${draftId}`, request)
    setPending(request)
    await api('/writing-analyses', request)
  })
  const fresh = () => { setPending(null); setHistoryId(null); setHistory(false) }
  return <Modal open wide title="Analyze writing samples" description="The model sees only your selected examples. Suggestions stay separate from the published style." onClose={onClose} focusOnClose={focusOnClose}><div className="dialog-body form-stack">
    <button className="text-button" onClick={() => setHistory(!history)}>{history ? 'Hide saved analyses' : 'Browse saved analyses'}</button>{history && <AnalysisHistoryList onSelect={id => { setHistoryId(id); setHistory(false) }} />}
    {jobId ? <SelectedAnalysis id={jobId} value={value} onApply={onApply} onFresh={fresh} /> : pending ? <PendingAnalysis pending={pending} busy={action.busy} checked={receipt.isSuccess} error={receipt.error?.message} onSend={send} onFresh={fresh} /> : <AnalysisSelection value={value} name={name} draftId={draftId} sourceVersionId={sourceVersionId} busy={action.busy} onStart={send} />}
    <ErrorNotice message={action.error} />
  </div><footer className="dialog-footer"><button className="button" onClick={onClose}>Return to style draft</button></footer></Modal>
}

function SelectedAnalysis({ id, value, onApply, onFresh }: { id: string; value: StyleContent; onApply: Props['onApply']; onFresh: () => void }) {
  const job = useAnalysis(id)
  return <>{job.isPending && <Loading label="Opening the saved analysis…" />}<ErrorNotice message={job.error?.message} />{job.data && <AnalysisResult key={id} job={job.data} current={value} onApply={onApply} />}{job.data && !analysisWorking(job.data.status) && <button className="button" onClick={onFresh}>Prepare another analysis</button>}</>
}

function PendingAnalysis({ pending, busy, checked, error, onSend, onFresh }: { pending: AnalysisStart; busy: boolean; checked: boolean; error?: string; onSend: (request: AnalysisStart) => void; onFresh: () => void }) {
  return <section className="form-stack"><p role="status">Checking the saved request. Reopening this view does not send it again.</p><ErrorNotice message={error} />{!busy && checked && <><p>No recorded request was found yet. Sending these same prepared inputs reuses the original action identifier.</p><button className="button" onClick={() => onSend(pending)}>Send the prepared analysis request</button><button className="text-button" onClick={onFresh}>Return to sample selection</button></>}</section>
}

function AnalysisSelection({ value, name, draftId, sourceVersionId, busy, onStart }: { value: StyleContent; name: string; draftId: string; sourceVersionId?: string; busy: boolean; onStart: (body: AnalysisStart) => void }) {
  const [selected, setSelected] = useState(value.examples.map((_, index) => index))
  const [profileId, setProfileId] = useState('')
  const [preview, setPreview] = useState<{ report: AnalysisPreview; body: AnalysisBody } | null>(null)
  const models = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const action = useAction()
  const body: AnalysisBody = { draft_id: draftId, name, source_version_id: sourceVersionId ?? null, profile_id: profileId || null, samples: value.examples.filter((_, index) => selected.includes(index)) }
  const prepare = () => action.run(async () => { const report = await api<AnalysisPreview>('/writing-analyses/preview', body); setPreview({ report, body }) })
  const current = preview && JSON.stringify(preview.body) === JSON.stringify(body)
  return <><SamplePicker samples={value.examples} selected={selected} onChange={setSelected} /><label className="field"><span>Sample analysis model</span><select aria-label="Sample analysis model" value={profileId} onChange={event => setProfileId(event.target.value)}><option value="">Use Library assistant default</option>{models.data?.profiles.map(model => <option key={model.profile_id} value={model.profile_id}>{model.display_name ?? model.name}</option>)}</select></label><ErrorNotice message={models.error?.message || action.error} /><button className="button" disabled={!body.samples.length || action.busy} onClick={prepare}>Preview sample analysis</button>{current && <AnalysisPreviewCard report={preview.report} busy={busy} onStart={() => onStart({ ...preview.body, operation_id: operationId(), preview_hash: preview.report.preview_hash })} />}</>
}

function SamplePicker({ samples, selected, onChange }: { samples: StyleContent['examples']; selected: number[]; onChange: (value: number[]) => void }) {
  return <fieldset className="form-stack"><legend>Samples to analyze</legend>{!samples.length && <p>Add writing samples to the style draft first, or browse a saved analysis.</p>}{samples.map((sample, index) => <div className="writing-sample form-stack" key={index}><label className="check-row"><input type="checkbox" checked={selected.includes(index)} onChange={event => onChange(event.target.checked ? [...selected, index] : selected.filter(item => item !== index))} />Sample {index + 1}: {sample.label}</label><pre className="authoring-prose" tabIndex={0}>{sample.text || '(empty)'}</pre></div>)}</fieldset>
}

function AnalysisPreviewCard({ report, busy, onStart }: { report: AnalysisPreview; busy: boolean; onStart: () => void }) {
  const snapshot = report.snapshot
  return <section className="review-estimate form-stack" aria-label="Sample analysis preview"><h3>One planned analysis request</h3><p>{snapshot.profile.name} · {snapshot.profile.config.model}</p><p className="subtle">~{snapshot.estimated_input_tokens.toLocaleString()} input tokens · {snapshot.samples.length} complete samples. Input allowance {snapshot.input_allowance.toLocaleString()}, including a {snapshot.overhead_margin}-token margin. Maximum output {snapshot.profile.config.max_output_tokens.toLocaleString()} tokens. Provider cost is unknown.</p><details><summary>Inspect selected samples and exact inputs</summary><AnalysisInputs snapshot={snapshot} /></details><button className="button primary" disabled={busy} onClick={onStart}>Analyze selected samples</button></section>
}

export function SampleAnalysisHistory({ onClose }: { onClose: () => void }) {
  const [id, setId] = useState<string | null>(null)
  const job = useAnalysis(id)
  return <Modal open wide title="Saved sample analyses" description="Review the selected examples, original responses and saved attempts. Viewing a record does not change a style." onClose={onClose}><div className="dialog-body form-stack"><AnalysisHistoryList onSelect={setId} /><ErrorNotice message={job.error?.message} />{job.data && <AnalysisResult key={job.data.id} job={job.data} />}</div><footer className="dialog-footer"><button className="button" onClick={onClose}>Close analyses</button></footer></Modal>
}
