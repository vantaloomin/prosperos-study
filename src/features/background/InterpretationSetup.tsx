import { useLayoutEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { readyProfiles } from '../models/profileReadiness'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { TextField } from '../../components/Fields'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import type { ModelProfile, ProfileList } from '../models/types'
import { PromptEditor, type Prompt } from '../prompts/Prompts'
import type { PrivatePreview } from './interpretationTypes'

export function InterpretationSetup({ branch, onClose, onStarted }: { branch: Branch; onClose: () => void; onStarted: (id: string) => void }) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  return <Modal open onClose={onClose} title="Private possibilities" description="Develop the saved cues into specific motives and future hooks. All results stay concealed until you choose to reveal them."><div className="dialog-body form-stack"><ErrorNotice message={profiles.error?.message} />{profiles.data ? <InterpretationForm branch={branch} profiles={profiles.data.profiles} onStarted={onStarted} /> : <Loading />}</div></Modal>
}

function InterpretationForm({ branch, profiles, onStarted }: { branch: Branch; profiles: ModelProfile[]; onStarted: (id: string) => void }) {
  const [compare, setCompare] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [direction, setDirection] = useState('')
  const [preview, setPreview] = useState<PrivatePreview | null>(null)
  const [prompt, setPrompt] = useState<Prompt | null>(null)
  const action = useAction()
  const request = { expected_revision: branch.revision, profile_ids: selected, direction }
  const changeProfiles = (values: string[]) => { setSelected(values); setPreview(null) }
  const changeMode = (value: boolean) => { setCompare(value); changeProfiles([]) }
  const inspect = () => action.run(async () => { setPreview(await api<PrivatePreview>(`/branches/${branch.id}/background/interpretations/preview`, request)) })
  const start = () => action.run(async () => {
    if (!preview) return
    const result = await api<{ id: string }>(`/branches/${branch.id}/background/interpretations`, { ...request, operation_id: operationId(), preview_hash: preview.preview_hash })
    onStarted(result.id)
  })
  const edit = () => action.run(async () => {
    const prompts = await api<Prompt[]>(`/prompts?story_id=${branch.story_id}`)
    setPrompt(prompts.find((item) => item.key === 'background-interpretation') ?? null)
  })
  const invalid = profiles.length === 0 || (compare && (selected.length < 2 || selected.length > 4))
  return <><PrivateProfileChoices profiles={profiles} selected={selected} compare={compare} onMode={changeMode} onChange={changeProfiles} />
    <TextField label="Private planning direction (optional)" rows={3} value={direction} onChange={(event) => { setDirection(event.target.value); setPreview(null) }} placeholder="Keep motivations grounded in the existing relationships…" />
    <details><summary>Instructions and saved defaults</summary><p className="subtle">This step inherits Primary Writer unless assigned in Story workflow → Models by step. The selection above overrides this request only.</p><button className="text-button" onClick={edit}>Edit private interpretation instructions</button></details>
    <p className="subtle">One model request per selected profile. Provider usage may be billed. The saved random draws and dates stay fixed; no Story events are accepted.</p><ErrorNotice message={action.error} />
    {preview ? <PrivateRequestPreview preview={preview} busy={action.busy} onStart={start} /> : <button className="button primary" disabled={action.busy || invalid} onClick={inspect}>Preview model requests</button>}
    {prompt && <PromptEditor prompt={prompt} storyId={branch.story_id} onClose={() => { setPrompt(null); setPreview(null) }} />}
  </>
}

function PrivateProfileChoices({ profiles, selected, compare, onMode, onChange }: { profiles: ModelProfile[]; selected: string[]; compare: boolean; onMode: (value: boolean) => void; onChange: (values: string[]) => void }) {
  const toggle = (id: string) => onChange(selected.includes(id) ? selected.filter((item) => item !== id) : [...selected, id])
  return <><label className="check-row"><input type="checkbox" checked={compare} onChange={(event) => onMode(event.target.checked)} />Explicitly compare multiple profiles</label>
    {compare ? <div className="asset-choices">{profiles.map((profile) => <label className="check-row" key={profile.profile_id}><input type="checkbox" checked={selected.includes(profile.profile_id)} onChange={() => toggle(profile.profile_id)} />{profile.display_name ?? profile.name}</label>)}<p className="subtle">Choose 2–4 profiles. Every alternative uses identical context and instructions.</p></div> : <label className="field"><span>Model for this request</span><select value={selected[0] ?? ''} onChange={(event) => onChange(event.target.value ? [event.target.value] : [])}><option value="">Use the configured step model</option>{profiles.map((profile) => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)}</select></label>}
    {!profiles.length && <p className="subtle">Add a model in Settings to develop private interpretations. Your seeded cues remain available.</p>}
  </>
}

function PrivateRequestPreview({ preview, busy, onStart }: { preview: PrivatePreview; busy: boolean; onStart: () => void }) {
  const heading = useRef<HTMLParagraphElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  return <div className="form-stack"><p ref={heading} tabIndex={-1}>{preview.target_counts.drives} character targets · {preview.target_counts.hooks} future hooks</p>{preview.jobs.map((job, index) => <div className="prepared-card" key={index}><strong>{job.profile_name}</strong><p className="subtle">{job.model} · prompt v{job.prompt_version} · estimated {job.estimated_input_tokens.toLocaleString()} input tokens</p></div>)}<button className="button primary" disabled={busy} onClick={onStart}>Generate {preview.request_count} private {preview.request_count === 1 ? 'interpretation' : 'alternatives'}</button></div>
}
