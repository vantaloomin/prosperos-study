import { useDeferredValue, useRef, useState } from 'react'
import { Field, TextField } from '../../components/Fields'
import { Modal } from '../../components/Modal'
import type { AssetContent } from '../../types'
import { LoreBookRules, LoreRules } from './LoreRules'
import { LoreScan } from './LoreScan'
import { ImportedEntryPicker } from './ImportedEntryPicker'
import { emptyLore, newEntry, type LoreDefinition, type LoreEntry } from './loreTypes'

export function LoreEntries({ content, versionId, onChange }: { content: AssetContent; versionId?: string; onChange: (patch: Partial<AssetContent>) => void }) {
  const [open, setOpen] = useState(false)
  const definition = content.lore_definition ?? emptyLore
  return <section className="lore-entry-launch"><h3>Entries & rules</h3><p className="subtle">Keep distinct places, people and facts in individual Markdown entries. {definition.entries.length} saved in this draft.</p>
    <button className="button" onClick={() => setOpen(true)}>Edit Canon entries</button>
    {open && <LoreEditor value={definition} versionId={versionId} onChange={(lore_definition) => onChange({ lore_definition })} onClose={() => setOpen(false)} />}
  </section>
}

function LoreEditor({ value, versionId, onChange, onClose }: { value: LoreDefinition; versionId?: string; onChange: (value: LoreDefinition) => void; onClose: () => void }) {
  const [selected, setSelected] = useState(value.entries[0]?.id ?? '')
  const [search, setSearch] = useState('')
  const filter = useDeferredValue(search.toLocaleLowerCase())
  const [scan, setScan] = useState(false)
  const [importing, setImporting] = useState(false)
  const [added, setAdded] = useState('')
  const [removed, setRemoved] = useState<{ entry: LoreEntry; index: number } | null>(null)
  const addButton = useRef<HTMLButtonElement>(null)
  const entries = (next: LoreEntry[]) => onChange({ ...value, entries: next })
  const add = () => { const entry = newEntry(); entries([...value.entries, entry]); setSearch(''); setSelected(entry.id); setAdded(entry.id) }
  const remove = (entry: LoreEntry) => { setRemoved({ entry, index: value.entries.indexOf(entry) }); entries(value.entries.filter((item) => item.id !== entry.id)); setSelected(''); addButton.current?.focus() }
  const undo = () => {
    if (!removed) return
    const next = [...value.entries]; next.splice(removed.index, 0, removed.entry)
    entries(next); setSelected(removed.entry.id); setAdded(removed.entry.id); setSearch(''); setRemoved(null)
  }
  const entry = value.entries.find((item) => item.id === selected)
  const visible = value.entries.filter((item) => `${item.title}\n${item.text}`.toLocaleLowerCase().includes(filter))
  return <Modal open wide title="Lore entries" description="Changes stay in your unpublished book draft. Done returns to the book; Save new version publishes it." onClose={onClose}>
    <div className="dialog-body form-stack"><p className="lore-rollout-note">Saved entry rules guide writing and informed reviews on each pinned path. Optional chance is recorded with prepared beats and approved scene plans; reading and branch switches never roll. Canon overviews remain active world guidance.</p>
      <div className="lore-editor-grid"><nav className="lore-entry-list" aria-label="Lore entry selection"><Field label="Find an entry" value={search} onChange={(e) => setSearch(e.target.value)} />
        <p className="subtle">{visible.length} matching entries</p><div className="lore-entry-buttons">{visible.slice(0, 80).map((item) => <button key={item.id} className={`lore-entry-select ${selected === item.id ? 'selected' : ''}`} aria-pressed={selected === item.id} onClick={() => { setSelected(item.id); setAdded('') }}><span>{item.title || 'Untitled entry'}</span><small>{item.enabled ? item.kind : 'Off'}</small></button>)}</div>
        {visible.length > 80 && <p className="subtle">Showing 80 matches. Refine the search to find another entry.</p>}
        <button ref={addButton} className="button" disabled={value.entries.length >= 500} onClick={add}>Add entry</button>
        {versionId && <button className="text-button" onClick={() => setImporting(true)}>Bring in preserved entries</button>}
      </nav><section className="form-stack lore-entry-detail" aria-label="Selected entry">
        {entry ? <EntryDetail key={entry.id} entry={entry} added={entry.id === added} onChange={(patch) => entries(value.entries.map((item) => item.id === entry.id ? { ...item, ...patch } : item))} onRemove={() => remove(entry)} /> : <div className="lore-entry-empty"><h3>One place for every detail</h3><p>Add an entry or choose one from the list. Each published entry gets its own Markdown file.</p></div>}
        {removed && <p role="status" className="subtle">Removed {removed.entry.title} from this draft. <button className="text-button" disabled={value.entries.length >= 500} onClick={undo}>Undo entry removal</button></p>}
      </section></div><LoreBookRules value={value} onChange={onChange} />
    </div><footer className="dialog-footer"><button className="button" onClick={() => setScan(true)}>Test draft rules</button><button className="button primary" onClick={onClose}>Done</button></footer>
    {scan && <LoreScan definition={value} onClose={() => setScan(false)} />}
    {importing && versionId && <ImportedEntryPicker versionId={versionId} entries={value.entries} onAdd={(entry) => { entries([...value.entries, entry]); setSearch(''); setSelected(entry.id); setAdded(entry.id) }} onClose={() => setImporting(false)} />}
  </Modal>
}

function EntryDetail({ entry, added, onChange, onRemove }: { entry: LoreEntry; added: boolean; onChange: (patch: Partial<LoreEntry>) => void; onRemove: () => void }) {
  return <><Field label="Entry title" value={entry.title} maxLength={160} autoFocus={added} onChange={(e) => onChange({ title: e.target.value })} />
    <label className="check-row"><input type="checkbox" checked={entry.enabled} onChange={(e) => onChange({ enabled: e.target.checked })} />Enable this entry</label>
    <TextField label="Entry prose · Markdown" value={entry.text} maxLength={100000} rows={10} onChange={(e) => onChange({ text: e.target.value })} hint="Write reference material. A fact here does not mean a character knows it or that an event has happened." />
    <LoreRules entry={entry} onChange={onChange} /><button className="text-button danger-text" onClick={onRemove}>Remove entry from draft</button></>
}
