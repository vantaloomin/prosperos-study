import { AttemptFields } from '../mechanics/PrepareBeat'
import { OutcomeSummary } from '../mechanics/OutcomeSummary'
import type { Beat, Opportunity, RngSettings, TableVersion } from '../mechanics/types'
import type { SceneBeat, SceneRun } from './types'

export type ChanceBoundary = Omit<Beat, 'label'>
export interface SceneChancePlan {
  inherited: { opportunity_id: string; result: Opportunity['snapshot'] } | null
  entries: { beat_id: string; title: string; result: Opportunity['snapshot'] }[]
}
export interface ChanceSnapshot { chance_version?: number; settings?: RngSettings; tables?: Record<string, TableVersion> }
const emptyBoundary: ChanceBoundary = { completed: false, waiting_for_player: true, protected: false, resolves_event: false, new_scene: false, family: 'narrative-push', attempt: null, extras: [] }
const flags = [['completed', 'A meaningful beat will be complete'], ['waiting_for_player', 'A player choice or action will still be unresolved'], ['protected', 'Keep this moment uninterrupted'], ['resolves_event', 'This beat resolves the previous generated event'], ['new_scene', 'This boundary starts a new scene']] as const

export function ChanceEditor({ beat, run, onChange }: { beat: SceneBeat; run: SceneRun; onChange: (change: Partial<SceneBeat>) => void }) {
  const value = beat.chance ?? emptyBoundary
  const patch = (change: Partial<ChanceBoundary>) => onChange({ chance: { ...value, ...change } })
  if (!run.snapshot.chance_version) return null
  return <details className="mechanics-advanced"><summary>Chance at this beat</summary><div className="form-stack"><p className="subtle">Only completed, unprotected boundaries with no player action waiting are eligible. This edit makes no rolls.</p>
    <label className="field"><span>Event family for {beat.title || 'this beat'}</span><select value={value.family} onChange={(event) => patch({ family: event.target.value as ChanceBoundary['family'] })}><option value="narrative-push">Narrative Push · develop an interaction</option><option value="encounter">Encounter · explore or transition</option><option value="none">No event · handling or optional tables only</option></select></label>
    <div className="mechanic-options">{flags.map(([key, label]) => <label className="check-row" key={key}><input type="checkbox" checked={value[key]} onChange={(event) => patch({ [key]: event.target.checked })} />{label}</label>)}</div>
    <label className="check-row"><input type="checkbox" checked={!!value.attempt} onChange={(event) => patch({ attempt: event.target.checked ? { action: '', actor: '', domain: '', level: 0, fractured: false, prepared: false } : null })} />Resolve an action already chosen by the character</label>
    {value.attempt && <AttemptFields value={value.attempt} onChange={(attempt) => patch({ attempt })} />}
    <ChanceExtras run={run} value={value} onChange={patch} />
  </div></details>
}

function ChanceExtras({ run, value, onChange }: { run: SceneRun; value: ChanceBoundary; onChange: (change: Partial<ChanceBoundary>) => void }) {
  const tables = Object.values(run.snapshot.tables ?? {}).filter((table) => ['extra', 'texture'].includes(table.definition.purpose))
  const toggle = (id: string) => onChange({ extras: value.extras.includes(id) ? value.extras.filter((key) => key !== id) : [...value.extras, id] })
  if (!tables.length) return null
  return <div><p className="subtle">Optional inspiration uses the Story's enabled tables and exclusions. Choose at most eight.</p><div className="mechanic-options">{tables.map((table) => <label className="check-row" key={table.table_id}><input type="checkbox" checked={value.extras.includes(table.table_id)} disabled={!value.extras.includes(table.table_id) && value.extras.length >= 8} onChange={() => toggle(table.table_id)} />{table.definition.name}</label>)}</div></div>
}

export function SceneChance({ run }: { run: SceneRun }) {
  if (!run.snapshot.chance_version) return null
  const plan = run.state.gate_a?.mechanics
  if (!plan) return <p className="subtle">{run.snapshot.settings?.enabled ? 'Chance is scheduled once when you approve this plan. Review each boundary under “Edit selected beat plan”; omitted boundaries remain ineligible. Draft alternatives and reviews reuse the saved results.' : 'Automatic chance is off for this plan. Approval makes no automatic draws.'}</p>
  return <details className="input-inspector"><summary>Saved chance · {plan.entries.length} planned {plan.entries.length === 1 ? 'boundary' : 'boundaries'}</summary><div className="form-stack"><p className="subtle">{run.state.accepted ? 'These results were adopted with the accepted scene.' : 'These results are reserved for this plan. Story state changes only when the checked scene is accepted.'}</p>
    {plan.inherited && <><p>A previously prepared beat is included unchanged. It was not rolled again.</p><SavedBoundary title="Prepared opening" result={plan.inherited.result} /></>}
    {plan.entries.map((entry) => <SavedBoundary key={entry.beat_id} title={entry.title} result={entry.result} />)}
  </div></details>
}

function SavedBoundary({ title, result }: { title: string; result: Opportunity['snapshot'] }) {
  return <article className="review-finding"><h4>{title}</h4>{result.eligibility && <p>{result.eligibility}</p>}
    <OutcomeSummary title="Event" outcome={result.event} /><OutcomeSummary title="Handling" outcome={result.handling} />
    {Object.entries(result.extras).map(([key, outcome]) => <OutcomeSummary key={key} title={result.tables[key]?.definition.name ?? key} outcome={outcome} />)}
    <details><summary>Inspect saved results</summary><pre>{JSON.stringify(result, null, 2)}</pre></details>
  </article>
}
