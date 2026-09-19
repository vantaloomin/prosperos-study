import { useEffect, useState } from 'react'
import type { Candidate } from './types'
import { isWorking } from './types'

function statusLabel(candidate: Candidate) {
  if (candidate.status === 'cleaning') return 'Cleaning up wording'
  if (candidate.status === 'running' && candidate.usage.writer_recall?.status === 'preparing') return 'Checking earlier evidence'
  if (candidate.status === 'running') return candidate.output ? 'Writing' : 'Waiting for the model'
  return { queued: 'Waiting to start', done: 'Draft ready', error: 'Could not finish this draft', cancelled: 'Stopped', interrupted: 'Interrupted' }[candidate.status]
}

export function RequestStatus({ candidate }: { candidate: Candidate }) {
  const [clock, setClock] = useState(() => Date.now())
  const working = isWorking(candidate)
  useEffect(() => {
    if (!working) return
    const timer = window.setInterval(() => setClock(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [working])
  const activity = candidate.activity
  const end = activity?.finished_at ? Date.parse(activity.finished_at) : clock
  const seconds = activity && (working || activity.finished_at) ? Math.max(0, Math.floor((end - Date.parse(activity.started_at)) / 1000)) : null
  return <div className="request-status"><span role="status" aria-live="polite" aria-atomic="true"><i className={working ? 'status-dot working' : 'status-dot'} />{statusLabel(candidate)}</span>
    {seconds !== null && <span aria-label="Elapsed time">{Math.floor(seconds / 60)}:{String(seconds % 60).padStart(2, '0')}</span>}
    <small>{candidate.profile.name} · {candidate.profile.config.model} · attempt {candidate.attempt}</small>
    {working && <small>Request limit: {candidate.profile.config.timeout_seconds}s. Waiting does not mean the request has failed.</small>}
  </div>
}
