import { lazy, Suspense, useRef, useState } from 'react'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { Field, TextField } from '../../components/Fields'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import { StyleFields } from './StyleFields'
import { RecipeFields } from './RecipeFields'
import { UnsupportedSettings } from './UnsupportedSettings'
import { SampleAnalysis } from './SampleAnalysis'
import { mergeStyleSuggestions, type StylePatch } from './analysisTypes'
import type { RecipeContent, StyleContent, WritingDraft, WritingResource } from './types'

const VersionedTextEdit = lazy(() => import('../textEdits/VersionedTextEdit').then(module => ({ default: module.VersionedTextEdit })))

export function WritingEditor({ initial, resource, resources, onClose }: { initial: WritingDraft; resource?: WritingResource; resources: WritingResource[]; onClose: () => void }) {
  const key = `prospero:writing-draft:v1:${resource?.id ?? initial.kind + ':' + initial.name}`
  const [draft, setDraft] = usePersistent<WritingDraft>(key, initial, true)
  const operation = useRef({ id: operationId(), payload: '' })
  const action = useAction()
  const [scopedEdit, setScopedEdit] = useState<WritingResource | null>(null)
  const [returnFocus] = useState(() => document.activeElement as HTMLElement | null)
  const patch = (change: Partial<WritingDraft>) => setDraft({ ...draft, ...change })
  const applySuggestions = (changes: StylePatch, expected: StylePatch) => {
    const stored = localStorage.getItem(key)
    const current = stored ? JSON.parse(stored) as WritingDraft : draft
    if (current.kind !== 'style') throw new Error('This draft is no longer a writing style.')
    setDraft({ ...current, content: mergeStyleSuggestions(current.content as StyleContent, changes, expected) })
  }
  const save = () => action.run(async () => {
    const payload = JSON.stringify(draft)
    if (operation.current.payload !== payload) operation.current = { id: operationId(), payload }
    await api(resource ? `/writing-resources/${resource.asset_id}/versions` : '/writing-resources', { ...draft, operation_id: operation.current.id, ...(resource ? { expected_version_id: resource.id } : {}) })
    localStorage.removeItem(key); onClose()
  })
  if (scopedEdit) return <Suspense fallback={<Loading />}><VersionedTextEdit source={{ kind: 'writing-field', asset_id: scopedEdit.asset_id }} expectedEdition={scopedEdit.id} onClose={onClose} focusOnClose={() => returnFocus} /></Suspense>
  return <Modal open wide onClose={onClose} title={resource ? `Edit ${resource.name}` : `New ${initial.kind === 'style' ? 'writing style' : 'writing recipe'}`} description="Publishing saves a new version. Stories keep their chosen versions until you adopt an update."><div className="dialog-body form-stack"><Field label="Name" autoFocus maxLength={120} value={draft.name} onChange={event => patch({ name: event.target.value })} /><TextField label="Description" rows={2} maxLength={2000} value={draft.description} onChange={event => patch({ description: event.target.value })} />
    <WritingContent draft={draft} resource={resource} resources={resources} draftKey={key} onChange={content => patch({ content })} onApply={applySuggestions} />
    <UnsupportedSettings value={draft.unsupported} />
    <ScopedWritingButton resource={resource} initial={initial} draft={draft} busy={action.busy} onOpen={setScopedEdit} />
    <TextField label="Version note" rows={2} maxLength={2000} value={draft.note} onChange={event => patch({ note: event.target.value })} /><ErrorNotice message={action.error} /></div><footer className="dialog-footer"><button className="text-button" onClick={onClose}>Close · keep draft</button><button className="button primary" disabled={!draft.name.trim() || action.busy} onClick={save}>{action.busy ? 'Publishing…' : 'Publish version'}</button></footer></Modal>
}

function WritingContent({ draft, resource, resources, draftKey, onChange, onApply }: { draft: WritingDraft; resource?: WritingResource; resources: WritingResource[]; draftKey: string; onChange: (value: StyleContent | RecipeContent) => void; onApply: (changes: StylePatch, expected: StylePatch) => void }) {
  if (draft.kind !== 'style') return <RecipeFields value={draft.content as RecipeContent} resources={resources} onChange={onChange} />
  return <><StyleFields value={draft.content as StyleContent} onChange={onChange} /><SampleAnalysis value={draft.content as StyleContent} name={draft.name} draftKey={draftKey} sourceVersionId={resource?.id} onApply={onApply} /></>
}

function ScopedWritingButton({ resource, initial, draft, busy, onOpen }: { resource?: WritingResource; initial: WritingDraft; draft: WritingDraft; busy: boolean; onOpen: (value: WritingResource) => void }) {
  if (!resource) return null
  const dirty = JSON.stringify(draft) !== JSON.stringify(initial)
  return <div className="form-stack"><button className="button" disabled={dirty || busy} onClick={() => onOpen(resource)}>Review a scoped text change</button>{dirty && <p className="subtle">Publish the current draft before starting a separate text-change proposal.</p>}</div>
}
