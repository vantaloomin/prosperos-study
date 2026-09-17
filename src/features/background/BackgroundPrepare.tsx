import { useState } from 'react'
import { api, operationId } from '../../api'
import { Field } from '../../components/Fields'
import { ErrorNotice } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'

export function BackgroundPrepare({ branch, revision, onBranch }: { branch: Branch; revision: number; onBranch: (id: string) => void }) {
  const [characters, setCharacters] = useState<string[]>([])
  const [drives, setDrives] = useState(false)
  const [hooks, setHooks] = useState(false)
  const [count, setCount] = useState(2)
  const [origin, setOrigin] = useState('Story opening')
  const [day, setDay] = useState(0)
  const [horizon, setHorizon] = useState(30)
  const action = useAction()
  const selected = drives ? characters : []
  const incomplete = drives && !characters.length
  const available = branch.attachments.filter((item) => item.kind !== 'lorebook' && item.enabled)
  const toggle = (id: string) => setCharacters((current) => current.includes(id) ? current.filter((item) => item !== id) : [...current, id])
  const prepare = () => action.run(async () => {
    const result = await api<{ branch_id: string }>(`/branches/${branch.id}/background`, { operation_id: operationId(), expected_revision: revision, character_ids: selected, hooks: hooks ? count : 0, origin, day, horizon })
    onBranch(result.branch_id)
  })
  return <div className="form-stack"><h3>Leave room for the unexpected</h3><p className="subtle">Prepare private inspiration once for this path. Writers interpret these cues within your genre and established world; preparation adds no Story events and starts no model call.</p>
    <label className="check-row"><input type="checkbox" checked={drives} onChange={(event) => setDrives(event.target.checked)} />Private drives for supporting characters</label>
    {drives && <fieldset className="background-characters"><legend>Characters you want the writer to guide</legend><p className="subtle">Choose supporting characters only. This never authorizes unchosen player feelings, actions or consent.</p>{available.map((item) => <label className="check-row" key={item.asset_id}><input type="checkbox" checked={characters.includes(item.asset_id)} onChange={() => toggle(item.asset_id)} />{item.version.name} · v{item.version.number}</label>)}{available.length === 0 && <p className="subtle">Attach and enable a supporting character in Context first.</p>}</fieldset>}
    <label className="check-row"><input type="checkbox" checked={hooks} onChange={(event) => setHooks(event.target.checked)} />Buried future hooks</label>
    {hooks && <div className="mechanic-fields"><Field label="Number of hooks" type="number" min={1} max={8} value={count} onChange={(event) => setCount(Number(event.target.value))} /><Field label="Within the next Story days" type="number" min={1} max={3650} value={horizon} onChange={(event) => setHorizon(Number(event.target.value))} /></div>}
    <Field label="Day zero means" maxLength={200} value={origin} onChange={(event) => setOrigin(event.target.value)} hint="For example: arrival at the station, the coronation, or the first day of school. No real-world calendar is assumed." />
    <Field label="Current Story day" type="number" min={0} max={1000000} value={day} onChange={(event) => setDay(Number(event.target.value))} hint="Record the day already established in the Story. Preparing hooks does not advance time." />
    <p className="subtle">Uses the Story’s pinned Automaton A, Automaton B and Hooks tables, including disabled tables and excluded results. This is an explicit one-time roll even when automatic randomness is off. Forking from a message preserves only the setup recorded at that message.</p>
    <ErrorNotice message={action.error} /><button className="button primary" disabled={action.busy || incomplete || (!selected.length && !hooks) || !origin.trim()} onClick={prepare}>Prepare concealed background</button>
  </div>
}
