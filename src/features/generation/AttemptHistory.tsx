import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'

interface Attempt { id: string; attempt: number; status: string; output: string; error: string }

export function AttemptHistory({ candidateId, attempt }: { candidateId: string; attempt: number }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['attempts', candidateId, attempt],
    queryFn: () => api<Attempt[]>(`/candidates/${candidateId}/attempts`), enabled: open })
  if (attempt < 2) return null
  return <details className="input-inspector" onToggle={(event) => setOpen(event.currentTarget.open)}>
    <summary>Earlier attempts and preserved text</summary>
    <ErrorNotice message={query.error?.message} />
    {query.data?.map((item) => <section key={item.id}><h4>Attempt {item.attempt} · {item.status}</h4><p className="subtle">{item.error}</p><div className="prose">{item.output || 'No text was returned.'}</div></section>)}
  </details>
}
