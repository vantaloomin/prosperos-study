import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { TextField } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import type { RecipeContent, WritingResource } from './types'
import { WritingSelect } from './WritingSelect'
import { RecipeVariables } from './RecipeVariables'
import { RecipeSteps } from './RecipeSteps'
import { RecipeSettings } from './RecipeSettings'
import { purposeHints, type RecipeOptions } from './recipeEditorTypes'

export function RecipeFields({ value, resources, onChange }: { value: RecipeContent; resources: WritingResource[]; onChange: (value: RecipeContent) => void }) {
  const options = useQuery({ queryKey: ['recipe-editor-options'], queryFn: () => api<RecipeOptions>('/writing-recipes/options') })
  return <div className="form-stack"><label className="field"><span>Recipe purpose</span><select aria-label="Recipe purpose" value={value.purpose} onChange={event => onChange({ ...value, purpose: event.target.value as RecipeContent['purpose'] })}><option value="draft">Draft new prose</option><option value="review">Review selected text</option><option value="revise">Revise selected text</option></select><small>{purposeHints[value.purpose]}</small></label>
    <TextField label="Recipe instructions" rows={7} maxLength={12000} value={value.instructions} onChange={event => onChange({ ...value, instructions: event.target.value })} hint="Use {{variable_name}} for an input, or {{{{ and }}}} for literal double braces. Substituted text stays literal." />
    <WritingSelect label="Writing style" kind="style" value={value.style} resources={resources} inherit="Use the Story's style" onChange={style => onChange({ ...value, style })} />
    <RecipeVariables value={value.variables} onChange={variables => onChange({ ...value, variables })} />
    <ErrorNotice message={options.error?.message} />
    <RecipeSteps value={value.steps} options={options.data} onChange={steps => onChange({ ...value, steps })} />
    {options.data && <RecipeSettings value={value} options={options.data} onChange={onChange} />}
    <AdvancedRecipe value={value} onChange={onChange} />
  </div>
}

function AdvancedRecipe({ value, onChange }: { value: RecipeContent; onChange: (value: RecipeContent) => void }) {
  const [text, setText] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [baseline, setBaseline] = useState('')
  const current = useRef(value)
  useEffect(() => { current.current = value }, [value])
  const load = async () => {
    if (busy) return
    setBusy(true)
    try {
      if (baseline !== JSON.stringify(value)) throw new Error('The recipe draft changed after this JSON was loaded. Load the current recipe again before applying advanced changes.')
      const parsed: unknown = JSON.parse(text)
      const next = await api<RecipeContent>('/writing-recipes/validate', { content: parsed })
      if (baseline !== JSON.stringify(current.current)) throw new Error('The recipe draft changed during validation. Load the current recipe again before applying advanced changes.')
      onChange(next); setBaseline(JSON.stringify(next)); setError('')
    } catch (failure) { setError(failure instanceof Error ? failure.message : 'Invalid recipe.') }
    finally { setBusy(false) }
  }
  return <details className="advanced-settings"><summary>Advanced recipe JSON</summary><div className="form-stack"><p className="subtle">Inspect every setting, including detailed table mappings. Validation changes this draft only; it does not publish or start work.</p><button className="text-button" onClick={() => { setText(JSON.stringify(value, null, 2)); setBaseline(JSON.stringify(value)); setError('') }}>Load current recipe into editor</button><TextField label="Advanced recipe JSON" rows={12} value={text} onChange={event => setText(event.target.value)} /><ErrorNotice message={error} /><button className="button" disabled={!text.trim() || busy} onClick={load}>Validate & load changes into draft</button></div></details>
}
