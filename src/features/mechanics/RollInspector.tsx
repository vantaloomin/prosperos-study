import { LoreReceiptView } from '../library/LoreReceiptView'
import { useQuery } from '@tanstack/react-query'
import { api, operationId } from '../../api'
import { Modal } from '../../components/Modal'
import { ErrorNotice, Loading } from '../../components/Feedback'
import { useAction } from '../../hooks/useAction'
import type { Branch } from '../../types'
import type { Opportunity } from './types'
import { OutcomeSummary } from './OutcomeSummary'

export function RollInspector({ id, branch, onClose, onBranch }: { id: string; branch?: Branch; onClose: () => void; onBranch?: (id: string) => void }) {
  const query = useQuery({ queryKey: ['opportunity', id], queryFn: () => api<Opportunity>(`/opportunities/${id}`) })
  return <Modal open onClose={onClose} title="The shape of this beat" description="A preserved proposal, separate from accepted story state." wide><div className="dialog-body form-stack"><ErrorNotice message={query.error?.message} />{!query.data && !query.error && <Loading />}{query.data && <RollDetails opportunity={query.data} branch={branch} onBranch={onBranch} onClose={onClose} />}</div></Modal>
}

function beatStatus(snapshot: Opportunity['snapshot']) {
  if (snapshot.lore?.advanced && snapshot.eligibility) return 'No event or handling was resolved. Canon selection is recorded for this completed beat.'
  return snapshot.eligibility || 'Only accepting the resulting narration commits this proposal.'
}

function RollDetails({ opportunity, branch, onBranch, onClose }: { opportunity: Opportunity; branch?: Branch; onBranch?: (id: string) => void; onClose: () => void }) {
  const { snapshot } = opportunity
  const action = useAction()
  const reroll = () => action.run(async () => {
    if (!branch || !onBranch) return
    const result = await api<{ branch_id: string }>(`/branches/${branch.id}/opportunities`, { operation_id: operationId(), expected_revision: branch.revision, beat: snapshot.beat, manual: snapshot.manual, reroll_of: opportunity.id, branch_name: `${snapshot.beat.label.slice(0,95)} · reroll` })
    onBranch(result.branch_id)
    onClose()
  })
  return <><div className="prepared-card"><span className="eyebrow">{snapshot.manual ? 'Explicit one-time request' : 'Beat-based opportunity'}</span><h3>{snapshot.beat.label}</h3><p className="subtle">{beatStatus(snapshot)}</p></div><OutcomeSummary title="Event" outcome={snapshot.event} /><OutcomeSummary title="Handling" outcome={snapshot.handling} />{Object.entries(snapshot.extras).map(([key, outcome]) => <OutcomeSummary key={key} title={key} outcome={outcome} />)}
    {snapshot.lore && <LoreReceiptView receipt={snapshot.lore} label="Canon for this prepared beat" />}
    <details className="input-inspector"><summary>Qualitative instructions supplied to the writer</summary><pre>{JSON.stringify(snapshot.writer, null, 2)}</pre></details>
    <details className="input-inspector"><summary>Complete roll log, table versions & proposed state</summary><p className="subtle">{snapshot.algorithm} · seed {snapshot.seed}</p><div className="roll-draws">{snapshot.draws.map((draw, index) => <div key={index}><span>{draw.stream} · {draw.purpose}</span><strong>d{draw.sides} → {draw.result}</strong></div>)}</div>{!snapshot.draws.length && <p className="subtle">No event or handling draws were made. Canon draws are listed in the Canon record above.</p>}<pre>{JSON.stringify(snapshot, null, 2)}</pre></details>
    <ErrorNotice message={action.error} />{branch && onBranch && <div className="mechanics-footer"><p className="subtle">Reroll from the original story point with current settings. Keep the old branch and record. No model call is started.</p><button className="button" onClick={reroll} disabled={action.busy}>Reroll on a new branch</button></div>}
  </>
}
