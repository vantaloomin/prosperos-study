import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { TextField } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import type { ModelProfile, ProfileList } from '../models/types'
import { stepLabels, type RecipeOptions, type RecipeStep } from './recipeEditorTypes'

export function RecipeSteps({ value, options, onChange }: { value: RecipeStep[]; options?: RecipeOptions; onChange: (value: RecipeStep[]) => void }) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles') })
  const update = (index: number, step: RecipeStep) => onChange(value.map((item, n) => n === index ? step : item))
  const move = (index: number, offset: number) => {
    const next = [...value]
    ;[next[index], next[index + offset]] = [next[index + offset], next[index]]
    onChange(next)
  }
  return <section className="form-stack"><h3>Recipe steps</h3><p className="subtle">Choose each task once and arrange its place in the sequence. With no explicit steps, the chosen recipe purpose supplies the writing action.</p><ErrorNotice message={profiles.error?.message} />
    {value.map((step, index) => <fieldset className="writing-sample form-stack" key={step.task}><legend>{index + 1}. {stepLabels[step.task]}</legend>
      {step.task === 'review' && <RecipeLenses value={step.lenses ?? []} options={options?.lenses ?? []} onChange={lenses => update(index, { ...step, lenses })} />}
      <details className="advanced-settings"><summary>Instructions & model for {stepLabels[step.task].toLowerCase()}</summary><div className="form-stack"><TextField label={`${stepLabels[step.task]} instructions`} rows={4} maxLength={12000} value={step.instructions ?? ''} onChange={event => update(index, { ...step, instructions: event.target.value })} hint="Optional instructions for this step. Declared inputs work here too." /><StepModel task={step.task} value={step.profile_id ?? ''} profiles={profiles.data?.profiles ?? []} onChange={profile_id => update(index, { ...step, profile_id: profile_id || null })} /></div></details>
      <div className="writing-resource-actions"><button className="button" disabled={index === 0} onClick={() => move(index, -1)}>Move {stepLabels[step.task].toLowerCase()} earlier</button><button className="button" disabled={index === value.length - 1} onClick={() => move(index, 1)}>Move {stepLabels[step.task].toLowerCase()} later</button><button className="text-button" onClick={() => onChange(value.filter((_, n) => n !== index))}>Remove {stepLabels[step.task].toLowerCase()}</button></div>
    </fieldset>)}
    <div className="writing-resource-actions">{(Object.keys(stepLabels) as RecipeStep['task'][]).map(task => <button className="button" key={task} disabled={value.some(step => step.task === task)} onClick={() => onChange([...value, { task }])}>Add {stepLabels[task].toLowerCase()}</button>)}</div>
    {(value.length > 1 || value.some(step => step.task === 'review')) && <p className="subtle">Select text and choose Run recipe to use this complete workflow. Single-step writing controls will refuse this configuration before making a request.</p>}
  </section>
}

function StepModel({ task, value, profiles, onChange }: { task: RecipeStep['task']; value: string; profiles: ModelProfile[]; onChange: (value: string) => void }) {
  return <label className="field"><span>{stepLabels[task]} model</span><select aria-label={`${stepLabels[task]} model`} value={value} onChange={event => onChange(event.target.value)}><option value="">Inherit this task's Story / workspace assignment</option>{value && !profiles.some(profile => profile.profile_id === value) && <option value={value}>Retained assignment · {value}</option>}{profiles.map(profile => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)}</select><small>An explicit model choice for a run overrides this recipe default.</small></label>
}

function RecipeLenses({ value, options, onChange }: { value: string[]; options: RecipeOptions['lenses']; onChange: (value: string[]) => void }) {
  const toggle = (key: string) => onChange(value.includes(key) ? value.filter(item => item !== key) : [...value, key])
  const retained = value.filter(key => !options.some(option => option.key === key))
  return <div className="form-stack"><p className="subtle">Review lenses select what the readers examine. An empty selection inherits the readers' task defaults.</p>{(['blind', 'informed'] as const).map(scope => <fieldset className="writing-sample form-stack" key={scope}><legend>{scope === 'blind' ? 'Independent reader · prose only' : 'Informed reader · permitted references'}</legend>{options.filter(option => option.scope === scope).map(option => <label className="check-row" key={option.key}><input type="checkbox" checked={value.includes(option.key)} onChange={() => toggle(option.key)} /><span>{option.name}<small>{option.focus}</small></span></label>)}</fieldset>)}{retained.map(key => <label className="check-row" key={key}><input type="checkbox" checked onChange={() => toggle(key)} />Retained lens · {key}</label>)}</div>
}
