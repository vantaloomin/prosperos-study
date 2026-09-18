import './usage.css'

const tokenLabels = [
  ['input_tokens', 'Input'], ['output_tokens', 'Output total'], ['thinking_tokens', 'Thinking'],
  ['response_tokens', 'Response'], ['cached_input_tokens', 'Cached input'],
] as const

function reported(value: unknown): value is number {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0
}

export function UsageSummary({ usage }: { usage: Record<string, unknown> }) {
  if (Array.isArray(usage.character_requests)) return <details><summary>Usage by character request</summary>{usage.character_requests.map((item, index) => <section key={index}><h4>{item.subject}{item.reused ? ' · reused from earlier attempt' : ''}</h4><UsageSummary usage={item.usage} /></section>)}</details>
  const summary = usage.summary as Record<string, unknown> | undefined
  if (!summary) return <details className="usage-details"><summary>Usage: {Object.keys(usage).length ? 'raw provider report' : 'not reported yet'}</summary><p className="subtle">Readable counts and cost are unavailable for this request.</p><pre>{JSON.stringify(usage, null, 2)}</pre></details>
  return <div className="usage-summary" aria-label="Reported model usage"><dl>{tokenLabels.map(([key, label]) => <div key={key}><dt>{label}</dt><dd>{reported(summary[key]) ? summary[key].toLocaleString() : 'Not reported'}</dd></div>)}<div><dt>Cost</dt><dd>{costLabel(summary)}</dd></div></dl><p className="subtle">Provider-reported tokens for this attempt. Thinking is included in output total; cached input is included in input. Cost is shown only when the provider reports it.</p><details><summary>Raw usage report</summary><pre>{JSON.stringify(usage, null, 2)}</pre></details></div>
}

function costLabel(summary: Record<string, unknown>) {
  if (reported(summary.cost_credits)) return summary.cost_credits.toLocaleString('en-US', { maximumFractionDigits: 6 }) + ' OpenRouter credits'
  if (reported(summary.cost_usd)) return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 6 }).format(summary.cost_usd) + ' USD'
  return 'Not reported'
}
