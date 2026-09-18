import { useEffect, useRef, useState } from 'react'
import { SourceMemoryCoverage } from './SourceMemoryCoverage'
import { api, operationId } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch } from '../../types'
import type { ModelProfile } from '../models/types'
import { defaultReviewSteps, type ReviewPreview, type ReviewRequest, type Routing, type ReviewStep } from './types'
import { ReaderLenses } from './ReaderChoices'

export function ReviewSetup({ branch, routing, profiles, onStarted }: { branch: Branch; routing: Routing; profiles: ModelProfile[]; onStarted: (id: string) => void }) {
  const latest = [...branch.messages].reverse().find((message) => ['assistant', 'narrator'].includes(message.role))
  const [draft, setDraft] = usePersistent(`roleplay:review-draft:${branch.id}:${branch.head_id}`, { from: latest?.id ?? '', through: '', steps: defaultReviewSteps })
  const [preview, setPreview] = useState<{ body: ReviewRequest; data: ReviewPreview; operation: string } | null>(null)
  const action = useAction()
  const patch = (change: Partial<typeof draft>) => { setDraft({ ...draft, ...change }); setPreview(null) }
  const prepare = () => action.run(async () => {
    const body = { expected_revision: branch.revision, from_node_id: draft.from || null, through_node_id: draft.through || null, steps: draft.steps }
    const data = await api<ReviewPreview>(`/branches/${branch.id}/reviews/preview`, body)
    setPreview({ body, data, operation: operationId() })
  })
  const start = () => action.run(async () => {
    if (!preview) return
    const result = await api<{ id: string }>(`/branches/${branch.id}/reviews`, { ...preview.body, preview_hash: preview.data.preview_hash, operation_id: preview.operation })
    onStarted(result.id)
  })
  return <div className="form-stack"><div><h3>Fresh eyes on a passage</h3><p className="subtle">Review the selected path without rewriting it. Each specialist works independently. Blind readers receive the passage and at most two preceding prose contributions, with no lore, rules, rolls or other reviews.</p></div>
    <div className="review-range"><PassageSelect label="Start of reviewed passage" value={draft.from} branch={branch} first="Beginning of this path" onChange={(from) => patch({ from })} /><PassageSelect label="End of reviewed passage" value={draft.through} branch={branch} first="Current end of this path" onChange={(through) => patch({ through })} /></div>
    <ReviewRoles routing={routing} profiles={profiles} steps={draft.steps} onChange={(steps) => patch({ steps })} />
    <p className="subtle">Rules and continuity reviews can discuss attached lore. Reports are suggestions, not accepted story changes. Prompts and inherited models can be edited in Models by step.</p><ErrorNotice message={action.error} />
    <button className="button" disabled={action.busy || !draft.steps.length || !branch.messages.length} onClick={prepare}>Preview review requests</button>
    {preview && <ReviewEstimate data={preview.data} busy={action.busy} onStart={start} />}
  </div>
}

export function ReviewRoles({ routing, profiles, steps, onChange, scene = false }: { routing: Routing; profiles: ModelProfile[]; steps: ReviewStep[]; onChange: (steps: ReviewStep[]) => void; scene?: boolean }) {
  const roles = routing.steps.filter((step) => step.key.startsWith('review-'))
  const toggle = (key: string) => onChange(steps.some((step) => step.key === key) ? steps.filter((step) => step.key !== key) : [...steps, { key, profile_ids: [] }])
  const replace = (updated: ReviewStep) => onChange(steps.map(step => step.key === updated.key ? updated : step))
  const legacy = steps.filter(step => !roles.some(role => role.key === step.key))
  return <div className="review-roles">{roles.map(role => <ReaderChoice key={role.key} role={role} selected={steps.find(step => step.key === role.key)} profiles={profiles} scene={scene} onToggle={() => toggle(role.key)} onChange={replace} />)}{legacy.map(step => <div className="review-role" key={step.key}><label className="check-row"><input type="checkbox" checked onChange={() => toggle(step.key)} />Retained selection · {step.key}</label><ComparisonChoices profiles={profiles} selected={step.profile_ids} onChange={profile_ids => replace({ ...step, profile_ids })} /><small>Uses its original specialist prompt. Deselect to adopt a combined reader above.</small></div>)}</div>
}

function ReaderChoice({ role, selected, profiles, scene, onToggle, onChange }: { role: Routing['steps'][number]; selected?: ReviewStep; profiles: ModelProfile[]; scene: boolean; onToggle: () => void; onChange: (step: ReviewStep) => void }) {
  const enabled = role.enabled !== false
  return <div className="review-role"><label className="check-row"><input type="checkbox" checked={enabled && !!selected} disabled={!enabled} onChange={onToggle} /><span>{role.name}{!enabled && ' (disabled in Prompts)'}<small>{role.scope === 'blind' ? 'Prose only' : 'Includes permitted pinned references'}</small></span></label>{selected && enabled && <><ReaderLenses role={role} selected={selected} scene={scene} onChange={onChange} /><ComparisonChoices profiles={profiles} selected={selected.profile_ids} onChange={profile_ids => onChange({ ...selected, profile_ids })} /></>}</div>
}

function PassageSelect({ label, value, branch, first, onChange }: { label: string; value: string; branch: Branch; first: string; onChange: (value: string) => void }) {
  return <label className="field"><span>{label}</span><select aria-label={label} value={value} onChange={(event) => onChange(event.target.value)}><option value="">{first}</option>{branch.messages.map((message, index) => <option key={message.id} value={message.id}>{index + 1} · {message.role} · {message.text.slice(0,65)}</option>)}</select></label>
}

function ComparisonChoices({ profiles, selected, onChange }: { profiles: ModelProfile[]; selected: string[]; onChange: (ids: string[]) => void }) {
  const toggle = (id: string) => onChange(selected.includes(id) ? selected.filter((value) => value !== id) : [...selected, id])
  return <details className="review-comparison"><summary>{selected.length ? `${selected.length} explicit profile${selected.length > 1 ? 's' : ''}` : 'Use assigned model · change or compare'}</summary><p className="subtle">Select up to four profiles to request separate reports with identical inputs. Leave empty to use this step's saved assignment.</p>{profiles.map((profile) => <label className="check-row" key={profile.profile_id}><input type="checkbox" checked={selected.includes(profile.profile_id)} disabled={!selected.includes(profile.profile_id) && selected.length >= 4} onChange={() => toggle(profile.profile_id)} />{profile.display_name ?? profile.name}</label>)}</details>
}

export function ReviewEstimate({ data, busy, onStart }: { data: ReviewPreview; busy: boolean; onStart: () => void }) {
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])
  return <section className="review-estimate form-stack"><h3 ref={heading} tabIndex={-1}>{data.request_count} deliberate requests</h3><p className="subtle">{data.scene ? `Saved draft of ${data.scene.title} · plan revision ${data.scene.revision}. This prose is not in Story history.` : `${data.draft_messages} contributions in the reviewed range.`} Input token counts are estimates; provider billing may differ. Previewing has made no model calls.</p>{data.jobs.map((job, index) => <div className="review-estimate-row" key={index}><strong>{job.name}</strong><span>{job.profile_name} · {job.model}</span><small>~{job.estimated_input_tokens.toLocaleString()} input tokens · {job.source_count} sources · prompt v{job.prompt_version}</small><SourceMemoryCoverage memory={job.source_memory} /></div>)}<button className="button primary" disabled={busy} onClick={onStart}>Start {data.request_count} review requests</button></section>
}
