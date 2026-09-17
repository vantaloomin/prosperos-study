import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'

export function AssessmentHistory({ branchId, onSelect }: { branchId: string; onSelect: (id: string) => void }) {
  const [open, setOpen] = useState(false)
  const query = useQuery({ queryKey: ['assessments', branchId], queryFn: () => api<{ id: string; created_at: string }[]>(`/branches/${branchId}/assessments`), enabled: open })
  return <details className="draft-history" onToggle={(e) => setOpen(e.currentTarget.open)}><summary>Beat assessment history</summary><ErrorNotice message={query.error?.message} /><div>{query.data?.map((run, index) => <button className="text-button" key={run.id} onClick={() => onSelect(run.id)}>Assessment {query.data.length - index} · {new Date(run.created_at).toLocaleString()}</button>)}</div>{query.data?.length === 0 && <p className="subtle">No assessments saved on this branch.</p>}</details>
}
