import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { ContinuityChange } from '../scenes/continuityTypes'
import type { PlanSource } from './planTypes'

type Citation = ContinuityChange['evidence'][number]
interface Page { items: PlanSource[]; revision: number; next_offset: number | null }
export function PlanEvidence({ branchId, revision, selected, onChange }: {
  branchId: string; revision: number; selected: Citation[]; onChange: (value: Citation[]) => void
}) {
  const [offset, setOffset] = useState(0)
  const query = useQuery({ queryKey: ['plan-sources', branchId, revision, offset],
    queryFn: () => api<Page>('/branches/' + branchId + '/plan-sources?offset=' + offset) })
  function toggle(source: PlanSource) {
    onChange(selected.some(item => item.source_id === source.id) ? selected.filter(item => item.source_id !== source.id) :
      [...selected, { source_id: source.id, quote: source.text }])
  }
  return <fieldset className="form-stack plan-evidence"><legend>Supporting passages</legend>
    <p className="subtle">Choose the accepted prose that establishes this plan or change. Selecting evidence does not establish that an interpretation is correct.</p>
    <p role="status">{selected.length} of 8 passages selected</p>
    {selected.length > 0 && <details><summary>Selected evidence</summary>{selected.map(item => <article key={item.source_id}>
      <blockquote>{item.quote}</blockquote><button className="text-button" type="button" onClick={() => onChange(selected.filter(other => other.source_id !== item.source_id))}>Remove this passage</button>
    </article>)}</details>}
    <ErrorNotice message={query.error?.message} />{query.isPending && <Loading label="Finding accepted passages…" />}
    {query.data?.items.map(source => <div className="prepared-card" key={source.id}>
      <label className="check-row"><input type="checkbox" checked={selected.some(item => item.source_id === source.id)}
        disabled={selected.length >= 8 && !selected.some(item => item.source_id === source.id)} onChange={() => toggle(source)} />{source.title}</label>
      <details><summary>Read passage</summary><pre className="authoring-prose" tabIndex={0}>{source.text}</pre></details>
    </div>)}
    <div className="import-downloads"><button className="button" type="button" disabled={!offset || query.isFetching} onClick={() => setOffset(Math.max(0, offset - 8))}>Previous passages</button>
      <button className="button" type="button" disabled={query.data?.next_offset == null || query.isFetching} onClick={() => setOffset(query.data!.next_offset!)}>Next passages</button></div>
  </fieldset>
}
