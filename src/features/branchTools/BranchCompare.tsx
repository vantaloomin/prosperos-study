import { useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api, operationId } from '../../api'
import type { BranchSummary } from '../../types'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { BranchPicker } from './BranchPicker'
import { ComparisonReader } from './ComparisonReader'
import type { OpenPassage, SavedComparison } from './types'

interface Props { storyId: string; branches: BranchSummary[]; selected: string; onOpen: OpenPassage; onSelect: (id: string) => void }
export function BranchCompare({ storyId, branches, selected, onOpen, onSelect }: Props) {
  const [left, setLeft] = useState(selected)
  const [right, setRight] = useState(() => branches.find(branch => branch.id !== selected && !branch.curation?.archived)?.id ?? '')
  const [comparisonId, setComparisonId] = useState('')
  const [archived, setArchived] = useState(false)
  const action = useAction()
  const cache = useQueryClient()
  const choices = branches.filter(branch => archived || !branch.curation?.archived || [left, right].includes(branch.id))
  const create = () => action.run(async () => {
    const first = branches.find(branch => branch.id === left)
    const second = branches.find(branch => branch.id === right)
    if (!first || !second) throw new Error('Choose two available tellings.')
    const result = await api<{ id: string }>(`/stories/${storyId}/branch-comparisons`, { operation_id: operationId(), left_branch_id: left, right_branch_id: right, left_revision: first.revision, right_revision: second.revision })
    setComparisonId(result.id)
  })
  return <div className="branch-tool-content form-stack"><div className="branch-comparison-choices"><BranchPicker branches={choices} value={left} onChange={setLeft} label="First telling" /><BranchPicker branches={choices} value={right} onChange={setRight} label="Second telling" /></div><div className="branch-tool-actions"><label className="check-row"><input type="checkbox" checked={archived} onChange={event => setArchived(event.target.checked)} />Include archived tellings</label><button className="button primary" disabled={!left || !right || left === right || action.busy} onClick={() => void create()}>{action.busy ? 'Saving comparison…' : 'Compare these tellings'}</button></div><p className="subtle">Each comparison saves the two current revisions. Continuing a telling leaves this comparison intact.</p><ErrorNotice message={action.error} />{action.error && <button className="text-button" onClick={() => void cache.invalidateQueries()}>Refresh available revisions</button>}
    <ComparisonHistory storyId={storyId} value={comparisonId} onChange={setComparisonId} />
    {comparisonId && <ComparisonReader key={comparisonId} id={comparisonId} onOpen={onOpen} onSelect={onSelect} />}
  </div>
}

function ComparisonHistory({ storyId, value, onChange }: { storyId: string; value: string; onChange: (id: string) => void }) {
  const history = useQuery({ queryKey: ['branch-comparisons', storyId], queryFn: () => api<SavedComparison[]>(`/stories/${storyId}/branch-comparisons`) })
  return <><ErrorNotice message={history.error?.message} /><label className="field"><span>Saved comparisons (most recent 100)</span><select aria-label="Saved comparison" value={value} onChange={event => onChange(event.target.value)}><option value="">Choose a saved comparison</option>{history.data?.map(item => <option key={item.id} value={item.id}>{item.left.name} r{item.left.revision} / {item.right.name} r{item.right.revision} · {new Date(item.created_at).toLocaleString()}</option>)}</select></label>{history.isPending && <Loading label="Reading saved comparisons…" />}</>
}
