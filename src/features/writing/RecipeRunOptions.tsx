import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import type { ProfileList } from '../models/types'
import { readyProfiles } from '../models/profileReadiness'
import type { RecipeContent } from './types'
import { stepLabels, type RecipeOptions } from './recipeEditorTypes'
import type { RecipeRunChoices, RecipeTask } from './recipeRunTypes'

export function RecipeRunOptions({ value, content, options, scene, onChange }: { value: RecipeRunChoices; content?: RecipeContent; options: RecipeOptions; scene: boolean; onChange: (value: RecipeRunChoices) => void }) {
  const profiles = useQuery({ queryKey: ['profiles'], queryFn: () => api<ProfileList>('/profiles'), select: readyProfiles })
  const tasks = content?.steps.length ? content.steps.map(step => step.task) : content ? [{ draft: 'writer', review: 'review', revise: 'revision' }[content.purpose] as RecipeTask] : []
  const setModel = (task: RecipeTask, model: string) => {
    const next = { ...value.profiles }
    if (model) next[task] = model
    else delete next[task]
    onChange({ ...value, profiles: next })
  }
  const setSwitch = (key: string, choice: string) => {
    const next = { ...value.task_switches }
    if (choice === 'inherit') delete next[key]
    else next[key] = choice === 'on'
    onChange({ ...value, task_switches: next })
  }
  return <details className="advanced-settings"><summary>Models, review lenses & task choices for this run</summary><div className="form-stack"><p className="subtle">Explicit run choices override recipe and Story defaults. Workspace disables remain a ceiling. Saving these choices changes no defaults.</p><ErrorNotice message={profiles.error?.message} />
    {tasks.map(task => <label className="field" key={task}><span>{stepLabels[task]} model for this run</span><select aria-label={`${stepLabels[task]} model for this run`} value={value.profiles[task] ?? ''} onChange={event => setModel(task, event.target.value)}><option value="">Use recipe / Story assignment</option>{profiles.data?.profiles.map(profile => <option key={profile.profile_id} value={profile.profile_id}>{profile.display_name ?? profile.name}</option>)}</select></label>)}
    {tasks.includes('review') && <fieldset className="form-stack"><legend>Reader focus</legend><label className="check-row"><input type="checkbox" checked={value.review_lenses !== null} onChange={event => onChange({ ...value, review_lenses: event.target.checked ? ['dialogue'] : null })} />Choose review lenses for this run</label>{value.review_lenses !== null && <div className="recipe-field-grid">{options.lenses.map(lens => <label className="check-row" key={lens.key}><input type="checkbox" disabled={lens.key === 'coverage' && !scene} checked={value.review_lenses!.includes(lens.key)} onChange={event => onChange({ ...value, review_lenses: event.target.checked ? [...value.review_lenses!, lens.key] : value.review_lenses!.filter(key => key !== lens.key) })} /><span>{lens.name}<small>{lens.scope === 'blind' ? 'Independent reader' : 'Informed reader'}{lens.key === 'coverage' && !scene ? ' · needs a scene block' : ''}</small></span></label>)}</div>}</fieldset>}
    <details><summary>Override individual task switches</summary><div className="recipe-field-grid">{options.tasks.map(task => <label className="field" key={task.key}><span>{task.name}</span><select aria-label={`Run task ${task.name}`} value={task.key in value.task_switches ? value.task_switches[task.key] ? 'on' : 'off' : 'inherit'} onChange={event => setSwitch(task.key, event.target.value)}><option value="inherit">Use recipe / Story choice</option><option value="on">Enable if workspace permits</option><option value="off">Disable for this run</option></select></label>)}</div></details>
  </div></details>
}
