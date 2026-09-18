import { useEffect, useRef, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { usePersistent } from '../../hooks/usePersistent'
import type { Branch } from '../../types'
import '../../styles/story-rehearsal.css'
import { RehearsalResults } from './RehearsalResults'
import { sameRehearsalBoundary, viewpointLabel, type RehearsalCatalogue, type RehearsalDraft, type RehearsalReport } from './rehearsalTypes'

export function SceneRehearsal({ branch, onDecisions }: { branch: Branch; onDecisions: () => void }) {
  const endpoint = '/branches/' + branch.id + '/memory-rehearsal'
  const catalogue = useQuery({ queryKey: ['memory-rehearsal', branch.id, branch.revision], queryFn: () => api<RehearsalCatalogue>(endpoint), refetchOnMount: 'always', refetchOnWindowFocus: 'always' })
  const [draft, setDraft] = usePersistent<RehearsalDraft>('roleplay:rehearsal:' + branch.id, { query: '', views: [], include_library: false })
  const [report, setReport] = useState<RehearsalReport | null>(null)
  const action = useAction()
  const heading = useRef<HTMLHeadingElement>(null)
  useEffect(() => { heading.current?.focus() }, [])
  const change = (next: RehearsalDraft) => { setDraft(next); setReport(null) }
  const prepare = () => action.run(async () => {
    if (!catalogue.data) return
    setReport(await api<RehearsalReport>(endpoint, { ...draft, expected_revision: catalogue.data.boundary.revision, expected_version_id: catalogue.data.boundary.version_id }))
  })
  const refresh = () => { setReport(null); void catalogue.refetch() }
  const stale = !!report && !!catalogue.data && !sameRehearsalBoundary(report.boundary, catalogue.data.boundary)
  return <section className="form-stack"><h3 ref={heading} tabIndex={-1}>Before the next scene</h3>
    <p>Revisit earlier evidence and compare what your characters have been told. This is an author’s preparation view. Nothing is sent to a model or added to the Story.</p>
    <fieldset disabled={action.busy} aria-label="Rehearsal setup" className="rehearsal-form prepared-card form-stack">
      <label className="field"><span>What should this scene remember?</span><input maxLength={1000} value={draft.query} onChange={event => change({ ...draft, query: event.target.value })} placeholder="The observatory key, the promised reunion…" /></label>
      <label className="check-row"><input type="checkbox" checked={draft.include_library} onChange={event => change({ ...draft, include_library: event.target.checked })} />Search pinned Canon and Character excerpts too</label>
      <p className="subtle">References use enabled, attached editions and eligible writing fields. Private background, author notes, conditional entries and other branches are excluded.</p>
      <ViewChoices catalogue={catalogue.data} draft={draft} onChange={change} />
      <ErrorNotice message={catalogue.error?.message || action.error} />
      <div className="import-downloads"><button className="button primary" disabled={!catalogue.data || !draft.query.trim() || catalogue.isFetching} onClick={prepare}>Rehearse from evidence</button><button className="button" disabled={catalogue.isFetching} onClick={refresh}>Refresh current path</button></div>
    </fieldset>
    {stale && <p role="status">The path or author decisions changed. These are earlier results; refresh before preparing the scene.</p>}
    {report && <RehearsalResults report={report} onDecisions={onDecisions} />}
  </section>
}

function ViewChoices({ catalogue, draft, onChange }: { catalogue?: RehearsalCatalogue; draft: RehearsalDraft; onChange: (value: RehearsalDraft) => void }) {
  const toggle = (key: string) => onChange({ ...draft, views: draft.views.includes(key) ? draft.views.filter(value => value !== key) : [...draft.views, key] })
  const unavailable = draft.views.filter(key => catalogue && !catalogue.views.some(view => view.key === key))
  return <details><summary>Whose knowledge should we compare? ({draft.views.length} selected)</summary><div className="form-stack authoring-history"><p className="subtle">Choose up to eight viewpoints, or search without a character comparison. Only explicit saved grants count. A missing grant does not establish ignorance.</p>
    {catalogue?.views.map(view => <label className="check-row" key={view.key}><input type="checkbox" checked={draft.views.includes(view.key)} disabled={!draft.views.includes(view.key) && draft.views.length >= 8} onChange={() => toggle(view.key)} />{viewpointLabel(view)}</label>)}
    {unavailable.map(key => <label className="check-row" key={key}><input type="checkbox" checked onChange={() => toggle(key)} />Unavailable viewpoint · remove this selection</label>)}
    {catalogue && !catalogue.views.length && <p>Attach Characters or record name-only knowledge in Author decisions to compare viewpoints.</p>}
  </div></details>
}
