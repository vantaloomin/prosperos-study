import type { Outcome } from './types'

export function OutcomeSummary({ title, outcome }: { title: string; outcome: Outcome }) {
  if (!outcome.status) return null
  return <section className="outcome-summary"><h3>{title} <span>{outcome.status.replaceAll('_', ' ')}</span></h3>{outcome.reason && <p>{outcome.reason}</p>}{outcome.status === 'resolved' && <ResolvedOutcome outcome={outcome} />}</section>
}

function ResolvedOutcome({ outcome }: { outcome: Outcome }) {
  return <>{outcome.band && <OutcomeText label={outcome.band.label} instruction={outcome.band.instruction} />}{outcome.chain?.map((item) => <OutcomeText key={item.table_id} label={item.row.label} instruction={item.row.instruction} />)}</>
}

function OutcomeText({ label, instruction }: { label: string; instruction: string }) {
  if (label === instruction) return <p>{instruction}</p>
  return <p><strong>{label}{/[.!?]$/.test(label) ? '' : '.'}</strong> {instruction}</p>
}
