import { useId, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import type { Branch } from '../../types'
import { SourceChoices } from './SummarySetup'
import type { Source, SourcePage } from './types'

export interface CharacterIdentity { id: string; name: string; version_id: string }

export function CharacterBinding({ characters, value, onChange }: { characters: CharacterIdentity[]; value?: string; onChange: (id: string, name?: string) => void }) {
  const id = useId()
  return <label className="field"><span id={id}>Character identity</span><select aria-labelledby={id} value={value ?? ''} onChange={event => onChange(event.target.value, characters.find(item => item.id === event.target.value)?.name)}>
    <option value="">Name-only viewpoint</option>
    {value && !characters.some(item => item.id === value) && <option value={value}>Previously attached Character (unavailable)</option>}
    {characters.map(item => <option key={item.id} value={item.id}>{item.name} · {item.id.slice(0, 8)}</option>)}
  </select><small>A linked Character keeps its grants after a rename. Its whole profile is never shared automatically.</small></label>
}

export function ControlSources({ branch, library, selected, onToggle }: { branch: Branch; library: boolean; selected: Source[]; onToggle: (source: Source) => void }) {
  const id = useId()
  const [category, setCategory] = useState('prose')
  const [page, setPage] = useState(0)
  const query = useQuery({ queryKey: ['memory-control-sources', branch.id, branch.revision, category, page], queryFn: () => api<SourcePage>('/branches/' + branch.id + '/memory-control-sources?category=' + category + '&offset=' + page * 12) })
  return <div className="form-stack">
    {library && <label className="field"><span id={id}>Evidence source</span><select aria-labelledby={id} value={category} onChange={event => { setCategory(event.target.value); setPage(0) }}><option value="prose">Accepted story passages</option><option value="library">Pinned Canon & Character text</option></select></label>}
    {category === 'library' && <p className="subtle">Select exact excerpts from the editions enabled in this Story. Only Canon overview text and Character writing fields are offered. Conditional entries, greetings and author notes are excluded. Every selected excerpt is shared in full; a later edition needs a new grant.</p>}
    {selected.length > 0 && <details><summary>Review or remove selected evidence ({selected.length})</summary>{selected.map(source => <article className="prepared-card form-stack" key={source.id}><strong>{source.name ?? source.title}{source.edition ? ' · edition ' + source.edition : ''}{source.field ? ' · ' + source.field : ''}</strong><pre className="authoring-prose" tabIndex={0}>{source.text}</pre><button className="text-button" onClick={() => onToggle(source)}>Remove this excerpt</button></article>)}</details>}
    <ErrorNotice message={query.error?.message} />
    <SourceChoices report={query.data} pending={query.isPending} fetching={query.isFetching} selected={selected} page={page} onPage={setPage} onToggle={onToggle} emptyMessage={category === 'library' ? 'No eligible reference text in the enabled, pinned editions. Add it in Library and attach that edition to this Story.' : undefined} />
  </div>
}
