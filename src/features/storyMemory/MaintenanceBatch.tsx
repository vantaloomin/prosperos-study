import { useLayoutEffect, useRef } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import { batchWorking, type Batch } from './maintenanceTypes'

export function MaintenanceBatch({ id, onReview, onBack }: { id: string; onReview: (id: string) => void; onBack: () => void }) {
  const query = useQuery({ queryKey: ['summary-batch', id], queryFn: () => api<Batch>('/summary-batches/' + id), refetchInterval: state => state.state.data && batchWorking(state.state.data.status) ? 700 : false })
  const heading = useRef<HTMLHeadingElement>(null)
  useLayoutEffect(() => { heading.current?.focus() }, [])
  return <section className="form-stack"><div className="section-heading"><h3 tabIndex={-1} ref={heading}>Summary batch</h3><button className="text-button" onClick={onBack}>Choose individual excerpts</button></div><ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}
    {query.data && <BatchProgress batch={query.data} onReview={onReview} />}
  </section>
}

function BatchProgress({ batch, onReview }: { batch: Batch; onReview: (id: string) => void }) {
  const action = useAction()
  const completed = batch.requests.filter(request => request.status === 'done').length
  const command = (verb: 'stop' | 'resume') => action.run(async () => { await api('/summary-batches/' + batch.id + '/' + verb, verb === 'resume' ? { operation_id: operationId(), expected_status: batch.status } : {}) })
  const running = batchWorking(batch.status)
  return <><p role="status">{batch.status} · {completed} of {batch.snapshot.request_count} requests complete · {batch.snapshot.selected_count} selected excerpts</p>
    <p className="subtle">Requests run in sequence. Closing keeps queued work running. Each result remains a suggestion until you review and save a memory version.</p>
    <ErrorNotice message={batch.error || action.error} />
    {running && <button className="button" disabled={action.busy} onClick={() => command('stop')}>Stop this batch</button>}
    {!running && batch.status !== 'done' && <><p className="subtle">Resuming uses the saved model, instructions and sources. Completed requests are kept; unfinished requests may incur another model call. Automatic batches require automatic maintenance to be enabled.</p><button className="button" disabled={action.busy} onClick={() => command('resume')}>Resume saved batch</button></>}
    {batch.runs.map(run => <article className="prepared-card" key={run.id}><h4>Group {run.ordinal + 1}</h4><ul>{batch.requests.filter(request => request.run_id === run.run_id).map(request => <li key={request.id}>{request.profile_name} · {request.status}</li>)}</ul><button className="button" onClick={() => onReview(run.run_id)}>Review this group</button></article>)}
  </>
}
