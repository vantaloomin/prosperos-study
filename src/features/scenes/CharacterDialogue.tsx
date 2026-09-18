import { useId } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import type { SceneJob, SceneRun } from './types'

export interface ActorDraft { view: string; slot_ids: string[]; briefing: string }
export interface DialogueSetup { enabled: boolean; actors: ActorDraft[] }
export interface ActorInput { character_id?: string; subject?: string; slot_ids: string[]; briefing: string }
export interface ActorRequest {
  subject?: string; slot_ids: string[]; content: string; instructions?: string; estimated_input_tokens: number
  knowledge_lens: { subject: string; selected_decisions: number; permitted_decisions: number; source_count: number }
}
interface View { key: string; subject: string; character_id: string | null }

export function CharacterDialogue({ run, value, onChange }: { run: SceneRun; value: DialogueSetup; onChange: (value: DialogueSetup) => void }) {
  const query = useQuery({ queryKey: ['scene-character-evidence', run.id], queryFn: () => api<View[]>('/scenes/' + run.id + '/character-evidence'), enabled: value.enabled })
  const slots = run.draft?.blocks.filter(block => block.kind === 'dialogue') ?? []
  const start = () => onChange({ ...value, enabled: !value.enabled, actors: value.actors.length ? value.actors : [{ view: '', slot_ids: slots.map(slot => slot.id), briefing: '' }] })
  const update = (index: number, actor: ActorDraft) => onChange({ ...value, actors: value.actors.map((item, position) => position === index ? actor : item) })
  return <section className="prepared-card form-stack"><label className="check-row"><input type="checkbox" checked={value.enabled} onChange={start} />Use each character’s own evidence</label>
    {value.enabled && <><p className="subtle">Assign every spoken slot to a character view and write what that character can observe now. Each briefing makes one independent model call per compared profile. Only its briefing and granted evidence are sent; the full plan, narration, other responses and chance receipts are withheld.</p>
      <p className="subtle">Knowledge is frozen when this scene starts. Start a new scene to use later author decisions. The selected stage model and editable Dialogue writer prompt apply to each call.</p><ErrorNotice message={query.error?.message} />
      {query.isSuccess && !query.data.length && <p role="status">No character knowledge views were available when this scene began. Add knowledge in Story memory → Author decisions, then start a new scene.</p>}
      {value.actors.map((actor, index) => <ActorEditor key={index} actor={actor} index={index} views={query.data ?? []} slots={slots} onChange={next => update(index, next)} onRemove={() => onChange({ ...value, actors: value.actors.filter((_, position) => position !== index) })} />)}
      <button className="button" disabled={value.actors.length >= 8} onClick={() => onChange({ ...value, actors: [...value.actors, { view: '', slot_ids: [], briefing: '' }] })}>Add character briefing</button>
      <p role="status">{value.actors.length} briefing(s). Each slot must be assigned exactly once. Preview checks permissions, assignments and model limits locally.</p>
    </>}
  </section>
}

function ActorEditor({ actor, index, views, slots, onChange, onRemove }: { actor: ActorDraft; index: number; views: View[]; slots: NonNullable<SceneRun['draft']>['blocks']; onChange: (actor: ActorDraft) => void; onRemove: () => void }) {
  const id = useId()
  const toggle = (key: string) => onChange({ ...actor, slot_ids: actor.slot_ids.includes(key) ? actor.slot_ids.filter(value => value !== key) : [...actor.slot_ids, key] })
  return <fieldset className="form-stack author-decision-fields"><legend>Character briefing {index + 1}</legend>
    <label className="field"><span id={id}>Character evidence view</span><select aria-labelledby={id} value={actor.view} onChange={event => onChange({ ...actor, view: event.target.value })}><option value="">Choose a frozen knowledge view</option>{views.map(view => <option key={view.key} value={view.key}>{view.subject} · {view.character_id ? 'Character ' + view.character_id.slice(0, 8) : 'name-only'}</option>)}</select></label>
    <div className="form-stack"><span>Assigned dialogue slots</span>{slots.map(slot => <label className="check-row" key={slot.id}><input type="checkbox" checked={actor.slot_ids.includes(slot.id)} onChange={() => toggle(slot.id)} />{slot.id} · {slot.kind === 'dialogue' ? slot.speaker : ''}</label>)}</div>
    <details><summary>Review original slot cues before sharing</summary><p className="subtle">These proposed cues are for your inspection. They are not sent automatically to the character writer.</p>{slots.filter(slot => actor.slot_ids.includes(slot.id)).map(slot => <p key={slot.id}>{slot.kind === 'dialogue' && slot.instruction}</p>)}</details>
    <label className="field"><span>What this character can observe and attempt</span><textarea rows={4} maxLength={12000} value={actor.briefing} onChange={event => onChange({ ...actor, briefing: event.target.value })} placeholder="Describe the visible situation, any words they heard, and the intended response. Leave the player's choice open." /></label>
    <small>Everything you write here is shared with this character writer. Proposals remain separate from accepted Story events.</small>
    <button className="text-button" onClick={onRemove}>Remove this briefing</button>
  </fieldset>
}

export function ActorInputs({ actors, prompt }: { actors: ActorRequest[]; prompt?: string }) {
  return <div className="form-stack">{actors.map((actor, index) => <div className="prepared-card form-stack" key={index}><strong>{actor.knowledge_lens.subject} · {actor.slot_ids.length} dialogue slot(s)</strong><small>~{actor.estimated_input_tokens.toLocaleString()} input tokens · {actor.knowledge_lens.selected_decisions} of {actor.knowledge_lens.permitted_decisions} permitted decisions · {actor.knowledge_lens.source_count} exact excerpts</small>
    <details><summary>Inspect this character’s exact request</summary><pre className="authoring-prose" tabIndex={0}>{actor.instructions ?? prompt}</pre><pre className="authoring-prose" tabIndex={0}>{actor.content}</pre></details>
  </div>)}</div>
}

export function ActorJobInputs({ job }: { job: SceneJob }) {
  if (!job.snapshot.dialogue_actors) return null
  return <section className="form-stack"><h4>Independent character writers</h4><p className="subtle">These are the requests sent to the model. The assembly context below is retained for validation and is not sent to these writers. Retry keeps completed character responses and resumes unfinished calls.</p><ActorInputs actors={job.snapshot.dialogue_actors} prompt={job.snapshot.prompt.template} /></section>
}
