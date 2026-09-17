import { Field, TextField } from '../../components/Fields'
import { agencyOptions, experiences, type WritingPreferences as Preferences } from './setup'

export function StoryStyle({ value, onChange }: { value: Preferences; onChange: (next: Partial<Preferences>) => void }) {
  return <div className="setup-field-pair"><Field label="Genre" placeholder="Everyday life, mystery, space opera…" maxLength={300} value={value.genre} onChange={(e) => onChange({ genre: e.target.value })} /><Field label="Tone" placeholder="Warm, tense, playful, reflective…" maxLength={300} value={value.tone} onChange={(e) => onChange({ tone: e.target.value })} /></div>
}

export function Participation({ value, onChange }: { value: Preferences; onChange: (next: Partial<Preferences>) => void }) {
  const roleplay = value.experience === 'roleplay'
  const options = roleplay ? agencyOptions : [['shared', 'Let the writer portray the cast'], ['user', 'Reserve my viewpoint character’s choices for me']]
  return <div className="form-stack"><TextField label="Your participation" rows={3} maxLength={10000} value={value.persona} onChange={(e) => onChange({ persona: e.target.value })} placeholder={roleplay ? 'The character you inhabit and the choices you want to keep…' : 'Your direction as an author, or a viewpoint character you want to write yourself…'} />
    <label className="field"><span>{roleplay ? 'Who controls your character?' : 'Who portrays the cast?'}</span><select value={value.player_agency} onChange={(e) => onChange({ player_agency: e.target.value })}>{options.map(([id, label]) => <option key={id} value={id}>{label}</option>)}</select><small>You can change this for future writing. Earlier scenes remain as written.</small></label>
    <details className="advanced-settings"><summary>Point of view, tense & response length</summary><div className="form-stack setup-writing-options"><Field label="Point of view" value={value.pov} maxLength={300} onChange={(e) => onChange({ pov: e.target.value })} /><Field label="Tense" value={value.tense} maxLength={300} onChange={(e) => onChange({ tense: e.target.value })} /><Field label="Preferred response length" value={value.response_length} maxLength={500} onChange={(e) => onChange({ response_length: e.target.value })} hint="Guidance for the writer, rather than a rigid output limit." /></div></details>
  </div>
}

export function ExperienceChoice({ value, onChange }: { value: string; onChange: (value: string) => void }) {
  return <fieldset className="setup-choices"><legend className="field-label">How would you like to write?</legend>{experiences.map((option) => <label className={`setup-choice ${value === option.id ? 'selected' : ''}`} key={option.id}><input type="radio" name="story-experience" value={option.id} checked={value === option.id} onChange={() => onChange(option.id)} /><span><strong>{option.name}</strong><small>{option.description}</small></span></label>)}</fieldset>
}
