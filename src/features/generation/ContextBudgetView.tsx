import type { ContextBudget } from './contextTypes'

const number = (value: number) => value.toLocaleString()

export function ContextBudgetView({ budget }: { budget: ContextBudget }) {
  const inputWidth = Math.min(100, budget.estimated_input_tokens / budget.context_tokens * 100)
  const outputWidth = Math.min(100 - inputWidth, budget.output_tokens / budget.context_tokens * 100)
  const overhead = budget.overhead_tokens ?? 0
  const total = budget.estimated_input_tokens + budget.output_tokens + overhead
  const overheadWidth = Math.min(100 - inputWidth - outputWidth, overhead / budget.context_tokens * 100)
  return <article className={`context-budget ${budget.fits ? '' : 'context-over-budget'}`}>
    <header><div><strong>{budget.name}</strong><small>{budget.model} · {budget.provider} · profile v{budget.version}</small></div>
      <span>{budget.fits ? `${number(budget.remaining_tokens)} left` : `${number(-budget.remaining_tokens)} over`}</span></header>
    <div className="context-budget-meter" role="meter" aria-label={`${budget.name} estimated context usage`} aria-valuemin={0} aria-valuemax={budget.context_tokens} aria-valuenow={Math.min(total, budget.context_tokens)} aria-valuetext={`${number(total)} estimated tokens including output and overhead, of ${number(budget.context_tokens)} configured`}>
      <span style={{ width: `${inputWidth}%` }} /><span style={{ width: `${outputWidth}%` }} />{overhead > 0 && <span style={{ width: overheadWidth + '%' }} />}</div>
    <dl><div><dt>Input estimate</dt><dd>{number(budget.estimated_input_tokens)}</dd></div><div><dt>Output reserved</dt><dd>{number(budget.output_tokens)}</dd></div>{overhead > 0 && <div><dt>Overhead allowance</dt><dd>{number(overhead)}</dd></div>}<div><dt>Configured limit</dt><dd>{number(budget.context_tokens)}</dd></div></dl>
    {!budget.fits && <p className="context-budget-warning">This request exceeds the configured allowance. Adjust this profile in Settings or choose another writer; no sources will be silently removed.</p>}
    {budget.provider === 'codex' && <p className="subtle">The output reserve is used for this estimate. The Codex CLI adapter does not enforce it as a generation limit.</p>}
  </article>
}
