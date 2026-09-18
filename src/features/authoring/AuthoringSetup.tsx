import { useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { readyProfiles } from '../models/profileReadiness'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { TextField } from '../../components/Fields'
import { useAction } from '../../hooks/useAction'
import type { ProfileList } from '../models/types'
import { AuthoringDefaults, ModelChoices } from './AuthoringModels'
import { proseTargets } from './targets'
import { actions, type AuthoringStep, type EditorProps, type Preview, type RequestBody, type Target } from './types'

export function AuthoringSetup({ onStarted, ...editor }: EditorProps & { onStarted: (id: string) => void }) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  return <><ErrorNotice message={profiles.error?.message} />{profiles.data ? <SetupForm {...editor} profiles={profiles.data} onStarted={onStarted} /> : <Loading />}</>
}

function SetupForm({ draft, draftId, asset, profiles, onStarted }: EditorProps & { profiles: ProfileList; onStarted: (id: string) => void }) {
  const targets = proseTargets(draft)
  const [key, setKey] = useState('text')
  const [step, setStep] = useState<AuthoringStep>('authoring-critique')
  const [context, setContext] = useState<string[]>(targets.slice(0, 6).filter((item) => item.text.trim()).map((item) => item.key))
  const [compare, setCompare] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [direction, setDirection] = useState('')
  const [preview, setPreview] = useState<{ value: Preview; request: RequestBody } | null>(null)
  const action = useAction()
  const target = targets.find((item) => item.key === key) ?? targets[0]
  const supporting = targets.filter((item) => item.key !== target.key && context.includes(item.key))
  const request: RequestBody = { source_version_id: asset?.id, draft_id: draftId, kind: draft.kind, name: draft.name, target_key: target.key, target_label: target.label, text: target.text, context: Object.fromEntries(supporting.map((item) => [item.key, item.text])), direction, step, profile_ids: selected }
  const change = (apply: () => void) => { apply(); setPreview(null) }
  const inspect = () => action.run(async () => { setPreview({ value: await api<Preview>('/authoring/preview', request), request }) })
  const start = () => action.run(async () => {
    if (!preview) return
    const result = await api<{ id: string }>('/authoring', { ...preview.request, operation_id: operationId(), preview_hash: preview.value.preview_hash })
    onStarted(result.id)
  })
  const invalid = !profiles.profiles.length || invalidSelection(compare, selected, step, target)
  return <><label className="field"><span>Passage to work on</span><select autoFocus value={target.key} onChange={(event) => change(() => setKey(event.target.value))}>{targets.map((item) => <option key={item.key} value={item.key}>{item.label}</option>)}</select></label>
    <label className="field"><span>Action</span><select value={step} onChange={(event) => change(() => setStep(event.target.value as AuthoringStep))}>{Object.entries(actions).filter(([value]) => value !== 'authoring-enrich').map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <p className="subtle">Critique returns quoted observations. Draft and Tighten return proposed prose for this field. Existing facts, genre and boundaries remain part of the instructions.</p>
    <TextField label="Your direction (optional)" value={direction} rows={3} maxLength={10000} onChange={(event) => change(() => setDirection(event.target.value))} placeholder="Keep the quiet tone, but make the motive more specific…" />
    <ContextChoices targets={targets} target={target} selected={context} onChange={(next) => change(() => setContext(next))} />
    <ModelChoices profiles={profiles.profiles} selected={selected} compare={compare} onMode={(next) => change(() => { setCompare(next); setSelected([]) })} onChange={(next) => change(() => setSelected(next))} />
    <AuthoringDefaults step={step} profiles={profiles.profiles} onChange={() => setPreview(null)} />
    {!profiles.profiles.length && <p className="subtle">Add a model profile in Settings to use the assistant.</p>}
    <p className="subtle">One provider request per profile; usage may be billed. Previewing is local and makes no model calls.</p><ErrorNotice message={action.error} />
    {preview ? <RequestPreview preview={preview.value} busy={action.busy} onStart={start} /> : <button className="button primary" disabled={action.busy || invalid} onClick={inspect}>Preview assistant requests</button>}
  </>
}

function invalidSelection(compare: boolean, selected: string[], step: AuthoringStep, target: Target) {
  return (compare && (selected.length < 2 || selected.length > 4)) || (step !== 'authoring-draft' && !target.text.trim())
}

function ContextChoices({ targets, target, selected, onChange }: { targets: Target[]; target: Target; selected: string[]; onChange: (keys: string[]) => void }) {
  const [filter, setFilter] = useState('')
  const visible = targets.filter((item) => item.key !== target.key && item.label.toLocaleLowerCase().includes(filter.toLocaleLowerCase()))
  const selectedCount = selected.filter((key) => key !== target.key).length
  const toggle = (key: string) => onChange(selected.includes(key) ? selected.filter((value) => value !== key) : [...selected, key])
  return <details className="advanced-settings"><summary>Passage & supporting context</summary><div className="form-stack authoring-history"><pre className="authoring-prose">{target.text || '(Empty passage)'}</pre><p className="subtle">Only the selected prose is sent. Choose up to 30 other fields for context; Story history and linked books are not included automatically.</p>
    <label className="field"><span>Find supporting fields</span><input value={filter} onChange={(event) => setFilter(event.target.value)} /></label>
    {visible.slice(0, 80).map((item) => <label key={item.key} className="check-row"><input type="checkbox" checked={selected.includes(item.key)} disabled={!selected.includes(item.key) && selectedCount >= 30} onChange={() => toggle(item.key)} />{item.label}</label>)}
    {visible.length > 80 && <p className="subtle">Refine your search to see more than the first 80 matches.</p>}
  </div></details>
}

export function RequestPreview({ preview, busy, onStart }: { preview: Preview; busy: boolean; onStart: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  return <section className="form-stack"><h3 ref={heading} tabIndex={-1}>Ready for your review</h3>{preview.jobs.map((job, index) => <div className="prepared-card" key={index}><strong>{job.profile_name}</strong><p className="subtle">{job.model} · instructions v{job.prompt_version} · about {job.estimated_input_tokens.toLocaleString()} input tokens</p><details><summary>Exact request content</summary><pre className="authoring-prose">{job.prompt}</pre><pre className="authoring-prose">{job.content}</pre></details></div>)}
    <button className="button primary" disabled={busy} onClick={onStart}>Generate {preview.request_count === 1 ? 'suggestion' : `${preview.request_count} alternatives`}</button>
  </section>
}
