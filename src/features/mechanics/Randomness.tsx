import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { api } from '../../api'
import { ErrorNotice, Loading } from '../../components/Feedback'
import type { Branch } from '../../types'
import type { MechanicsContext } from './types'
import { RngControls } from './RngControls'
import { PrepareBeat } from './PrepareBeat'
import { TableLibrary } from './TableLibrary'
import { RollInspector } from './RollInspector'
import { BackgroundPanel } from '../background/BackgroundPanel'

export function Randomness({ branch, onBranch }: { branch: Branch; onBranch: (id: string) => void }) {
  const query = useQuery({ queryKey: ['mechanics', branch.id], queryFn: () => api<MechanicsContext>(`/branches/${branch.id}/mechanics`) })
  const [tab, setTab] = useState('controls')
  const [inspecting, setInspecting] = useState('')
  return <>
    <div className="dialog-body mechanics-panel"><div className="tabs" aria-label="Randomness views">{[['controls', 'Controls'], ['prepare', 'Prepare a beat'], ['background', 'Background'], ['tables', 'Tables'], ['history', 'Roll history']].map(([key, label]) => <button key={key} aria-pressed={tab === key} onClick={() => setTab(key)}>{label}</button>)}</div>
      <ErrorNotice message={query.error?.message} />{query.isPending && <Loading />}
      {query.data && <div className="mechanics-content">
        {tab === 'controls' && <RngControls key={query.data.story_revision} branch={branch} data={query.data} onSaved={() => setTab('prepare')} />}
        {tab === 'prepare' && <PrepareBeat branch={branch} data={query.data} onBranch={onBranch} onInspect={setInspecting} />}
        {tab === 'tables' && <TableLibrary data={query.data} />}
        {tab === 'background' && <BackgroundPanel key={branch.id} branch={branch} onBranch={onBranch} />}
        {tab === 'history' && <RollHistory data={query.data} onInspect={setInspecting} />}
      </div>}
    </div>
    {inspecting && <RollInspector id={inspecting} branch={branch} onClose={() => setInspecting('')} onBranch={onBranch} />}
  </>
}

function RollHistory({ data, onInspect }: { data: MechanicsContext; onInspect: (id: string) => void }) {
  return <div className="form-stack"><p className="subtle">Rolls belong to the branch and point where they were prepared. No-event results and unaccepted proposals remain in this history.</p>{data.history.map((item, index) => <button className="roll-history-row" key={item.id} onClick={() => onInspect(item.id)}><span>Prepared beat {data.history.length - index}</span><small>{new Date(item.created_at).toLocaleString()}</small></button>)}{!data.history.length && <p className="subtle">No rolls have been prepared on this branch.</p>}</div>
}
