import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Pencil } from 'lucide-react'
import { api } from '../../api'
import { Modal } from '../../components/Modal'
import { TextField } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { sectionState } from './sectionState'
import { usePersistent } from '../../hooks/usePersistent'
import type { TaskSetting } from '../workflow/types'
import { RetiredPrompts, TaskSettings } from './TaskSettings'
import { LibraryModels } from './LibraryModels'

export interface Prompt { id: string; key: string; label: string; number: number; template: string; enabled?: boolean; activation_revision?: number; order?: number; group?: string; description?: string; tasks?: TaskSetting[] }

function previousDraft(prompt: Prompt, storyId?: string) {
  if (storyId) return prompt.template
  try {
    const value: unknown = JSON.parse(localStorage.getItem(`roleplay:prompt-draft:${prompt.id}`) ?? 'null')
    return typeof value === 'string' ? value : prompt.template
  } catch { return prompt.template }
}

export function Prompts() {
  const query = useQuery({ queryKey: ['prompts'], queryFn: () => api<Prompt[]>('/prompts') })
  const [editing, setEditing] = useState<Prompt | null>(null)
  const groups = [...new Set(query.data?.map(prompt => prompt.group ?? 'Workflow') ?? [])]
  return <section className="prompt-flow"><div className="section-heading"><div><h2>Instructions behind the scenes</h2><p className="subtle">Your agents, in the order they work. Interactive writing and scene building follow different paths; sidebar and Library tools run when you ask.</p><p className="subtle">Switches apply to new requests. Active requests finish and saved results remain available. Manual writing is always available.</p></div></div><ErrorNotice message={query.error?.message} />
    <ConsolidationNotice /><LibraryModels /><RetiredPrompts />
    {groups.map(group => <PromptSection key={group} group={group} prompts={query.data?.filter(prompt => (prompt.group ?? 'Workflow') === group) ?? []} onEdit={setEditing} />)}
    {editing && <PromptEditor prompt={editing} onClose={() => setEditing(null)} />}
  </section>
}

function ConsolidationNotice() {
  const [dismissed, setDismissed] = usePersistent('roleplay:consolidation-notice:v062', false)
  if (dismissed) return null
  return <aside className="scene-notice"><p>Eleven roles now cover the workflow. Earlier custom instructions, Story pins, task models and disabled tasks are preserved below each role. You can deliberately switch a retained prompt to its combined role.</p><button className="text-button" onClick={() => setDismissed(true)}>Dismiss update</button></aside>
}

function PromptSection({ group, prompts, onEdit }: { group: string; prompts: Prompt[]; onEdit: (prompt: Prompt) => void }) {
  const action = useAction()
  const input = useRef<HTMLInputElement>(null)
  const state = sectionState(prompts)
  useEffect(() => { if (input.current) input.current.indeterminate = state === 'mixed' }, [state])
  const toggle = () => action.run(async () => {
    await api('/prompt-sections/activation', { group, enabled: state !== 'all', expected_revision: prompts[0]?.activation_revision ?? 0 }, 'PUT')
  })
  return <section className="prompt-group" aria-label={group}><header className="prompt-group-heading"><h3>{group}</h3><label className="section-switch"><input ref={input} type="checkbox" aria-label={`${group}: ${state === 'all' ? 'Disable all' : 'Enable all'}`} aria-checked={state === 'mixed' ? 'mixed' : state === 'all'} checked={state === 'all'} disabled={action.busy} onChange={toggle} /><span>{state === 'mixed' ? 'Some enabled' : state === 'all' ? 'All enabled' : 'All disabled'}<small>{state === 'all' ? 'Disable all' : 'Enable all'}</small></span></label></header><ErrorNotice message={action.error} />{prompts.map(prompt => <PromptCard key={prompt.key} prompt={prompt} onEdit={() => onEdit(prompt)} disabled={action.busy} />)}</section>
}

function PromptCard({ prompt, onEdit, disabled }: { prompt: Prompt; onEdit: () => void; disabled?: boolean }) {
  const action = useAction()
  const enabled = prompt.enabled !== false
  const toggle = () => action.run(async () => {
    await api(`/prompts/${prompt.key}/activation`, { enabled: !enabled, expected_revision: prompt.activation_revision ?? 0 }, 'PUT')
  })
  return <article className="prompt-card" data-enabled={enabled}>
    <span className="prompt-number" aria-hidden="true">{String((prompt.order ?? 0) + 1).padStart(2, '0')}</span>
    <div className="prompt-description"><h4>{prompt.label}</h4><p>{prompt.description}</p><small>Version {prompt.number} · {enabled ? 'Available for future requests' : 'Disabled · skipped in the flow'}</small><TaskSettings prompt={prompt} /><ErrorNotice message={action.error} /></div>
    <div className="prompt-actions"><label className="agent-switch"><input type="checkbox" role="switch" aria-label={`Enable ${prompt.label}`} checked={enabled} disabled={disabled || action.busy} onChange={toggle} /><span aria-hidden="true" /><small>{enabled ? 'Enabled' : 'Disabled'}</small></label><button className="button quiet" aria-label={`Edit ${prompt.label} instructions`} onClick={onEdit}><Pencil size={15} />Edit prompt</button></div>
  </article>
}

export function PromptEditor({ prompt, onClose, storyId }: { prompt: Prompt; onClose: () => void; storyId?: string }) {
  const draftKey = `roleplay:prompt-draft:${storyId ?? 'workspace'}:${prompt.id}`
  const [text, setText] = usePersistent(draftKey, previousDraft(prompt, storyId))
  const history = useQuery({ queryKey: ['prompt-history', prompt.key], queryFn: () => api<Prompt[]>(`/prompts/${prompt.key}/versions`) })
  const combined = history.data?.find(version => version.id === `${prompt.key}-default-v062`)
  const action = useAction()
  const save = () => action.run(async () => {
    await api(`/prompts/${prompt.key}${storyId ? `?story_id=${storyId}` : ''}`, { expected_version_id: prompt.id, template: text }, 'PUT')
    localStorage.removeItem(draftKey)
    if (!storyId) localStorage.removeItem(`roleplay:prompt-draft:${prompt.id}`)
    onClose()
  })
  const scope = storyId ? 'Save an override for future requests in this Story.' : 'Edit the workspace default for future requests that inherit it.'
  return <Modal open onClose={onClose} title={`Edit ${prompt.label} instructions`} description={`${scope} Recorded inputs and application permissions stay unchanged.`} wide><div className="dialog-body form-stack"><TaskSettings prompt={prompt} storyId={storyId} />{combined && combined.id !== prompt.id && <button className="button" onClick={() => setText(combined.template)}>Load v0.6.2 default as a draft</button>}<TextField label="Role instructions" rows={15} value={text} onChange={(e) => setText(e.target.value)} /><details className="advanced-settings"><summary>Earlier versions</summary><div className="version-buttons">{history.data?.map((version) => <button className="button" key={version.id} onClick={() => setText(version.template)}>Use v{version.number} as draft</button>)}</div></details><ErrorNotice message={action.error} /></div><footer className="dialog-footer"><span className="subtle">Unpublished edits are saved as a local draft.</span><button className="button primary" disabled={!text.trim() || action.busy} onClick={save}>Publish new version</button></footer></Modal>
}
