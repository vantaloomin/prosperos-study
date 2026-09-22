import { TemplateChoice } from '../prompts/AgentTemplates'
import { Field, TextField } from '../../components/Fields'
import { experiences, type SetupDraft } from './setup'
import { StoryStyle } from './WritingPreferences'
import { providers, type ProfileList } from '../models/types'
import { OpeningPassage } from './SetupOpening'

export function SetupStory({ draft, patch }: { draft: SetupDraft; patch: (next: Partial<SetupDraft>) => void }) {
  return <div className="form-stack"><Field label="Story title" value={draft.title} maxLength={120} placeholder="The observatory" onChange={(event) => patch({ title: event.target.value })} hint="Add a title, or choose Skip setup to begin with Untitled Story." /><StoryStyle value={draft} onChange={patch} /><TextField label="Story brief" rows={4} value={draft.premise} maxLength={30000} onChange={(event) => patch({ premise: event.target.value })} placeholder="A place, a person, an unfinished question…" hint="Premise, tone, and lasting guidance for the whole story. This is not a passage or a path-specific author’s note." />
    <details className="advanced-settings"><summary>Add an opening passage (optional)</summary><div className="setup-writing-options"><OpeningPassage draft={draft} patch={patch} /></div></details>
  </div>
}

const assistance = [
  { id: 'off', name: 'Stay with my direction', description: 'Random events are off. You decide when the situation changes.' },
  { id: 'quiet', name: 'A little uncertainty', description: '10% chance on a prepared eligible beat, with four beats between events.' },
  { id: 'balanced', name: 'Room for surprise', description: '15% chance on a prepared eligible beat, with three beats between events.' },
]
export function SetupAssistance({ draft, patch }: { draft: SetupDraft; patch: (next: Partial<SetupDraft>) => void }) {
  return <div className="form-stack"><fieldset className="setup-choices"><legend className="field-label">How much surprise?</legend>{assistance.map((item) => <label className={`setup-choice ${draft.randomness === item.id ? 'selected' : ''}`} key={item.id}><input type="radio" name="setup-randomness" checked={draft.randomness === item.id} onChange={() => patch({ randomness: item.id })} /><span><strong>{item.name}</strong><small>{item.description}</small></span></label>)}</fieldset>
    <p className="subtle">Events use eligible story beats, with a chance and cooldown. In Randomness, you can prepare a beat yourself or enable model-assisted beat checks. Every table and result can be switched off; intentional no-event outcomes remain possible.</p>
    <TemplateChoice experience={draft.experience} value={draft.agent_settings} onChange={agent_settings => patch({ agent_settings })} /><div className="setup-callout"><strong>You keep the final say</strong><p className="subtle">Workflow offers planning, specialist reviews, and proposed continuity changes with explicit acceptance. The sidebar collaborator can discuss the full context but cannot advance the Story. Prompts and individual model assignments stay in secondary editors.</p></div>
  </div>
}

function castReview(draft: SetupDraft) {
  return { label: draft.experience === 'roleplay' ? 'Your character' : 'Cast', text: draft.player_agency === 'user' ? 'Your viewpoint character’s choices remain yours' : 'Shared with the writer', step: 3 }
}

function agentsReview(draft: SetupDraft) {
  return { label: 'Agents', text: `${draft.experience === 'roleplay' ? 'Active' : 'Passive'} template${draft.agent_settings?.agent_template.customized ? ' · customized' : ''}`, step: 4 }
}

function reviewRows(draft: SetupDraft, profiles: ProfileList) {
  const selected = profiles.profiles.find((profile) => profile.profile_id === (draft.primary_profile_id || profiles.primary_profile_id))
  return [
    { label: 'Experience', text: experiences.find((item) => item.id === draft.experience)?.name ?? draft.experience, step: 0 },
    { label: 'Writer', text: selected ? `${selected.name} · ${providers[selected.config.provider].name} · ${selected.config.model}` : 'Manual writing to begin', step: 1 },
    { label: 'Style', text: [draft.genre, draft.tone].filter(Boolean).join(' · ') || 'Develop as you write', step: 2 },
    { label: 'Prose', text: [draft.pov, draft.tense, draft.response_length].filter(Boolean).join(' · '), step: 3 },
    { label: 'Participation', text: draft.persona || 'Decide as you write', step: 3 },
    castReview(draft),
    { label: 'Library', text: draft.assets.map((asset) => `${asset.name} v${asset.number}`).join(', ') || 'No items attached', step: 3 },
    agentsReview(draft),
    { label: 'Randomness', text: assistance.find((item) => item.id === draft.randomness)?.name ?? 'Off', step: 4 },
  ]
}

export function SetupReview({ draft, profiles, onEdit }: { draft: SetupDraft; profiles: ProfileList; onEdit: (step: number) => void }) {
  return <div className="setup-review form-stack"><div><span className="eyebrow">YOUR NEXT CHAPTER</span><h2>{draft.title || 'Give this Story a title'}</h2><p className="subtle setup-premise">{draft.premise || 'A blank page, ready for your first words.'}</p><button className="text-button" disabled={!!draft.pending} onClick={() => onEdit(2)}>Edit Story</button></div>
    <dl className="setup-summary">{reviewRows(draft, profiles).map((row) => <div key={row.label}><dt>{row.label}</dt><dd>{row.text}</dd><button className="text-button" disabled={!!draft.pending} onClick={() => onEdit(row.step)}>Edit {row.label.toLowerCase()}</button></div>)}</dl>
    {draft.opening && <div><h3>Your opening passage</h3><p className="subtle">{draft.opening_source ? 'Character greeting · assistant contribution. Adapted wording preserves its source version.' : 'Custom narrator contribution.'}</p><div className="setup-opening prose">{draft.opening}</div></div>}
    <p className="subtle">Start saves this Story on your device{draft.opening ? ' with your opening passage' : ' ready for your first passage'}. No model request starts until you explicitly generate. Preferences, Library attachments and model assignments can be changed later.</p>
  </div>
}
