import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice } from '../../components/Feedback'
import type { Branch } from '../../types'
import type { BackgroundSummary } from './types'
import { InterpretationSetup } from './InterpretationSetup'
import { InterpretationResults } from './InterpretationResults'

export function BackgroundInterpretations({ branch, current, onBranch }: { branch: Branch; current: BackgroundSummary; onBranch: (id: string) => void }) {
  const [setup, setSetup] = useState(false)
  const [run, setRun] = useState('')
  const history = useQuery({ queryKey: ['private-history', branch.id], queryFn: () => api<{ id: string; created_at: string }[]>(`/branches/${branch.id}/background/interpretations`) })
  const started = (id: string) => { setSetup(false); setRun(id) }
  return <section className="form-stack mechanics-advanced"><h3>Give the cues a private meaning</h3><p className="subtle">{current.interpreted ? 'This setup has a selected interpretation. Its details remain fixed across future responses.' : 'Develop specific motives and future possibilities with a model. The seeded cues and dates stay fixed.'}</p>
    <button className="button" onClick={() => setSetup(true)}>Develop private background</button>
    {current.interpretation_run_id && <button className="text-button" onClick={() => setRun(current.interpretation_run_id!)}>Open the selected model request</button>}
    <ErrorNotice message={history.error?.message} />{history.data && history.data.length > 0 && <div className="review-history">{history.data.map((item, index) => <button className="button quiet" key={item.id} aria-pressed={run === item.id} onClick={() => setRun(item.id)}>Private request {index + 1} · {new Date(item.created_at).toLocaleString()}</button>)}</div>}
    {run && <InterpretationResults key={run} id={run} onBranch={onBranch} />}{setup && <InterpretationSetup branch={branch} onClose={() => setSetup(false)} onStarted={started} />}
  </section>
}
