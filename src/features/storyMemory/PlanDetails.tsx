import type { PlannedEvent } from '../scenes/continuityTypes'

export function PlanDetails({ plan }: { plan: PlannedEvent }) {
  return <div className="form-stack plan-details">
    <p><strong>{plan.status}</strong> · {plan.timing}</p>
    <small className="subtle">{plan.time_anchor}</small>
    <ul>{plan.participants.map(person => <li key={person.id}><span>{person.name}</span><small>{person.commitment}</small></li>)}</ul>
    {plan.resolution && <p>{plan.resolution}</p>}
  </div>
}
