import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { RequestStatus } from './RequestStatus'
import { useGeneration } from './useGeneration'
import { isWorking } from './types'

export function DraftActivity({ id, onOpen }: { id: string; onOpen: () => void }) {
  const query = useGeneration(id, false)
  const action = useAction()
  const candidates = query.data?.candidates ?? []
  const current = candidates.find(isWorking) ?? candidates.find(candidate => !candidate.accepted_node_id)
  const stop = () => action.run(async () => { if (current) await api(`/candidates/${current.id}/cancel`, {}) })
  return <div className="draft-activity"><div>{current && <RequestStatus candidate={current} />}{query.error && <ErrorNotice message="Connection to the app lost. Status is unknown; no new request has been sent." />}<ErrorNotice message={action.error} /></div><button className="text-button" onClick={onOpen}>Open draft & details</button>{current && isWorking(current) && <button className="button" disabled={action.busy} onClick={stop}>Stop</button>}</div>
}
