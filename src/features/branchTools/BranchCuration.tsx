import { Star } from 'lucide-react'
import { useQueryClient } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import type { BranchSummary } from '../../types'
import { useAction } from '../../hooks/useAction'
import { ErrorNotice } from '../../components/Feedback'

export function BranchCurationControls({ branch }: { branch: BranchSummary }) {
  const action = useAction()
  const cache = useQueryClient()
  const state = branch.curation ?? { favorite: false, archived: false, revision: 0 }
  const update = (change: { favorite?: boolean; archived?: boolean }) => action.run(async () => {
    await api(`/branches/${branch.id}/curation`, { operation_id: operationId(), expected_revision: state.revision, favorite: state.favorite, archived: state.archived, ...change }, 'PUT')
  })
  return <div className="branch-curation"><div className="branch-tool-actions"><button className="button" aria-pressed={state.favorite} disabled={action.busy} onClick={() => void update({ favorite: !state.favorite })}><Star size={15} fill={state.favorite ? 'currentColor' : 'none'} />{state.favorite ? 'Favorited' : 'Favorite'}</button><button className="button" disabled={action.busy} onClick={() => void update({ archived: !state.archived })}>{state.archived ? 'Unarchive telling' : 'Archive telling'}</button></div><ErrorNotice message={action.error} />{action.error && <button className="text-button" onClick={() => void cache.invalidateQueries()}>Refresh branch status</button>}<p className="subtle">{state.archived ? 'Archived · still available through references and archived filters.' : 'Archiving hides this telling from ordinary browsing. Its history and book selections stay available.'}</p></div>
}
