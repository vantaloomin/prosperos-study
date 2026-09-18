import type { ReviewStep, TaskSetting, WorkflowStep } from './types'

export function ReaderLenses({ role, selected, scene, onChange }: { role: WorkflowStep; selected: ReviewStep; scene: boolean; onChange: (step: ReviewStep) => void }) {
  const lenses = role.lenses?.filter(lens => scene || lens.key !== 'coverage') ?? []
  const keys = selected.lenses ?? lenses.map(lens => lens.key)
  const toggle = (key: string) => onChange({ ...selected, lenses: keys.includes(key) ? keys.filter(value => value !== key) : [...keys, key] })
  return <fieldset className="reader-lenses"><legend>Reading lenses</legend>{lenses.map(lens => {
    const task = role.tasks?.find(item => item.key === (lens.key === 'coverage' ? 'scene-coverage' : `review-${lens.key}`))
    return <label className="check-row" key={lens.key}><input type="checkbox" checked={task?.enabled !== false && keys.includes(lens.key)} disabled={task?.enabled === false} onChange={() => toggle(lens.key)} /><span>{lens.key}<small>{lens.focus}{taskLabel(task)}</small></span></label>
  })}</fieldset>
}

function taskLabel(task?: TaskSetting) {
  if (task?.enabled === false) return ' · disabled in Prompts'
  return task?.custom_prompt || task?.profile_id ? ' · retained task settings can add a request' : ''
}
