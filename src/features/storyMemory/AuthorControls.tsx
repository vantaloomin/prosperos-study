import { useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, ApiError, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import { ControlEditor, ControlHistory, UnavailableDecisions } from './ControlEditor'
import { DecisionMerge, DecisionRecovery } from './DecisionRecovery'
import { useDecisionDraft } from './useDecisionDraft'
import { saveBody, staleDraft, startDraft, type DecisionDraft } from './decisionDraft'
import { labels, states, type Entry, type Kind, type State } from './controlTypes'

export function AuthorControls({ branch }: { branch: Branch }) {
  const query = useQuery({ queryKey: ['memory-controls', branch.id, branch.revision], refetchOnMount: 'always', refetchOnWindowFocus: 'always', queryFn: () => api<State>('/branches/' + branch.id + '/memory-controls') })
  const recovery = useDecisionDraft(branch)
  const draft = recovery.value
  const [review, setReview] = useState<State | null>(null)
  const action = useAction()
  const heading = useRef<HTMLHeadingElement>(null)
  const editing = draft?.editing ?? null
  useLayoutEffect(() => { if (!editing) heading.current?.focus() }, [editing])
  const initial = () => draft ?? startDraft(branch, query.data!, operationId())
  const edit = (entry: Entry | null) => recovery.store({ ...initial(), editing: entry })
  const update = (entries: Entry[]) => recovery.store({ ...initial(), entries })
  const keep = (entry: Entry) => { const next = initial(); recovery.store({ ...next, entries: [...next.entries.filter(item => item.id !== entry.id), entry], editing: null }) }
  const save = () => action.run(async () => {
    if (!draft) return
    const receipt = draft.pending ? draft : recovery.store({ ...draft, pending: saveBody(draft, operationId()) })!
    try {
      await api('/branches/' + branch.id + '/memory-controls', receipt.pending, 'PUT')
      recovery.store(null, receipt.stamp)
    } catch (failure) {
      if (failure instanceof ApiError && [400, 409, 422].includes(failure.status)) {
        recovery.store({ ...receipt, pending: null }, receipt.stamp)
        await query.refetch()
      }
      throw failure
    }
  })
  const refresh = () => action.run(async () => { const latest = await query.refetch(); if (latest.error) throw latest.error; setReview(latest.data!) })
  return <section className="form-stack"><h3 ref={heading} tabIndex={-1}>Author decisions</h3>
    <p className="subtle">Record what a character knows or believes, keep conflicting accounts visible, and guide emphasis. These decisions preserve your evidence and earlier versions. They never add a story event or edit Canon.</p>
    <DecisionRecovery draft={draft} error={recovery.error} recovered={recovery.recovered} onDownload={recovery.download} onDiscard={() => recovery.store(null)} />
    <ErrorNotice message={query.error?.message || action.error} />
    {query.isPending && <Loading />}
    <DecisionWorkspace branch={branch} saved={query.data} draft={draft} review={review} busy={action.busy} checking={query.isFetching} unreadable={recovery.unreadable}
      onEdit={edit} onKeep={keep} onUpdate={update} onSave={save} onRefresh={refresh}
      onMerged={value => { recovery.store(value); setReview(null); heading.current?.focus() }} onCancelReview={() => { setReview(null); heading.current?.focus() }}
      onDiscard={() => { recovery.store(null); setReview(null); action.clearError() }} />
  </section>
}

interface WorkspaceProps {
  branch: Branch; saved?: State; draft: DecisionDraft | null; review: State | null; busy: boolean; checking: boolean; unreadable: boolean
  onEdit: (entry: Entry | null) => void; onKeep: (entry: Entry) => void; onUpdate: (entries: Entry[]) => void
  onSave: () => void; onRefresh: () => void; onMerged: (draft: DecisionDraft) => void; onCancelReview: () => void; onDiscard: () => void
}

function DecisionWorkspace(props: WorkspaceProps) {
  const { saved, draft, review } = props
  if (!saved && !draft) return null
  if (review && draft) return <DecisionMerge key={review.revision + ':' + review.version_id} draft={draft} current={review} onKeep={props.onMerged} onCancel={props.onCancelReview} />
  const editing = draft?.editing
  return <>
    <fieldset className="form-stack author-decision-fields" disabled={decisionLocked(props)}>
      {editing ? <DecisionEditor {...props} entry={editing} /> :
        <DecisionList {...props} />}
    </fieldset>
    <DecisionActions {...props} />
  </>
}

function decisionLocked({ busy, unreadable, draft, review }: WorkspaceProps) { return busy || unreadable || !!draft?.pending || !!review }

function DecisionEditor({ branch, saved, entry, onEdit, onKeep }: WorkspaceProps & { entry: Entry }) {
  const sourceBranch = { ...branch, revision: saved?.revision ?? branch.revision }
  return <ControlEditor key={entry.id} branch={sourceBranch} characters={saved?.characters ?? []} entry={entry} onChange={onEdit} onKeep={onKeep} onCancel={() => onEdit(null)} />
}

function DecisionList({ branch, saved, draft, review, onEdit, onUpdate }: WorkspaceProps) {
  const entries = draft?.entries ?? saved?.entries ?? []
  return <><div className="import-downloads">{(Object.keys(labels) as Kind[]).map(kind => <button className="button" key={kind} disabled={entries.length >= 64 || !!review} onClick={() => onEdit({ id: operationId(), kind, subject: '', text: '', stance: states[kind][0][0], enabled: true, sources: [] })}>Add {labels[kind].toLowerCase()}</button>)}</div>
    {entries.map(entry => <DecisionCard key={entry.id} entry={entry} onEdit={() => onEdit(entry)} onRemove={() => onUpdate(entries.filter(item => item.id !== entry.id))} onToggle={enabled => onUpdate(entries.map(item => item.id === entry.id ? { ...item, enabled } : item))} />)}
    <UnavailableDecisions entries={saved?.unavailable_entries} onEdit={onEdit} />
    {!entries.length && <p>No available decisions on this path.</p>}
    <p className="subtle">Existing sibling branches and saved requests keep their own decisions. Pins and knowledge/conflict evidence must fit the model context. Exclusion affects optional Long story recall; required targets and the current passage remain available.</p>
    <ControlHistory branchId={branch.id} onLoad={onUpdate} />
  </>
}

function DecisionCard({ entry, onEdit, onRemove, onToggle }: { entry: Entry; onEdit: () => void; onRemove: () => void; onToggle: (enabled: boolean) => void }) {
  return <article className="prepared-card form-stack"><div className="section-heading"><h4>{entry.subject}</h4><button className="text-button" onClick={onEdit}>Edit decision</button></div>
    <small>{labels[entry.kind]} · {states[entry.kind].find(item => item[0] === entry.stance)?.[1]} · {entry.sources.length} source excerpt(s)</small><p>{entry.text}</p>
    <button className="text-button" onClick={onRemove}>Remove from draft</button>
    <label className="check-row"><input type="checkbox" checked={entry.enabled} onChange={event => onToggle(event.target.checked)} />Use this decision in future requests</label>
    <details><summary>Inspect exact evidence</summary>{entry.sources.map(source => <div key={source.id}><small>{source.title} · characters {source.start + 1}–{source.end}</small><pre className="authoring-prose" tabIndex={0}>{source.text}</pre></div>)}</details>
  </article>
}

function DecisionActions(props: WorkspaceProps) {
  const { draft, saved, busy, onSave, onDiscard, onRefresh } = props
  const stale = staleDraft(draft, saved)
  if (draft?.editing) return <p className="subtle">This entry is kept for recovery as you type. Keep it in the draft before saving the full decision set.</p>
  return <><p className="subtle" role="status">{stale ? 'The accepted path or saved decisions changed. Review the latest state before saving this draft.' : 'Saving applies the reviewed decisions to future requests on this path.'}</p>
    <DecisionButtons draft={draft} unavailable={saveUnavailable(props)} stale={stale} busy={busy} onSave={onSave} onDiscard={onDiscard} onRefresh={onRefresh} />
  </>
}

function DecisionButtons({ draft, unavailable, stale, busy, onSave, onDiscard, onRefresh }: {
  draft: DecisionDraft | null; unavailable: boolean; stale: boolean; busy: boolean; onSave: () => void; onDiscard: () => void; onRefresh: () => void
}) {
  const pending = !!draft?.pending
  return <div className="import-downloads"><button className="button primary" disabled={saveDisabled(busy, !!draft, pending, unavailable || stale)} onClick={onSave}>{pending ? 'Retry original save' : 'Save author decisions'}</button>
    <button className="button" disabled={!draft || busy || pending} onClick={onDiscard}>Discard unsaved changes</button>
    {stale && !pending && <button className="button" disabled={unavailable} onClick={onRefresh}>Review latest state</button>}
  </div>
}

function saveDisabled(busy: boolean, hasDraft: boolean, pending: boolean, stale: boolean) { return busy || !hasDraft || (!pending && stale) }

function saveUnavailable({ saved, busy, unreadable, review, checking }: WorkspaceProps) { return !saved || busy || unreadable || !!review || checking }
