import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Branch } from '../../types'
import type { BackgroundContext } from './types'
import { BackgroundPrepare } from './BackgroundPrepare'
import { BackgroundSettings } from './BackgroundSettings'
import { BackgroundReveal } from './BackgroundReveal'
import { BackgroundInterpretations } from './BackgroundInterpretations'

export function BackgroundPanel({ branch, onBranch }: { branch: Branch; onBranch: (id: string) => void }) {
  const query = useQuery({ queryKey: ['background', branch.id], queryFn: () => api<BackgroundContext>(`/branches/${branch.id}/background`) })
  const [reveal, setReveal] = useState('')
  const current = query.data?.history.find((item) => item.id === query.data.current)
  return <><ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}{query.data && <div className="form-stack">
    {current ? <BackgroundSettings key={current.id} current={current} branchId={branch.id} revision={query.data.revision} onBranch={onBranch} onReveal={setReveal} /> : <BackgroundPrepare key={branch.id} branch={branch} revision={query.data.revision} onBranch={onBranch} />}
    {current && <BackgroundInterpretations key={branch.id} branch={{ ...branch, revision: query.data.revision }} current={current} onBranch={onBranch} />}
    {query.data.history.length > 1 && <details><summary>Earlier setup versions</summary><div className="form-stack">{query.data.history.filter((item) => item.id !== query.data.current).map((item) => <button className="roll-history-row" key={item.id} onClick={() => setReveal(item.id)}><span>Reveal setup · day {item.day}</span><small>{new Date(item.created_at).toLocaleString()}</small></button>)}</div></details>}
  </div>}{reveal && <BackgroundReveal id={reveal} onClose={() => setReveal('')} />}</>
}
