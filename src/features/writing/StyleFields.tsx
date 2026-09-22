import { Field, TextField } from '../../components/Fields'
import type { StyleContent } from './types'

const fields = [
  ['prose', 'Prose preferences', 'The qualities you want the writing to have.'],
  ['viewpoint', 'Point of view', 'For example, close third person.'],
  ['tense', 'Tense', 'For example, past tense.'],
  ['dialogue', 'Dialogue conventions', 'Voices, punctuation, subtext, and how much is left unsaid.'],
  ['rhythm', 'Rhythm', 'Sentence lengths, paragraph shape, and deliberate pauses.'],
  ['description', 'Descriptive detail', 'The kinds of details the prose should notice.'],
  ['avoid', 'Unwanted habits', 'Phrases, mannerisms, or tendencies you want to avoid.'],
] as const

export function StyleFields({ value, onChange }: { value: StyleContent; onChange: (value: StyleContent) => void }) {
  return <div className="form-stack">{fields.map(([key, label, hint]) => <TextField key={key} label={label} hint={hint} value={value[key] ?? ''} rows={key === 'prose' ? 4 : 2} maxLength={12000} onChange={event => onChange({ ...value, [key]: event.target.value })} />)}
    <section className="form-stack"><h3>Examples from your writing</h3><p className="subtle">Examples guide the prose style. They do not become events or Canon in your Story.</p>
      {value.examples.map((sample, index) => <fieldset className="writing-sample form-stack" key={index}><legend>Sample {index + 1}</legend><Field label={`Sample ${index + 1} label`} value={sample.label} maxLength={120} onChange={event => onChange({ ...value, examples: value.examples.map((item, n) => n === index ? { ...item, label: event.target.value } : item) })} /><TextField label={`Sample ${index + 1} text`} rows={5} maxLength={20000} value={sample.text} onChange={event => onChange({ ...value, examples: value.examples.map((item, n) => n === index ? { ...item, text: event.target.value } : item) })} /><button className="text-button" onClick={() => onChange({ ...value, examples: value.examples.filter((_, n) => n !== index) })}>Remove sample {index + 1}</button></fieldset>)}
      <button className="button" disabled={value.examples.length >= 8} onClick={() => onChange({ ...value, examples: [...value.examples, { label: `Sample ${value.examples.length + 1}`, text: '' }] })}>Add writing sample</button>
    </section>
  </div>
}
