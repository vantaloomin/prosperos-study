import { TextField } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { WritingSelect } from './WritingSelect'
import { useWritingResources } from './useWritingResources'
import { useEffectiveWriting } from './useEffectiveWriting'
import type { RecipeContent, RecipeVariable, WritingChoices, WritingResource } from './types'
import './writing.css'

export function RequestWritingChoices({ storyId, value, onChange, recipePurpose = 'draft', expanded = false }: { storyId: string; value: WritingChoices; onChange: (value: WritingChoices) => void; recipePurpose?: 'draft' | 'revise' | 'all'; expanded?: boolean }) {
  const resources = useWritingResources()
  const { recipeId, recipe, content, styleId, style, error } = useEffectiveWriting(storyId, value)
  return <details open={expanded || undefined} className="advanced-settings writing-request"><summary>Style & recipe for this request</summary><div className="form-stack"><WritingSelect label="Request recipe" kind="recipe" recipePurpose={recipePurpose === 'all' ? undefined : recipePurpose} value={value.recipe} resources={resources.data ?? []} inherit="Use Story recipe" onChange={next => onChange({ ...value, recipe: next, variables: {} })} /><WritingSelect label="Request writing style" kind="style" value={value.style} resources={resources.data ?? []} inherit="Use recipe / Story style" onChange={next => onChange({ ...value, style: next })} /><p className="subtle" role="status">Effective recipe: {resourceLabel(recipeId, recipe)}. Effective style: {resourceLabel(styleId, style)}.</p>{content && <RecipeInputs key={recipeId} content={content} values={value.variables} onChange={variables => onChange({ ...value, variables })} />}<p className="subtle">Choices apply to the next request. Preview its inputs to inspect composed guidance and its budget.</p><ErrorNotice message={error || resources.error?.message} /></div></details>
}

function resourceLabel(id: string, resource?: WritingResource) {
  if (id === 'none') return 'none'
  return resource ? `${resource.name} · v${resource.number}` : 'loading selected version'
}

function RecipeInputs({ content, values, onChange }: { content: RecipeContent; values: WritingChoices['variables']; onChange: (values: WritingChoices['variables']) => void }) {
  const update = (variable: RecipeVariable, value: string) => {
    const next = { ...values }
    next[variable.name] = variable.type === 'number' && value !== '' ? Number(value) : value
    onChange(next)
  }
  return <>{content.variables.map(variable => <RecipeInput key={variable.name} variable={variable} value={String(values[variable.name] ?? variable.default ?? '')} onChange={value => update(variable, value)} />)}</>
}

function RecipeInput({ variable, value, onChange }: { variable: RecipeVariable; value: string; onChange: (value: string) => void }) {
  const label = `${variable.label}${variable.required ? ' (required)' : ''}`
  if (variable.type === 'choice') return <label className="field"><span>{label}</span><select aria-label={label} value={value} onChange={event => onChange(event.target.value)}><option value="">Choose…</option>{variable.choices?.map(choice => <option key={choice} value={choice}>{choice}</option>)}</select><small>{variable.description}</small></label>
  if (variable.type === 'number') return <label className="field"><span>{label}</span><input aria-label={label} type="number" step="any" value={value} placeholder={variable.example} onChange={event => onChange(event.target.value)} /><small>{variable.description}</small></label>
  return <TextField label={label} rows={2} value={value} placeholder={variable.example} hint={variable.description} onChange={event => onChange(event.target.value)} />
}
