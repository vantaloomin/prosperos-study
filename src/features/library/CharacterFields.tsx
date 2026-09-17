import { useRef, useState } from 'react'
import { Field, TextField } from '../../components/Fields'
import type { AssetContent, CharacterGreeting } from '../../types'
import { LoreLinks } from './LoreLinks'
import { characterGreetings } from './greetings'

export function CharacterFields({ content, onChange }: { content: AssetContent; onChange: (change: Partial<AssetContent>) => void }) {
  return <>
    <details className="advanced-settings"><summary>Form of address & pronouns</summary><div className="form-stack character-advanced"><Field label="Form of address" value={content.address ?? ''} maxLength={1000} onChange={event => onChange({ address: event.target.value })} /><Field label="Pronouns (optional)" value={content.pronouns ?? ''} maxLength={300} onChange={event => onChange({ pronouns: event.target.value })} /></div></details>
    <TextField label="Voice & manner" value={content.voice ?? ''} onChange={(e) => onChange({ voice: e.target.value })} rows={3} />
    <TextField label="Behavior & boundaries" value={content.behavior_rules ?? ''} onChange={(e) => onChange({ behavior_rules: e.target.value })} rows={4} maxLength={100000} hint="How they act, what matters to them, and limits the writer should respect." />
    <GreetingEditor value={characterGreetings(content)} onChange={(greetings) => onChange({ greetings })} />
    <details className="advanced-settings"><summary>Scenario, examples & editor notes</summary><div className="form-stack character-advanced">
      <TextField label="Scenario" value={content.scenario ?? ''} onChange={(e) => onChange({ scenario: e.target.value })} rows={4} maxLength={100000} hint="The character’s starting circumstances. Story history determines what happens next." />
      <TextField label="Example dialogue" value={content.example_dialogue ?? ''} onChange={(e) => onChange({ example_dialogue: e.target.value })} rows={5} maxLength={100000} hint="Examples of their voice, rather than events that have already happened." />
      <TextField label="Editor notes" value={content.author_notes ?? ''} onChange={(e) => onChange({ author_notes: e.target.value })} rows={4} maxLength={100000} hint="Kept out of narrative requests. Available in the Library and to the sidebar collaborator." />
    </div></details>
    <LoreLinks value={content.lorebook_versions ?? []} onChange={(lorebook_versions) => onChange({ lorebook_versions })} />
  </>
}

function GreetingEditor({ value, onChange }: { value: CharacterGreeting[]; onChange: (next: CharacterGreeting[]) => void }) {
  const [removed, setRemoved] = useState<{ item: CharacterGreeting; index: number } | null>(null)
  const [newId, setNewId] = useState<string | null>(null)
  const addButton = useRef<HTMLButtonElement>(null)
  const change = (id: string, patch: Partial<CharacterGreeting>) => onChange(value.map((item) => item.id === id ? { ...item, ...patch } : item))
  const remove = (item: CharacterGreeting, index: number) => { setRemoved({ item, index }); onChange(value.filter((entry) => entry.id !== item.id)); addButton.current?.focus() }
  const undo = () => {
    if (!removed) return
    const next = [...value]; next.splice(removed.index, 0, removed.item)
    onChange(next); setNewId(removed.item.id); setRemoved(null)
  }
  const add = () => { const id = crypto.randomUUID(); setNewId(id); onChange([...value, { id, label: `Greeting ${value.length + 1}`, text: '' }]) }
  return <section className="character-greetings" aria-label="Opening greetings"><h3>Ways to begin</h3><p className="subtle">Write alternative openings. Choose one during Story setup; the others stay in the Library.</p>
    {value.map((item, index) => <GreetingRow key={item.id} item={item} index={index} added={item.id === newId} onChange={(patch) => change(item.id, patch)} onRemove={() => remove(item, index)} />)}
    {removed && <div className="greeting-undo" role="status">Removed {removed.item.label || 'greeting'}. <button className="text-button" disabled={value.length >= 32} onClick={undo}>Undo removal</button></div>}
    <button ref={addButton} className="button" disabled={value.length >= 32} onClick={add}>Add opening greeting</button>
  </section>
}

function GreetingRow({ item, index, added, onChange, onRemove }: { item: CharacterGreeting; index: number; added: boolean; onChange: (patch: Partial<CharacterGreeting>) => void; onRemove: () => void }) {
  const [expanded, setExpanded] = useState(added)
  return <details className="greeting-card" open={expanded} onToggle={(event) => setExpanded(event.currentTarget.open)}>
    <summary>{item.label || `Greeting ${index + 1}`}</summary><div className="form-stack character-advanced">
      <Field label={`Greeting ${index + 1} label`} value={item.label} maxLength={120} autoFocus={added} onChange={(e) => onChange({ label: e.target.value })} />
      <TextField label={`Greeting ${index + 1} text`} value={item.text} rows={6} maxLength={100000} onChange={(e) => onChange({ text: e.target.value })} hint="Opening prose, ready to become the first assistant contribution. Use names directly; placeholders are not expanded." />
      <button className="text-button danger-text" onClick={onRemove}>Remove greeting {index + 1}</button>
    </div>
  </details>
}
