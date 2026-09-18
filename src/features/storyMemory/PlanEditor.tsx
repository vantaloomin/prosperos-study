import { useRef, useState } from 'react'
import { api, ApiError, operationId } from '../../api'
import { Field, TextField } from '../../components/Fields'
import { Modal } from '../../components/Modal'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { ContinuityChange, PlannedEvent } from '../scenes/continuityTypes'
import { PlanEvidence } from './PlanEvidence'
import { commitments, planStatuses, type PlanEntry, type PlanView } from './planTypes'

function initialChange(entry?: PlanEntry): ContinuityChange {
  return { id: operationId(), action: entry ? 'replace' : 'add', target_id: entry?.id ?? null, kind: 'plan',
    subject: entry?.subject ?? '', text: entry?.text ?? '', reason: '', evidence: [],
    plan: entry?.plan ?? { status: 'proposed', timing: '', time_anchor: '', resolution: null,
      participants: [{ id: operationId(), name: '', commitment: 'proposed' }] } }
}
interface Props { branchId: string; view: PlanView; entry?: PlanEntry; suggestion?: ContinuityChange; onClose: () => void }
export function PlanEditor({ branchId, view, entry, suggestion, onClose }: Props) {
  const [change, setChange] = useState(() => suggestion ?? initialChange(entry))
  const [base] = useState(() => ({ revision: view.revision, version_id: view.version_id }))
  const [pending, setPending] = useState(false)
  const request = useRef<object | null>(null)
  const action = useAction()
  const updatePlan = (plan: PlannedEvent) => setChange(value => ({ ...value, plan }))
  const close = () => { if (!action.busy) onClose() }
  async function save() {
    await action.run(async () => {
      request.current ??= { operation_id: operationId(), expected_revision: base.revision, expected_version_id: base.version_id, change }
      setPending(true)
      try { await api('/branches/' + branchId + '/plans', request.current); onClose() }
      catch (error) {
        if (error instanceof ApiError && error.status < 500) { request.current = null; setPending(false) }
        throw error
      }
    })
  }
  return <Modal open onClose={close} title={entry ? 'Update a plan' : 'Remember a plan'}
    description="Record an intention or commitment from accepted prose. Your manuscript and other branches keep their own history." wide>
    <form className="plan-form" onSubmit={event => { event.preventDefault(); void save() }}>
      <div className="dialog-body form-stack"><ErrorNotice message={action.error} />
        <SuggestionNotice suggestion={suggestion} entry={entry} />
        <fieldset className="form-stack plan-fields" disabled={action.busy || pending}>
          <Field label="Plan" value={change.subject} readOnly={!!entry} maxLength={300} required onChange={event => setChange({ ...change, subject: event.target.value })} />
          <TextField label="What is currently established?" value={change.text} rows={3} maxLength={5000} required onChange={event => setChange({ ...change, text: event.target.value })} />
          <PlanFields value={change.plan!} onChange={updatePlan} />
          <TextField label="Reason for this record or correction" value={change.reason} rows={2} maxLength={3000} required onChange={event => setChange({ ...change, reason: event.target.value })} />
          <PlanEvidence branchId={branchId} revision={base.revision} selected={change.evidence} onChange={evidence => setChange({ ...change, evidence })} />
        </fieldset>
        {pending && <p className="subtle" role="status">The save has not been confirmed yet. Retry the same request to check its result safely.</p>}
        {action.error && <p className="subtle">Your entries remain here. If this path changed, close and reopen the plan to review its latest state before saving.</p>}
      </div>
      <footer className="dialog-footer"><button className="button" type="button" disabled={action.busy} onClick={close}>Cancel</button>
        <button className="button primary" type="submit" disabled={action.busy || !change.evidence.length}>{action.busy ? 'Saving…' : pending ? 'Retry original save' : 'Save plan'}</button></footer>
    </form>
  </Modal>
}
function PlanFields({ value, onChange }: { value: PlannedEvent; onChange: (value: PlannedEvent) => void }) {
  const closed = value.status === 'completed' || value.status === 'cancelled'
  return <>
    <label className="field"><span>Plan status</span><select aria-label="Plan status" value={value.status} onChange={event => {
      const status = event.target.value as PlannedEvent['status']
      onChange({ ...value, status, resolution: status === 'completed' || status === 'cancelled' ? value.resolution ?? '' : null })
    }}>{planStatuses.map(status => <option key={status} value={status}>{status}</option>)}</select></label>
    <div className="plan-timing"><Field label="When in the story?" value={value.timing} placeholder="This weekend; after the ship arrives…" maxLength={500} required onChange={event => onChange({ ...value, timing: event.target.value })} />
      <Field label="Timing refers to…" value={value.time_anchor} placeholder="Friday evening, when they made the agreement" maxLength={500} required onChange={event => onChange({ ...value, time_anchor: event.target.value })} /></div>
    <PlanParticipants value={value} onChange={onChange} />
    {closed && <TextField label="What explicitly completed or cancelled it?" value={value.resolution ?? ''} rows={2} maxLength={1000} required onChange={event => onChange({ ...value, resolution: event.target.value })} />}
    <p className="subtle">Passing a date or attempting a task does not complete it. One person withdrawing does not cancel the whole plan.</p>
  </>
}
function PlanParticipants({ value, onChange }: { value: PlannedEvent; onChange: (value: PlannedEvent) => void }) {
  function update(id: string, patch: Partial<PlannedEvent['participants'][number]>) {
    onChange({ ...value, participants: value.participants.map(person => person.id === id ? { ...person, ...patch } : person) })
  }
  return <fieldset className="form-stack plan-participants"><legend>Participants</legend>
    {value.participants.map((person, index) => <div className="plan-participant" key={person.id}>
      <Field label={'Participant ' + (index + 1)} value={person.name} required maxLength={200} onChange={event => update(person.id, { name: event.target.value })} />
      <label className="field"><span>{'Commitment · participant ' + (index + 1)}</span><select aria-label={'Commitment · participant ' + (index + 1)} value={person.commitment} onChange={event => update(person.id, { commitment: event.target.value as typeof person.commitment })}>
        {commitments.map(status => <option key={status} value={status}>{status}</option>)}</select></label>
    </div>)}
    <button className="text-button" type="button" disabled={value.participants.length >= 24} onClick={() => onChange({ ...value, participants: [...value.participants, { id: operationId(), name: '', commitment: 'proposed' }] })}>Add participant</button>
    <small className="subtle">Keep the people already recorded; use declined or withdrawn when their involvement changes.</small>
  </fieldset>
}

function SuggestionNotice({ suggestion, entry }: { suggestion?: ContinuityChange; entry?: PlanEntry }) {
  if (!suggestion) return null
  return <><p className="scene-notice">Suggested by the continuity role. Check the interpretation and evidence before saving.</p>
    {entry && <details><summary>Compare with the current plan</summary><p>{entry.text}</p><p>{entry.plan.status} · {entry.plan.timing}</p></details>}</>
}
