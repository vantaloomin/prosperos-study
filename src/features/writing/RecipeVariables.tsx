import { Field, TextField } from '../../components/Fields'
import type { RecipeVariable } from './types'

export function RecipeVariables({ value, onChange }: { value: RecipeVariable[]; onChange: (value: RecipeVariable[]) => void }) {
  const update = (index: number, variable: RecipeVariable) => onChange(value.map((item, n) => n === index ? variable : item))
  return <section className="form-stack"><h3>Inputs to ask for</h3><p className="subtle">Give each input a short name to use in instructions, such as {'{{scene_focus}}'}. Text entered when running a recipe stays literal.</p>
    {value.map((variable, index) => <VariableFields key={index} value={variable} number={index + 1} onChange={variable => update(index, variable)} onRemove={() => onChange(value.filter((_, n) => n !== index))} />)}
    <button className="button" disabled={value.length >= 20} onClick={() => onChange([...value, { name: '', label: '', type: 'text', required: true }])}>Add input</button>
  </section>
}

function VariableFields({ value, number, onChange, onRemove }: { value: RecipeVariable; number: number; onChange: (value: RecipeVariable) => void; onRemove: () => void }) {
  const patch = (change: Partial<RecipeVariable>) => onChange({ ...value, ...change })
  const label = `Input ${number}`
  const type = value.type ?? 'text'
  const changeType = (type: NonNullable<RecipeVariable['type']>) => patch({ type, choices: type === 'choice' ? value.choices ?? [] : [] })
  return <fieldset className="writing-sample form-stack"><legend>{label}</legend>
    <div className="recipe-field-grid"><Field label={`${label} name`} maxLength={40} value={value.name} placeholder="scene_focus" onChange={event => patch({ name: event.target.value })} hint="Lowercase letters, numbers and underscores; begin with a letter." /><Field label={`${label} label`} maxLength={120} value={value.label} placeholder="Scene focus" onChange={event => patch({ label: event.target.value })} /></div>
    <TextField label={`${label} description`} rows={2} maxLength={2000} value={value.description ?? ''} onChange={event => patch({ description: event.target.value })} />
    <label className="field"><span>{label} type</span><select aria-label={`${label} type`} value={type} onChange={event => changeType(event.target.value as NonNullable<RecipeVariable['type']>)}><option value="text">Text</option><option value="number">Number</option><option value="choice">Choose from a list</option></select></label>
    {type === 'choice' && <TextField label={`${label} choices`} rows={3} value={(value.choices ?? []).join('\n')} onChange={event => patch({ choices: event.target.value.split('\n') })} hint="One distinct choice per line, up to 30. Choices must not be blank." />}
    <label className="check-row"><input type="checkbox" checked={value.required !== false} onChange={event => patch({ required: event.target.checked })} />Require a value for input {number}</label>
    <VariableDefault value={value} label={label} onChange={patch} />
    <Field label={`${label} example`} maxLength={2000} value={value.example ?? ''} onChange={event => patch({ example: event.target.value })} hint="A hint for the author; it is not supplied as a default." />
    <button className="text-button" onClick={onRemove}>Remove input {number}</button>
  </fieldset>
}

function VariableDefault({ value, label, onChange }: { value: RecipeVariable; label: string; onChange: (value: Partial<RecipeVariable>) => void }) {
  const change = (text: string) => {
    if (!text) { onChange({ default: null }); return }
    const number = Number(text)
    onChange({ default: value.type === 'number' && Number.isFinite(number) && String(number) === text ? number : text })
  }
  const finish = () => {
    if (value.type !== 'number' || value.default === null || value.default === undefined || value.default === '') return
    const number = Number(value.default)
    if (Number.isFinite(number)) onChange({ default: number })
  }
  return <Field label={`${label} default`} value={value.default ?? ''} inputMode={value.type === 'number' ? 'decimal' : undefined} maxLength={12000} onChange={event => change(event.target.value)} onBlur={finish} hint="Optional. A number input needs a finite number; a choice default must match one listed value. Publishing validates the default." />
}
